"""Entrypoint for the native A2A coordinator."""

import logging
import os

import uvicorn
from coordinator_service import create_app

if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger(__name__).info("Starting coordinator service")
    uvicorn.run(
        create_app(),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8004")),
    )
