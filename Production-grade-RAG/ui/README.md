# UI - Next.js Frontend

React/Next.js chat interface for the Nuke RAG system. The UI is scoped to the Foundry Nuke 17.0 reference documentation and supports CopilotKit plus the OpenAI Responses API.

## Getting Started

```bash
cd ui
npm install
npm run dev      # http://localhost:3002
```

In Docker, the UI is exposed at `http://localhost:3004`.

## Directory Structure

```text
ui/
  app/
    page.tsx                      # Nuke assistant home page
    layout.tsx                    # Root layout with global styles
    globals.css
    api/
      copilotkit/[[...slug]]/     # CopilotKit backend route
      eval/[...path]/route.ts     # Eval console proxy to FastAPI
      openai-chat/route.ts        # OpenAI Responses API proxy with tool-calling loop
  components/
    RAGCopilot.tsx                # CopilotKit sidebar for Nuke docs
    AgentSteps.tsx                # Renders intermediate LangGraph node steps
    NukeResults.tsx               # Nuke documentation result cards
    OpenAIChat.tsx                # OpenAI Responses API chat
  lib/                            # Shared utilities
  public/                         # Static assets
  Dockerfile                      # Production image
  next.config.ts
  package.json
  tsconfig.json
```

## Chat Providers

### CopilotKit

Uses `@copilotkit/react-ui` and `@copilotkit/react-core`. The sidebar calls the FastAPI Nuke RAG endpoints through the CopilotKit backend route.

### OpenAI Responses API

`OpenAIChat.tsx` calls the proxy route at `app/api/openai-chat/route.ts`, which runs an OpenAI tool-calling loop against the Nuke knowledge base.

## Knowledge Source

The UI is scoped to the Foundry Nuke 17.0 reference documentation.

## Environment Variables

Create `ui/.env.local` with:

```env
OPENAI_API_KEY=sk-...
COPILOTKIT_PUBLIC_API_KEY=...   # Optional, for CopilotKit cloud features
```

## Docker

```bash
docker compose build ui
docker compose up -d api ui
```

The UI container is placed behind Nginx which handles `/` for the UI and `/api/` routing.
