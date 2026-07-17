import logging
import os
import json
import secrets
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from httpx_sse import aconnect_sse

from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.genai import types as genai_types
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import TracerProvider, export
from pydantic import BaseModel
from dotenv import load_dotenv

from authenticated_httpx import create_authenticated_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

class Feedback(BaseModel):
    score: float
    text: str | None = None
    run_id: str | None = None
    user_id: str | None = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

provider = TracerProvider()
processor = export.BatchSpanProcessor(
    CloudTraceSpanExporter(),
)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent_name = os.getenv("AGENT_NAME", None)
agent_server_url = os.getenv("AGENT_SERVER_URL")
if not agent_server_url:
    raise ValueError("AGENT_SERVER_URL environment variable not set")
else:
    agent_server_url = agent_server_url.rstrip("/")

clients: Dict[str, httpx.AsyncClient] = {}

async def get_client(agent_server_origin: str) -> httpx.AsyncClient:
    global clients
    if agent_server_origin not in clients:
        clients[agent_server_origin] = create_authenticated_client(agent_server_origin)
    return clients[agent_server_origin]

async def create_session(agent_server_origin: str, agent_name: str, user_id: str) -> Dict[str, Any]:
    httpx_client = await get_client(agent_server_origin)
    headers=[
        ("Content-Type", "application/json")
    ]
    session_request_url = f"{agent_server_origin}/apps/{agent_name}/users/{user_id}/sessions"
    session_response = await httpx_client.post(
        session_request_url,
        headers=headers
    )
    session_response.raise_for_status()
    return session_response.json()

async def get_session(agent_server_origin: str, agent_name: str, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    httpx_client = await get_client(agent_server_origin)
    headers=[
        ("Content-Type", "application/json")
    ]
    session_request_url = f"{agent_server_origin}/apps/{agent_name}/users/{user_id}/sessions/{session_id}"
    session_response = await httpx_client.get(
        session_request_url,
        headers=headers
    )
    if session_response.status_code == 404:
        return None
    session_response.raise_for_status()
    return session_response.json()


async def list_agents(agent_server_origin: str) -> List[str]:
    httpx_client = await get_client(agent_server_origin)
    headers=[
        ("Content-Type", "application/json")
    ]
    list_url = f"{agent_server_origin}/list-apps"
    list_response = await httpx_client.get(
        list_url,
        headers=headers
    )
    list_response.raise_for_status()
    agent_list = list_response.json()
    if not agent_list:
        agent_list = ["agent"]
    return agent_list


async def query_adk_sever(
        agent_server_origin: str, agent_name: str, user_id: str, message: str, session_id
) -> AsyncGenerator[Dict[str, Any], None]:
    httpx_client = await get_client(agent_server_origin)
    request = {
        "appName": agent_name,
        "userId": user_id,
        "sessionId": session_id,
        "newMessage": {
            "role": "user",
            "parts": [{"text": message}]
        },
        "streaming": False
    }
    async with aconnect_sse(
        httpx_client,
        "POST",
        f"{agent_server_origin}/run_sse",
        json=request
    ) as event_source:
        if event_source.response.is_error:
            event = {
                "author": agent_name,
                "content":{
                    "parts": [
                        {
                            "text": f"Error {event_source.response.text}"
                        }
                    ]
                }
            }
            yield event
        else:
            async for server_event in event_source.aiter_sse():
                event = server_event.json()
                yield event

class SimpleChatRequest(BaseModel):
    message: str
    user_id: str = "test_user"
    session_id: Optional[str] = None


class LearnerProfileRequest(BaseModel):
    subject: str
    familiarity: int = 3
    known_concepts: str = ""
    goal: str = ""


class LearnerContinuationRequest(BaseModel):
    task_id: str
    context_id: str
    action: str
    response: str = ""
    idempotency_key: str


async def _coordinator_post(path: str, payload: dict, browser_session: str) -> dict:
    client = await get_client(agent_server_url)  # type: ignore[arg-type]
    response = await client.post(
        f"{agent_server_url}{path}",
        json=payload,
        headers={"X-Browser-Session": browser_session},
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Course session could not continue.")
    return response.json()


async def _coordinator_get(path: str, browser_session: str) -> dict:
    client = await get_client(agent_server_url)  # type: ignore[arg-type]
    response = await client.get(
        f"{agent_server_url}{path}", headers={"X-Browser-Session": browser_session}
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Course session could not continue.")
    return response.json()


@app.post("/api/learner/start")
async def start_learner_course(
    request: LearnerProfileRequest,
    response: Response,
    course_session: str | None = Cookie(default=None),
) -> dict:
    """Create an anonymous, browser-bound learner task without logging profile text."""
    session = course_session or secrets.token_urlsafe(32)
    result = await _coordinator_post("/internal/learner/start", request.model_dump(), session)
    response.set_cookie("course_session", session, httponly=True, samesite="lax", secure=False)
    return result


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Suppress a browser-only favicon miss for the demo UI."""
    return Response(status_code=204)


@app.post("/api/learner/continue")
async def continue_learner_course(
    request: LearnerContinuationRequest,
    course_session: str | None = Cookie(default=None),
) -> dict:
    if not course_session:
        raise HTTPException(status_code=403, detail="Course session is not available.")
    return await _coordinator_post("/internal/learner/continue", request.model_dump(), course_session)


@app.get("/api/learner/{task_id}")
async def learner_course_status(
    task_id: str, course_session: str | None = Cookie(default=None)
) -> dict:
    if not course_session:
        raise HTTPException(status_code=403, detail="Course session is not available.")
    return await _coordinator_get(f"/internal/learner/{task_id}", course_session)

@app.post("/api/chat_stream")
async def chat_stream(request: SimpleChatRequest):
    """Streaming chat endpoint."""
    global agent_name, agent_server_url
    if not agent_name:
        agent_name = (await list_agents(agent_server_url))[0] # type: ignore

    session = None
    if request.session_id:
        session = await get_session(
            agent_server_url, # type: ignore
            agent_name,
            request.user_id,
            request.session_id
        )
    if session is None:
        session = await create_session(
            agent_server_url, # type: ignore
            agent_name,
            request.user_id
        )

    events = query_adk_sever(
        agent_server_url, # type: ignore
        agent_name,
        request.user_id,
        request.message,
        session["id"]
    )

    async def event_generator():
        final_text = ""
        async for event in events:
            # Send progress updates based on which agent is active
            if event["author"] == "researcher":
                 yield json.dumps({"type": "progress", "text": "🔍 Researcher is gathering information..."}) + "\n"
            elif event["author"] == "judge":
                 yield json.dumps({"type": "progress", "text": "⚖️ Judge is evaluating findings..."}) + "\n"
            elif event["author"] == "content_builder":
                 yield json.dumps({"type": "progress", "text": "✍️ Content Builder is writing the course..."}) + "\n"
            # Accumulate final text
            if "content" in event and event["content"]:
                content = genai_types.Content.model_validate(event["content"])
                for part in content.parts: # type: ignore
                    if part.text:
                        final_text += part.text
        # Send final result
        yield json.dumps({"type": "result", "text": final_text.strip()}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

# Mount frontend from the copied location
frontend_path = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
