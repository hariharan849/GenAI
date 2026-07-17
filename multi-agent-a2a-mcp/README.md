# Course Creation Agent

A distributed, learner-adaptive course-creation system. Independent agent
services research a topic, assess the evidence, propose a learning path for
learner approval, and generate the final course content.

Services communicate through the Agent-to-Agent (A2A) protocol. The specialist
agents share a Source Intelligence service over the Model Context Protocol
(MCP), keeping web access separate from the course-workflow handoffs.

## Architecture

```text
Browser
  |
  v
FastAPI web app (port 8000)
  |
  v
Orchestrator / LangGraph workflow (port 8004)
  |-- A2A --> Researcher (port 8001) ----\
  |-- A2A --> Judge (port 8002) ----------+--> Source Intelligence MCP
  '-- A2A --> Content Builder (port 8003) /    (stdio locally, HTTP on Cloud Run)
```

The orchestrator retries research when the judge rejects it, pauses for learner
approval of the proposed learning path, then asks the content builder to create
the course.

## Services

The `agents/` directory currently contains five services:

| Service | Directory | Responsibility |
| --- | --- | --- |
| Orchestrator | `agents/orchestrator/` | Runs the learner-approval workflow and calls specialist services through A2A. |
| Researcher | `agents/researcher/` | Uses a LangGraph workflow and OpenAI model to produce grounded research. |
| Judge | `agents/judge/` | Uses CrewAI to evaluate research and validate citation-related evidence. |
| Content Builder | `agents/content_builder/` | Uses Amazon Bedrock to generate the final Markdown course from approved research. |
| Source Intelligence | `agents/source_intelligence/` | MCP server for web search, public-page retrieval, and citation verification. |

`app/` is the browser-facing FastAPI application. `shared/` holds reusable A2A,
HTTP, ADK, and learning-contract helpers.

## Frameworks and services

| Technology | Used for |
| --- | --- |
| Python 3.10+ and uv | Runtime and dependency management. |
| FastAPI and Uvicorn | HTTP APIs for the web app and A2A services. |
| A2A SDK | Agent cards, agent discovery, task messaging, and service-to-service handoffs. |
| LangGraph | Stateful orchestration, research workflow, retries, and learner approval interrupts. |
| CrewAI | Research-quality assessment in the judge service. |
| LangChain OpenAI | OpenAI chat-model integration in the researcher. |
| Amazon Bedrock and Boto3 | Course-content generation in the content-builder service. |
| MCP / FastMCP | Shared, least-privilege live-source tools. |
| Tavily | Web-source discovery for the Source Intelligence service. |
| Pydantic | Validated contracts and structured agent data. |
| Google ADK | Included for the ADK-based remote-A2A composition example and shared helpers. |
| Google Cloud Run / IAM | Container deployment and authenticated access to the deployed MCP service. |

## Requirements

- Python 3.10-3.13 and [uv](https://docs.astral.sh/uv/)
- Bash/WSL on Windows to run `run_local.sh`
- Credentials for the providers you intend to use:
  - `OPENAI_API_KEY` for the researcher and CrewAI judge
  - AWS credentials, `AWS_REGION`, and optionally `BEDROCK_MODEL_ID` for the content builder
  - `TAVILY_API_KEY` when using live web search
- Google Cloud SDK; `run_local.sh` reads the active Google Cloud project, and
  Cloud Run deployment also requires application-default credentials

## Quick start

1. Install all project dependencies:

   ```bash
   uv sync --all-groups --all-extras
   ```

2. Configure the required local environment variables. For example:

   ```bash
   export OPENAI_API_KEY="..."
   export TAVILY_API_KEY="..."
   export AWS_REGION="us-east-1"
   # Configure AWS credentials through the normal AWS credential provider chain.
   ```

3. Start the application from Bash or WSL:

   ```bash
   ./run_local.sh
   ```

   This starts the researcher, judge, content builder, orchestrator, and web
   app. Each specialist launches its own stdio-connected Source Intelligence
   MCP process for local development.

4. Open <http://localhost:8000>.

## Development and verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

To start only the web application:

```bash
cd app
uv run uvicorn main:app --reload --port 8000
```

To run Source Intelligence independently over HTTP:

```bash
cd agents/source_intelligence
PORT=8005 uv run python main.py
```

Its MCP endpoint is then available at `http://localhost:8005/mcp`.

## Deployment

`deploy.sh` deploys the five agent services and the web app to Google Cloud
Run. The deployed Source Intelligence endpoint is IAM-protected; the
researcher, judge, and content-builder service identities are granted the
Cloud Run Invoker role. Review the provider credentials and environment
variables in `deploy.sh` before deploying, and do not commit secrets or `.env`
files.

## Additional documentation

- [Source Intelligence service](agents/source_intelligence/README.md)
- [Architecture decisions](docs/adr/)
- [Project context](CONTEXT.md)
