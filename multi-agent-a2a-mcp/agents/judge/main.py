"""Entrypoint for the CrewAI judge A2A service."""

import logging
import os

import uvicorn
from judge_service import create_app

if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger(__name__).info("Starting judge service")
    uvicorn.run(
        create_app(),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8002")),
    )
