import subprocess
from urllib.parse import urlparse

import httpx
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google.oauth2.id_token import fetch_id_token_credentials

DEFAULT_TIMEOUT = 600.0


def create_authenticated_client(
    remote_service_url: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.AsyncClient:
    """Create an httpx client authenticated with a Google identity token."""

    class _IdentityTokenAuth(httpx.Auth):
        def __init__(self, remote_service_url: str):
            parsed_url = urlparse(remote_service_url)
            self.root_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            self.is_local = parsed_url.hostname in {"localhost", "127.0.0.1", "::1"}
            self.session = None

        def auth_flow(self, request):
            if self.is_local:
                yield request
                return

            if self.session:
                id_token = self.session.credentials.token
            else:
                id_token = None
                try:
                    credentials = fetch_id_token_credentials(audience=self.root_url)
                    credentials.refresh(Request())
                    self.session = AuthorizedSession(credentials)
                    id_token = self.session.credentials.token
                except DefaultCredentialsError:
                    self.outside_cloud = True

                if not id_token:
                    try:
                        id_token = subprocess.check_output(
                            ["gcloud", "auth", "print-identity-token", "-q"]
                        ).decode().strip()
                        if id_token:
                            refresh_token = subprocess.check_output(
                                ["gcloud", "auth", "print-refresh-token", "-q"]
                            ).decode().strip()
                            credentials = Credentials(
                                token=id_token,
                                id_token=id_token,
                                refresh_token=refresh_token,
                            )
                            self.session = AuthorizedSession(credentials)
                    except (OSError, subprocess.SubprocessError):
                        print("ERROR: Unable to fetch identity token.")

            if id_token:
                request.headers["Authorization"] = f"Bearer {id_token}"
            yield request

    return httpx.AsyncClient(
        auth=_IdentityTokenAuth(remote_service_url),
        follow_redirects=True,
        timeout=timeout,
    )
