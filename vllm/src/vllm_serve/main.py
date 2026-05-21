from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from src.vllm_serve.api.health import router as health_router
from src.vllm_serve.api.chat import router as chat_router
from src.vllm_serve.config import settings
from src.vllm_serve.engine import init_engine, shutdown_engine


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("vllm_serve")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Loading model: %s", settings.model)
    await init_engine()
    logger.info("Engine ready")
    yield
    logger.info("Shutting down")
    shutdown_engine()


app = FastAPI(title="vllm-serve", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])  # TODO: tighten this in production
app.include_router(health_router)
app.include_router(chat_router)


def cli():
    import uvicorn
    from src.vllm_serve.config import Settings
    settings = Settings()
    uvicorn.run(
        "vllm_serve.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    cli()
