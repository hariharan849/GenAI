# LangGraph Researcher

The researcher is a stateless LangGraph workflow exposed through the A2A SDK and powered by OpenAI.
Its stable public interface is:

- `POST /a2a/agent` for A2A JSON-RPC requests and streaming requests.
- `GET /a2a/agent/.well-known/agent-card.json` for discovery.
- `GET /healthz` for liveness checks.

Set `OPENAI_API_KEY` in the repository `.env`; `OPENAI_MODEL` is optional and
defaults to `gpt-5.5`. For deployments, set `A2A_PUBLIC_URL` to
the public service URL, so the Agent Card does not advertise `localhost`.

Run locally from this directory:

```bash
uv sync --all-groups
uv run python main.py
```
