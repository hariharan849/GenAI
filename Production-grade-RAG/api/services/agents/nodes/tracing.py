import logging
import time
from contextlib import nullcontext
from typing import Any, Dict, Optional

from api.services.langfuse.client import FallbackPrompt

logger = logging.getLogger(__name__)


def create_node_span(runtime, name: str, input_data: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None):
    """Create a Langfuse span for a node, returning None when tracing is unavailable."""
    tracer = getattr(runtime.context, "langfuse_tracer", None)
    trace = getattr(runtime.context, "trace", None)
    if not tracer or not getattr(runtime.context, "langfuse_enabled", False) or trace is None:
        return None

    try:
        return tracer.create_span(trace=trace, name=name, input_data=input_data, metadata=metadata or {})
    except Exception as exc:
        logger.warning(f"Failed to create span for {name}: {exc}")
        return None


def fetch_prompt(runtime, prompt_name: str, fallback_template: str):
    """Fetch a versioned prompt or fall back to a hardcoded template."""
    tracer = getattr(runtime.context, "langfuse_tracer", None)
    if tracer:
        return tracer.fetch_prompt(prompt_name, fallback_template=fallback_template)
    return FallbackPrompt(fallback_template)


def start_generation(runtime, name: str, model: str, input_data: Any, prompt: Any = None):
    """Create a Langfuse generation context or a no-op context when disabled."""
    tracer = getattr(runtime.context, "langfuse_tracer", None)
    if tracer:
        return tracer.start_generation(name=name, model=model, input_data=input_data, prompt=prompt)
    return nullcontext(None)


def finish_node_span(
    runtime,
    span,
    start_time: float,
    *,
    output: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    level: Optional[str] = None,
    status_message: Optional[str] = None,
):
    """Attach final node data and end the span if tracing is active."""
    if not span:
        return

    tracer = getattr(runtime.context, "langfuse_tracer", None)
    if not tracer:
        return

    span_metadata = dict(metadata or {})
    span_metadata["execution_time_ms"] = round((time.time() - start_time) * 1000, 2)
    tracer.end_span(
        span,
        output=output,
        metadata=span_metadata,
        level=level,
        status_message=status_message,
    )
