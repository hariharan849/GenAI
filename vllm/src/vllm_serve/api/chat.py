import uuid
import time
from typing import AsyncIterator
from fastapi import HTTPException, APIRouter
from fastapi.responses import StreamingResponse

from src.vllm_serve.config import settings
from src.vllm_serve.engine import build_sampling_params, get_engine, get_tokenizer, init_engine, shutdown_engine
from src.vllm_serve.models import (
    ChatRequest,
    ChatResponse,
    Choice,
    DeltaMessage,
    Message,
    StreamChoice,
    StreamChunk,
    Usage,
)


router = APIRouter()

async def _apply_chat_template(messages: list[Message]) -> str:
    tokenizer = await get_tokenizer()
    return tokenizer.apply_chat_template(
        [m.model_dump() for m in messages], tokenize=False, add_generation_prompt=True,
    )


def _request_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"

@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    engine = get_engine()
    prompt = await _apply_chat_template(req.messages)
    params = build_sampling_params(
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        top_p=req.top_p,
        top_k=req.top_k,
        stop=req.stop,
        frequency_penalty=req.frequency_penalty,
        presence_penalty=req.presence_penalty,
        stream=req.stream,
    )
    rid = _request_id()

    if req.stream:
        return StreamingResponse(
            _stream(engine, prompt, params, rid), media_type="text/event-stream"
        )

    results_generator = engine.generate(
        prompt,
        params,
        rid,
    )

    final_output = None

    async for output in results_generator:
        final_output = output

    if final_output is None:
        raise HTTPException(status_code=500, detail="No output from engine")
    completion = final_output.outputs[0]
    text = completion.text
    return ChatResponse(
        id=rid,
        created=int(time.time()),
        model=req.model,
        choices=[Choice(message=Message(role="assistant", content=text), finish_reason="stop")],
        usage=Usage(
        prompt_tokens=len(final_output.prompt_token_ids),
        completion_tokens=len(completion.token_ids),
        total_tokens=(
            len(final_output.prompt_token_ids)
            + len(completion.token_ids)
        ),
    ),
    )

async def _stream(engine, prompt: str, params, rid: str) -> AsyncIterator[str]:
    created = int(time.time())

    async for output in engine.generate(prompt=prompt, sampling_params=params, request_id=rid):
        text = output.outputs[0].text
        if text:
            chunk = StreamChunk(
                id=rid,
                created=created,
                model=settings.model,
                choices=[StreamChoice(delta=DeltaMessage(content=text))],
            )
            yield f"data: {chunk.model_dump_json()}\n\n"

        if output.finished:
            break

    chunk = StreamChunk(
        id=rid,
        created=created,
        model=settings.model,
        choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
    )
    yield f"data: {chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"
