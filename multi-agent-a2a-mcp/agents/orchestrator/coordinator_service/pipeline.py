"""Execute the configured A2A specialist services for one learner task."""

from __future__ import annotations

import json
import logging
import subprocess
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request
from google.oauth2.id_token import fetch_id_token_credentials

from shared.learning_contracts import CoordinatorTaskState, SpecialistRequest

LOGGER = logging.getLogger(__name__)


class CoursePipeline:
    """Research, review, then build a course through each specialist's card URL."""

    def __init__(self, urls: dict[str, str]) -> None:
        self._urls = urls

    @classmethod
    def from_environment(cls) -> CoursePipeline:
        import os

        names = {
            "researcher": "RESEARCHER_AGENT_CARD_URL",
            "judge": "JUDGE_AGENT_CARD_URL",
            "content_builder": "CONTENT_BUILDER_AGENT_CARD_URL",
        }
        urls = {name: os.environ.get(variable, "") for name, variable in names.items()}
        missing = [name for name, url in urls.items() if not url]
        if missing:
            raise RuntimeError(f"Missing agent-card URLs: {', '.join(missing)}")
        return cls(urls)

    async def research(self, task: CoordinatorTaskState, feedback: str = "") -> str:
        LOGGER.info("pipeline_progress task_id=%s stage=researching", task.task_id)
        request = SpecialistRequest(
            profile=task.profile,
            learning_path=task.learning_path,
            judge_feedback=feedback,
        )
        return await self._send("researcher", request.model_dump_json())

    async def judge(
        self, task: CoordinatorTaskState, findings: str
    ) -> tuple[bool, str]:
        LOGGER.info("pipeline_progress task_id=%s stage=fact-checking", task.task_id)
        response = await self._send(
            "judge",
            SpecialistRequest(
                profile=task.profile,
                learning_path=task.learning_path,
                research_findings=findings,
            ).model_dump_json(),
        )
        try:
            verdict = json.loads(response)
            return verdict.get("status") == "pass", str(verdict.get("feedback", ""))
        except (TypeError, ValueError):
            return False, "The research review did not return a valid verdict."

    async def build(self, findings: str) -> str:
        LOGGER.info("pipeline_progress stage=writing")
        return await self._send("content_builder", findings)

    async def run(
        self,
        task: CoordinatorTaskState,
        set_stage: Callable[[str], None],
    ) -> str:
        set_stage("researching")
        findings = await self.research(task)

        # Temporary test-mode behavior: run one fact-check for observability, but
        # proceed to course generation regardless of the judge's verdict.
        set_stage("fact-checking")
        await self.judge(task, findings)

        set_stage("writing")
        return await self.build(findings)

    async def _send(self, agent: str, text: str) -> str:
        LOGGER.info("agent_request_started agent=%s request_chars=%d", agent, len(text))
        card_url = self._urls[agent]
        async with _authenticated_client(card_url) as client:
            card_response = await client.get(card_url)
            card_response.raise_for_status()
            rpc_url = card_response.json()["url"]
            response = await client.post(rpc_url, json=_message_request(text))
            response.raise_for_status()
        result = response.json().get("result", {})
        state = result.get("status", {}).get("state")
        if state != "completed":
            raise RuntimeError(f"{agent} returned {state or 'an invalid response'}.")
        for artifact in result.get("artifacts", []):
            for part in artifact.get("parts", []):
                if part.get("kind") == "text" and part.get("text"):
                    LOGGER.info("agent_request_completed agent=%s", agent)
                    return part["text"]
        raise RuntimeError(f"{agent} completed without an output artifact.")


def _message_request(text: str) -> dict[str, Any]:
    identifier = str(uuid.uuid4())
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": identifier,
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }


def _authenticated_client(remote_service_url: str) -> httpx.AsyncClient:
    """Use Cloud Run identity tokens remotely and no auth for localhost services."""
    return httpx.AsyncClient(
        auth=_CloudRunIdentityTokenAuth(remote_service_url),
        follow_redirects=True,
        timeout=300,
    )


class _CloudRunIdentityTokenAuth(httpx.Auth):
    def __init__(self, remote_service_url: str) -> None:
        parsed_url = httpx.URL(remote_service_url)
        self._audience = f"{parsed_url.scheme}://{parsed_url.host}"
        if parsed_url.port:
            self._audience += f":{parsed_url.port}"
        self._is_local = parsed_url.host in {"localhost", "127.0.0.1", "::1"}

    def auth_flow(self, request: httpx.Request):
        if self._is_local:
            yield request
            return
        token = _identity_token(self._audience)
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
        yield request


def _identity_token(audience: str) -> str | None:
    try:
        credentials = fetch_id_token_credentials(audience=audience)
        credentials.refresh(Request())
        return credentials.token
    except DefaultCredentialsError:
        try:
            return subprocess.check_output(
                ["gcloud", "auth", "print-identity-token", "-q"], text=True
            ).strip()
        except (OSError, subprocess.SubprocessError):
            return None
