from fastapi import FastAPI
from prometheus_client import generate_latest
from starlette.testclient import TestClient

from api.middlewares import MetricsMiddleware


def test_metrics_middleware_records_requests_latency_and_errors():
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/ok").status_code == 200
    assert client.get("/missing").status_code == 404
    assert client.get("/boom").status_code == 500

    metrics = generate_latest().decode("utf-8")

    assert 'app_requests_total{endpoint="/ok",method="GET",service="rag-api",status="200"}' in metrics
    assert 'app_requests_total{endpoint="/missing",method="GET",service="rag-api",status="404"}' in metrics
    assert 'app_requests_total{endpoint="/boom",method="GET",service="rag-api",status="500"}' in metrics
    assert 'app_errors_total{service="rag-api",type="warning"}' in metrics
    assert 'app_errors_total{service="rag-api",type="critical"}' in metrics
    assert 'app_request_duration_seconds_count{endpoint="/ok",method="GET",service="rag-api",status="200"}' in metrics
    assert "app_request_latency_seconds_count" in metrics
