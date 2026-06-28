# UI — Next.js Frontend

React/Next.js chat interface for the Nuke RAG system. Supports two knowledge bases (Nuke docs, arXiv) and two chat providers (CopilotKit, OpenAI Responses API).

---

## Getting Started

```bash
cd ui
npm install
npm run dev      # http://localhost:3004
```

In production the UI is served via the Nginx reverse proxy at port 80.

---

## Directory Structure

```
ui/
├── app/
│   ├── page.tsx                      # Landing page — knowledge source + provider picker
│   ├── layout.tsx                    # Root layout with global styles
│   ├── globals.css
│   └── api/
│       ├── copilotkit/[[...slug]]/   # CopilotKit backend route (proxies to FastAPI)
│       └── openai-chat/route.ts      # OpenAI Responses API proxy with tool-calling loop
├── components/
│   ├── RAGCopilot.tsx                # CopilotKit sidebar — calls /ask-agentic
│   ├── AgentSteps.tsx                # Renders intermediate LangGraph node steps
│   ├── OpenAIChat.tsx                # OpenAI Responses API chat (Nuke KB only)
│   └── PaperCard.tsx                 # arXiv paper card component
├── lib/                              # Shared utilities
├── public/                           # Static assets
├── Dockerfile                        # Production image
├── next.config.ts
├── package.json
└── tsconfig.json
```

---

## Chat Providers

### CopilotKit

Uses `@copilotkit/react-ui` and `@copilotkit/react-core`. The sidebar sends questions to `/ask-agentic` via the CopilotKit backend route (`app/api/copilotkit/`). Intermediate agent steps are rendered in real time by `AgentSteps.tsx`.

### OpenAI Responses API

`OpenAIChat.tsx` calls the proxy route at `app/api/openai-chat/route.ts`, which runs an OpenAI tool-calling loop against the Nuke knowledge base. Only available when the Nuke knowledge source is selected.

---

## Knowledge Sources

| Source | Description |
|--------|-------------|
| Nuke | Foundry Nuke 17.0 reference documentation (default) |
| arXiv | Research paper knowledge base (experimental) |

---

## Environment Variables

Create `ui/.env.local` with:

```env
NEXT_PUBLIC_API_URL=http://localhost:8083
OPENAI_API_KEY=sk-...
COPILOTKIT_PUBLIC_API_KEY=...   # Optional — for CopilotKit cloud features
```

---

## Docker

```bash
# Build
docker compose build rag-ui

# Run (with API and infra already up)
docker compose up rag-ui
```

The UI container is placed behind Nginx which handles `/` (UI) and `/api/` (FastAPI) routing.
