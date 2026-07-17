import httpx

import authenticated_httpx
from authenticated_httpx import create_authenticated_client


def test_create_authenticated_client_is_importable() -> None:
    client = create_authenticated_client("https://agent.example.com")

    assert client.follow_redirects is True
    assert client.timeout.connect == 600.0


def test_localhost_client_does_not_require_gcloud(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("gcloud must not be called for local services")

    monkeypatch.setattr(authenticated_httpx.subprocess, "check_output", fail_if_called)
    client = create_authenticated_client("http://localhost:8004")

    request = next(client._auth.auth_flow(httpx.Request("POST", "http://localhost:8004")))

    assert "Authorization" not in request.headers
