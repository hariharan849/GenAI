import asyncio
import logging
import os
import random

from api.platform.runtime import configure_event_loop_policy, configure_prometheus_registry

configure_event_loop_policy()
configure_prometheus_registry()

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from api import metrics  # noqa: F401
from api.config import get_settings
from api.middlewares import MetricsMiddleware
from api.platform.lifespan import lifespan
from api.routers import agentic_ask, eval as eval_router, hybrid_search, ping
from api.routers.ask import ask_router, stream_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(
    title="Nuke Documentation RAG API",
    description="Nuke documentation search and question answering with RAG capabilities",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator(
    should_group_status_codes=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],
).instrument(app)


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    payload, content_type = metrics.render_metrics()
    return Response(content=payload, headers={"Content-Type": content_type})


@app.get("/slow", tags=["Observability"])
@app.get("/api/v1/slow", tags=["Observability"])
async def slow_endpoint() -> dict[str, float | str]:
    delay_seconds = random.uniform(1.0, 3.0)
    await asyncio.sleep(delay_seconds)
    return {"message": "Slow response simulated", "delay_seconds": round(delay_seconds, 3)}


app.include_router(ping.router, prefix="/api/v1")
app.include_router(hybrid_search.router, prefix="/api/v1")
app.include_router(ask_router, prefix="/api/v1")
app.include_router(stream_router, prefix="/api/v1")
app.include_router(agentic_ask.router)
app.include_router(eval_router.router)


if __name__ == "__main__":
    uvicorn.run(app, port=8083, host="0.0.0.0")
