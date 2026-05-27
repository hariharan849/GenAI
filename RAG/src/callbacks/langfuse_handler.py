import os

from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler

from src.config import settings


Langfuse(
    secret_key=settings.langfuse.secret_key,
    public_key=settings.langfuse.public_key,
    host=settings.langfuse.base_url,
    tracing_enabled=True,
    timeout=15
)

langfuse = get_client()
langfuse_handler = CallbackHandler()