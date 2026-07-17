# Generative AI Projects

A collection of independent experiments and reference implementations for building generative-AI applications, agent workflows, retrieval systems, and model-serving infrastructure. Each directory is a self-contained project with its own dependencies, configuration, and run instructions.

## Projects

| Project | What it contains | Start here |
| --- | --- | --- |
| [Blog2Podcast](Blog2Podcast/) | Four implementations of a blog-to-podcast application. Each converts a blog URL into a conversational script and ElevenLabs audio, with a Streamlit interface and Firecrawl/Groq integrations. The implementations explore AutoGen, CrewAI, Google ADK, and LangGraph-oriented approaches. | [LangGraph](Blog2Podcast/langgraph/README.md) · [CrewAI](Blog2Podcast/crew/README.md) · [AutoGen](Blog2Podcast/autogen/README.md) · [Google ADK](Blog2Podcast/google-adk/README.md) |
| [GitHub Assistant Agent](github_assistant_agent/README.md) | A CrewAI-powered assistant that locally indexes GitHub repositories, answers questions from retrieved repository context, and falls back to GitHub search when needed. Includes a CLI, Gradio UI, Docker setup, and tests. | [README](github_assistant_agent/README.md) |
| [Mid Software Engineer](mid_software_engineer/README.md) | A LangChain DeepAgents implementation of a mid-level software-engineering workflow: requirements shaping, design review, incremental implementation with tests, demonstration, and release preparation. Includes a ChatKit-oriented local UI and SQLite/LangSmith-compatible tracing. | [README](mid_software_engineer/README.md) |
| [Multi-Agent A2A + MCP Course Creator](multi-agent-a2a-mcp/README.md) | A distributed, learner-adaptive course-creation system. A LangGraph orchestrator coordinates A2A researcher, judge, and content-builder services; a shared MCP service provides source discovery and verification. | [README](multi-agent-a2a-mcp/README.md) |
| [Production-Grade RAG](Production-grade-RAG/README.md) | A Foundry Nuke documentation RAG platform with hybrid retrieval, a LangGraph agentic workflow, FastAPI API, Next.js chat UI, evaluation tooling, observability, and Airflow/Prefect/Dagster ingestion options. | [README](Production-grade-RAG/README.md) |
| [vLLM Serve](vllm/README.md) | A compact FastAPI service around vLLM that exposes an OpenAI-compatible streaming chat-completions endpoint for GPU-backed inference. | [README](vllm/README.md) |

## Getting started

Choose a project, open its README, and run its setup in that directory. Most Python projects use [uv](https://docs.astral.sh/uv/) and require Python 3.10+; the exact Python version, provider credentials, and optional infrastructure vary by project.

```powershell
cd <project-directory>
uv sync
```

Use the project's README rather than a shared command when starting services: several projects require provider keys, Docker, a GPU, or multiple local processes.

## Repository conventions

- Keep secrets in local environment files or environment variables; do not commit API keys or `.env` files.
- Treat project folders as independent environments. Their dependencies and ports can differ.
- Run each project's documented tests and static checks before making changes.

## Project map

```text
GenAI/
├── Blog2Podcast/             # Blog URL to script/audio implementations
├── github_assistant_agent/   # Repository-aware GitHub Q&A assistant
├── mid_software_engineer/    # DeepAgents software-engineering agent
├── multi-agent-a2a-mcp/      # A2A/MCP course-creation system
├── Production-grade-RAG/     # Production RAG system for Nuke documentation
└── vllm/                     # vLLM + FastAPI inference server
```
