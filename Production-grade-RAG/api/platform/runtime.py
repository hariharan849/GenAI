"""Runtime process configuration that must happen before the app is built."""

import asyncio
import os
import sys


def configure_event_loop_policy() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def configure_prometheus_registry() -> None:
    if os.getenv("API_WORKERS", "1") == "1":
        os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
        os.environ.pop("prometheus_multiproc_dir", None)
