from contextlib import contextmanager
from types import SimpleNamespace

from api.services.agents.nodes.tracing import create_node_span, fetch_prompt, finish_node_span, start_generation


class FakePrompt:
    is_fallback = False

    def __init__(self, template: str):
        self.template = template

    def compile(self, **kwargs):
        return self.template.format(**kwargs)


class FakeTracer:
    def __init__(self):
        self.created_spans = []
        self.prompt_requests = []
        self.generation_requests = []
        self.ended_spans = []

    def create_span(self, *, trace, name, input_data=None, metadata=None):
        span = SimpleNamespace(name=name, input_data=input_data, metadata=metadata, trace=trace, ended=False)
        self.created_spans.append(span)
        return span

    def fetch_prompt(self, name, fallback_template):
        self.prompt_requests.append((name, fallback_template))
        return FakePrompt(fallback_template)

    @contextmanager
    def start_generation(self, **kwargs):
        self.generation_requests.append(kwargs)
        generation = SimpleNamespace(update=lambda **_: None)
        yield generation

    def end_span(self, span, **kwargs):
        span.ended = True
        self.ended_spans.append((span, kwargs))


def runtime(*, tracer=None, trace=None, enabled=False):
    return SimpleNamespace(
        context=SimpleNamespace(
            langfuse_tracer=tracer,
            trace=trace,
            langfuse_enabled=enabled,
        )
    )


def test_create_node_span_returns_none_when_disabled():
    assert create_node_span(runtime(), "demo") is None


def test_create_node_span_creates_span_when_enabled():
    tracer = FakeTracer()
    fake_trace = object()

    span = create_node_span(runtime(tracer=tracer, trace=fake_trace, enabled=True), "demo", {"q": "x"})

    assert span is not None
    assert span.name == "demo"
    assert tracer.created_spans[0].input_data == {"q": "x"}


def test_fetch_prompt_falls_back_without_tracer():
    prompt = fetch_prompt(runtime(), "demo", "Hello {name}")

    assert prompt.compile(name="world") == "Hello world"
    assert getattr(prompt, "is_fallback", False) is True


def test_finish_node_span_adds_execution_time_and_ends_span():
    tracer = FakeTracer()
    fake_runtime = runtime(tracer=tracer, trace=object(), enabled=True)
    span = tracer.create_span(trace=fake_runtime.context.trace, name="demo")

    finish_node_span(fake_runtime, span, start_time=10.0, output={"ok": True}, metadata={"node": "demo"})

    assert tracer.ended_spans
    ended_span, payload = tracer.ended_spans[0]
    assert ended_span is span
    assert payload["output"] == {"ok": True}
    assert payload["metadata"]["node"] == "demo"
    assert payload["metadata"]["execution_time_ms"] > 0


def test_start_generation_returns_noop_context_without_tracer():
    ctx = start_generation(runtime(), "demo", model="m", input_data="x")
    with ctx as generation:
        assert generation is None
