"""FastAPI UI server for the mid software engineer DeepAgent."""

from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .agent import DEFAULT_GSTACK_SKILLS, create_local_development_agent
from .tracing import DEFAULT_TRACE_DB, AgentTraceStore


load_dotenv()


class AgentMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str = "default"


class AgentMessageResponse(BaseModel):
    thread_id: str
    content: str
    interrupted: bool = False
    raw: dict[str, Any] | None = None


def create_app(
    *,
    model: str = "openai:gpt-5.4",
    backend_root: str | Path = ".",
    construct_agent: bool = True,
    trace_store: AgentTraceStore | None = None,
    trace_db_path: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Mid Software Engineer Agent UI")
    agent: Any | None = None
    store = trace_store or AgentTraceStore(trace_db_path or os.getenv("MID_SE_TRACE_DB", DEFAULT_TRACE_DB))

    if construct_agent:
        agent = create_local_development_agent(
            model=model,
            backend_root=backend_root,
            trace_store=store,
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return render_index(model=model)

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return {
            "model": model,
            "skills": list(DEFAULT_GSTACK_SKILLS),
            "middleware": ["CodeInterpreterMiddleware", "HumanInTheLoopMiddleware via interrupt_on"],
            "chatkit_api_url": "/chatkit",
            "local_agent_endpoint": "/api/agent/message",
            "trace_db_path": store.db_path,
            "traces_endpoint": "/api/traces",
        }

    @app.get("/api/traces")
    def traces(limit: int = 50) -> dict[str, Any]:
        return {"traces": store.recent(limit)}

    @app.post("/api/agent/message", response_model=AgentMessageResponse)
    def send_message(payload: AgentMessageRequest) -> AgentMessageResponse:
        if agent is None:
            return AgentMessageResponse(
                thread_id=payload.thread_id,
                content="Agent construction is disabled for this test server.",
            )

        result = agent.invoke(
            {"messages": [{"role": "user", "content": payload.message}]},
            config={
                "configurable": {"thread_id": payload.thread_id},
                "tags": ["mid-software-engineer", "local-ui"],
                "metadata": {
                    "thread_id": payload.thread_id,
                    "model": model,
                    "skills": list(DEFAULT_GSTACK_SKILLS),
                    "trace_db_path": store.db_path,
                },
            },
        )
        return response_from_agent_result(payload.thread_id, result)

    @app.post("/chatkit")
    async def chatkit_endpoint() -> None:
        raise HTTPException(
            status_code=501,
            detail=(
                "ChatKit custom server protocol endpoint reserved. "
                "Use /api/agent/message for the local DeepAgent bridge in this MVP."
            ),
        )

    return app


def response_from_agent_result(thread_id: str, result: Any) -> AgentMessageResponse:
    if isinstance(result, dict) and "__interrupt__" in result:
        return AgentMessageResponse(
            thread_id=thread_id,
            content="The agent needs human approval before continuing.",
            interrupted=True,
            raw=result,
        )

    content = extract_last_message_content(result)
    return AgentMessageResponse(thread_id=thread_id, content=content, raw=result if isinstance(result, dict) else None)


def extract_last_message_content(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)

    messages = result.get("messages")
    if not messages:
        return str(result)

    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content")
    if isinstance(content, list):
        return format_content_blocks(content)
    return str(content)


def format_content_blocks(blocks: list[Any]) -> str:
    """Render LLM content blocks as user-facing text.

    DeepAgents can return OpenAI/LangChain content blocks as dictionaries. The UI
    should show the block text, not Python's dict representation. If both
    commentary and final-answer phases repeat the same text, keep one copy.
    """

    final_texts: list[str] = []
    fallback_texts: list[str] = []
    seen: set[str] = set()

    for block in blocks:
        text = extract_block_text(block)
        if not text or text in seen:
            continue
        seen.add(text)

        phase = block.get("phase") if isinstance(block, dict) else None
        if phase == "final_answer":
            final_texts.append(text)
        else:
            fallback_texts.append(text)

    selected = final_texts or fallback_texts
    return "\n\n".join(selected) if selected else "\n".join(str(block) for block in blocks)


def extract_block_text(block: Any) -> str:
    if isinstance(block, dict):
        text = block.get("text")
        if isinstance(text, str):
            return text
        if text is not None:
            return str(text)
        content = block.get("content")
        if isinstance(content, str):
            return content
        if content is not None:
            return str(content)
        return ""

    text = getattr(block, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(block, "content", None)
    if isinstance(content, str):
        return content
    return str(block)


def render_index(*, model: str) -> str:
    thread_id = f"ui-{uuid.uuid4().hex[:8]}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Mid Software Engineer Agent</title>
  <script src="https://cdn.platform.openai.com/deployments/chatkit/chatkit.js" async></script>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f7f4;
      color: #1e293b;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
    }}
    main {{
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(360px, 1fr);
      min-height: 100vh;
    }}
    aside {{
      border-right: 1px solid #d8ddd5;
      background: #ffffff;
      padding: 24px;
    }}
    section {{
      padding: 24px;
      display: grid;
      grid-template-rows: auto 1fr;
      gap: 16px;
    }}
    h1 {{
      font-size: 24px;
      line-height: 1.2;
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 15px;
      margin: 22px 0 8px;
      letter-spacing: 0;
    }}
    p, li {{
      font-size: 14px;
      line-height: 1.5;
    }}
    ul {{
      padding-left: 18px;
    }}
    code {{
      background: #eef2f0;
      border-radius: 4px;
      padding: 2px 5px;
    }}
    .panel {{
      border: 1px solid #d8ddd5;
      border-radius: 8px;
      background: #ffffff;
      overflow: hidden;
      min-height: 520px;
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      border-bottom: 1px solid #d8ddd5;
      padding: 12px 14px;
    }}
    .fallback {{
      display: grid;
      grid-template-rows: 1fr auto;
      min-height: 520px;
    }}
    #messages {{
      padding: 16px;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .msg {{
      max-width: 780px;
      border-radius: 8px;
      padding: 10px 12px;
      line-height: 1.5;
      font-size: 14px;
    }}
    .user {{
      align-self: flex-end;
      background: #1f6f68;
      color: #fff;
    }}
    .assistant {{
      align-self: flex-start;
      background: #eef2f0;
    }}
    .assistant.rich {{
      width: min(920px, 100%);
      max-width: 920px;
      background: transparent;
      padding: 0;
    }}
    .response-stack {{
      display: grid;
      gap: 10px;
    }}
    .response-summary {{
      border: 1px solid #bdd6d1;
      border-left: 4px solid #1f6f68;
      border-radius: 8px;
      background: #f4fbf9;
      padding: 12px 14px;
      font-weight: 600;
    }}
    .section-card {{
      border: 1px solid #d8ddd5;
      border-radius: 8px;
      background: #ffffff;
      overflow: hidden;
    }}
    .section-card header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      border-bottom: 1px solid #e5e9e3;
      padding: 10px 12px;
      background: #fbfcfa;
    }}
    .section-card h3 {{
      margin: 0;
      font-size: 14px;
      letter-spacing: 0;
    }}
    .section-kind {{
      border-radius: 999px;
      background: #e6f0ed;
      color: #1f4f4a;
      font-size: 12px;
      padding: 3px 8px;
      white-space: nowrap;
    }}
    .section-body {{
      padding: 12px;
    }}
    .section-body p {{
      margin: 0 0 8px;
    }}
    .section-body ul, .section-body ol {{
      margin: 6px 0 10px;
      padding-left: 22px;
    }}
    .section-body li {{
      margin: 4px 0;
    }}
    .code-card {{
      border: 1px solid #cbd5cf;
      border-radius: 8px;
      overflow: hidden;
      background: #0f172a;
      color: #e2e8f0;
      margin: 10px 0;
    }}
    .code-card header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 8px 10px;
      background: #182235;
      border-bottom: 1px solid #263248;
      font-size: 12px;
    }}
    .code-card pre {{
      margin: 0;
      padding: 12px;
      overflow: auto;
      white-space: pre;
      font-size: 13px;
      line-height: 1.45;
    }}
    .copy-btn, .action-chip {{
      border: 1px solid #b9c8c2;
      border-radius: 999px;
      background: #ffffff;
      color: #1e293b;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }}
    .code-card .copy-btn {{
      border-color: #3a4961;
      background: #22304a;
      color: #e2e8f0;
      padding: 4px 8px;
    }}
    .action-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .plain-line {{
      white-space: pre-wrap;
    }}
    form {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      border-top: 1px solid #d8ddd5;
      padding: 12px;
    }}
    textarea {{
      resize: vertical;
      min-height: 44px;
      max-height: 160px;
      border: 1px solid #cbd5cf;
      border-radius: 8px;
      padding: 10px;
      font: inherit;
    }}
    button {{
      border: 0;
      border-radius: 8px;
      background: #1f6f68;
      color: white;
      padding: 0 18px;
      font-weight: 600;
    }}
    chatkit-widget {{
      display: block;
      width: 100%;
      min-height: 520px;
    }}
    @media (max-width: 860px) {{
      main {{
        grid-template-columns: 1fr;
      }}
      aside {{
        border-right: 0;
        border-bottom: 1px solid #d8ddd5;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <aside>
      <h1>Mid Software Engineer Agent</h1>
      <p>Model: <code>{model}</code></p>
      <h2>Flow</h2>
      <ul>
        <li>Requirement intake</li>
        <li>Design approval gate</li>
        <li>Implementation with tests</li>
        <li>Demo and ship readiness</li>
      </ul>
      <h2>Middleware</h2>
      <ul>
        <li><code>CodeInterpreterMiddleware</code></li>
        <li><code>interrupt_on</code> for write/edit approval</li>
      </ul>
      <h2>ChatKit</h2>
      <p>The page loads ChatKit's web script and reserves <code>/chatkit</code> for the custom protocol. The local fallback below talks directly to DeepAgents.</p>
    </aside>
    <section>
      <div class="toolbar">
        <strong>Agent Console</strong>
        <code id="thread">{thread_id}</code>
      </div>
      <div class="panel">
        <chatkit-widget id="chatkit" api-url="/chatkit"></chatkit-widget>
        <div class="fallback" id="fallback">
          <div id="messages">
            <div class="msg assistant rich">
              <div class="response-stack">
                <div class="response-summary">Describe a product-owner requirement. The agent will ask for missing details, propose a design gate, and pause before risky file changes.</div>
              </div>
            </div>
          </div>
          <form id="agent-form">
            <textarea id="message" placeholder="Create a requirement intake UI for the agent..." required></textarea>
            <button type="submit">Send</button>
          </form>
        </div>
      </div>
    </section>
  </main>
  <script>
    const form = document.getElementById("agent-form");
    const input = document.getElementById("message");
    const messages = document.getElementById("messages");
    const threadId = document.getElementById("thread").textContent;

    function addMessage(role, content) {{
      const node = document.createElement("div");
      node.className = `msg ${{role}}`;
      node.textContent = content;
      messages.appendChild(node);
      messages.scrollTop = messages.scrollHeight;
      return node;
    }}

    function addAssistantMessage(content) {{
      const node = document.createElement("div");
      node.className = "msg assistant rich";
      node.appendChild(renderAgentResponse(content));
      messages.appendChild(node);
      messages.scrollTop = messages.scrollHeight;
      return node;
    }}

    function escapeHtml(value) {{
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function sectionKind(title) {{
      const normalized = title.toLowerCase();
      if (normalized.includes("requirement")) return "intake";
      if (normalized.includes("design")) return "design";
      if (normalized.includes("test")) return "verification";
      if (normalized.includes("demo") || normalized.includes("run")) return "demo";
      if (normalized.includes("risk")) return "risk";
      if (normalized.includes("ship") || normalized.includes("next")) return "ship";
      return "note";
    }}

    function normalizeTitle(line) {{
      return line.replace(/^[-#*\\s]+/, "").replace(/:$/, "").trim();
    }}

    function isSectionHeading(line) {{
      const clean = normalizeTitle(line).toLowerCase();
      return [
        "requirement intake",
        "concise design proposal",
        "design proposal for modularization",
        "test strategy",
        "demo path",
        "risks",
        "changed files",
        "unresolved risks",
        "next good step",
        "ship readiness",
        "run",
        "test",
        "demo",
      ].some((heading) => clean === heading || clean.startsWith(`${{heading}} `));
    }}

    function splitResponse(content) {{
      const lines = content.split("\\n");
      const sections = [];
      let current = {{ title: "Response", lines: [] }};
      let inCode = false;

      for (const line of lines) {{
        if (line.trim().startsWith("```")) {{
          inCode = !inCode;
          current.lines.push(line);
          continue;
        }}
        if (!inCode && line.trim().endsWith(":") && isSectionHeading(line)) {{
          if (current.lines.join("\\n").trim()) sections.push(current);
          current = {{ title: normalizeTitle(line), lines: [] }};
          continue;
        }}
        current.lines.push(line);
      }}

      if (current.lines.join("\\n").trim()) sections.push(current);
      return sections;
    }}

    function renderInlineMarkdown(text) {{
      const escaped = escapeHtml(text);
      return escaped
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>");
    }}

    function renderBody(text) {{
      const fragment = document.createDocumentFragment();
      const parts = text.split(/```([a-zA-Z0-9_+-]*)\\n([\\s\\S]*?)```/g);

      for (let i = 0; i < parts.length; i += 3) {{
        const prose = parts[i] || "";
        appendProse(fragment, prose);

        const lang = parts[i + 1];
        const code = parts[i + 2];
        if (code !== undefined) {{
          fragment.appendChild(renderCodeBlock(lang || "text", code));
        }}
      }}

      return fragment;
    }}

    function appendProse(parent, prose) {{
      const lines = prose.split("\\n");
      let list = null;
      let ordered = false;

      function closeList() {{
        if (list) {{
          parent.appendChild(list);
          list = null;
          ordered = false;
        }}
      }}

      for (const rawLine of lines) {{
        const line = rawLine.trim();
        if (!line) {{
          closeList();
          continue;
        }}

        const bullet = line.match(/^[-*]\\s+(.*)$/);
        const numbered = line.match(/^\\d+\\.\\s+(.*)$/);
        if (bullet || numbered) {{
          const shouldOrder = Boolean(numbered);
          if (!list || ordered !== shouldOrder) {{
            closeList();
            list = document.createElement(shouldOrder ? "ol" : "ul");
            ordered = shouldOrder;
          }}
          const item = document.createElement("li");
          item.innerHTML = renderInlineMarkdown((bullet || numbered)[1]);
          list.appendChild(item);
          continue;
        }}

        closeList();
        const paragraph = document.createElement("p");
        paragraph.className = "plain-line";
        paragraph.innerHTML = renderInlineMarkdown(line);
        parent.appendChild(paragraph);
      }}
      closeList();
    }}

    function renderCodeBlock(lang, code) {{
      const card = document.createElement("div");
      card.className = "code-card";

      const header = document.createElement("header");
      const label = document.createElement("span");
      label.textContent = lang || "text";
      const copy = document.createElement("button");
      copy.className = "copy-btn";
      copy.type = "button";
      copy.textContent = "Copy";
      copy.addEventListener("click", async () => {{
        await navigator.clipboard.writeText(code.trim());
        copy.textContent = "Copied";
        setTimeout(() => (copy.textContent = "Copy"), 1200);
      }});
      header.append(label, copy);

      const pre = document.createElement("pre");
      const codeNode = document.createElement("code");
      codeNode.textContent = code.trim();
      pre.appendChild(codeNode);

      card.append(header, pre);
      return card;
    }}

    function inferSummary(sections) {{
      const first = sections.find((section) => section.title !== "Response") || sections[0];
      if (!first) return "Agent response";
      const joined = first.lines.join(" ").replace(/\\s+/g, " ").trim();
      return joined.length > 180 ? `${{joined.slice(0, 177)}}...` : joined || first.title;
    }}

    function inferActions(content) {{
      const lower = content.toLowerCase();
      const actions = [];
      if (lower.includes("proceed") || lower.includes("approval")) actions.push("proceed");
      if (lower.includes("modular")) actions.push("modularize");
      if (lower.includes("test")) actions.push("add tests");
      if (lower.includes("env") || lower.includes("api key")) actions.push("add .env support");
      if (lower.includes("ollama")) actions.push("use ollama");
      return [...new Set(actions)].slice(0, 5);
    }}

    function renderAgentResponse(content) {{
      const stack = document.createElement("div");
      stack.className = "response-stack";
      const sections = splitResponse(content);

      const summary = document.createElement("div");
      summary.className = "response-summary";
      summary.textContent = inferSummary(sections);
      stack.appendChild(summary);

      for (const section of sections) {{
        const bodyText = section.lines.join("\\n").trim();
        if (!bodyText) continue;

        const card = document.createElement("article");
        card.className = "section-card";
        const header = document.createElement("header");
        const title = document.createElement("h3");
        title.textContent = section.title;
        const kind = document.createElement("span");
        kind.className = "section-kind";
        kind.textContent = sectionKind(section.title);
        header.append(title, kind);

        const body = document.createElement("div");
        body.className = "section-body";
        body.appendChild(renderBody(bodyText));

        card.append(header, body);
        stack.appendChild(card);
      }}

      const actions = inferActions(content);
      if (actions.length) {{
        const row = document.createElement("div");
        row.className = "action-row";
        for (const action of actions) {{
          const button = document.createElement("button");
          button.type = "button";
          button.className = "action-chip";
          button.textContent = action;
          button.addEventListener("click", () => {{
            input.value = action;
            input.focus();
          }});
          row.appendChild(button);
        }}
        stack.appendChild(row);
      }}

      return stack;
    }}

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const message = input.value.trim();
      if (!message) return;
      input.value = "";
      addMessage("user", message);
      const pending = addAssistantMessage("Working...");

      try {{
        const response = await fetch("/api/agent/message", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ message, thread_id: threadId }}),
        }});
        const payload = await response.json();
        const rendered = renderAgentResponse(
          payload.interrupted
            ? `${{payload.content}}\\n\\nOpen the server logs or approval handler to resume this interrupted action.`
            : payload.content
        );
        pending.replaceChildren(rendered);
      }} catch (error) {{
        pending.replaceChildren(renderAgentResponse(`Request failed: ${{error}}`));
      }}
    }});
  </script>
</body>
</html>"""


def should_construct_agent(model: str) -> bool:
    if os.getenv("MID_SE_AGENT_SKIP_CONSTRUCT", "").lower() in {"1", "true", "yes"}:
        return False
    if model.startswith("openai:"):
        return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY"))
    return True


_DEFAULT_MODEL = os.getenv("MID_SE_AGENT_MODEL", "openai:gpt-5.4")
app = create_app(
    model=_DEFAULT_MODEL,
    backend_root=os.getenv("MID_SE_AGENT_BACKEND_ROOT", "."),
    construct_agent=should_construct_agent(_DEFAULT_MODEL),
    trace_db_path=os.getenv("MID_SE_TRACE_DB", DEFAULT_TRACE_DB),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local ChatKit-oriented agent UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", default=os.getenv("MID_SE_AGENT_MODEL", "openai:gpt-5.4"))
    args = parser.parse_args()

    runtime_app = create_app(
        model=args.model,
        backend_root=os.getenv("MID_SE_AGENT_BACKEND_ROOT", "."),
        construct_agent=should_construct_agent(args.model),
        trace_db_path=os.getenv("MID_SE_TRACE_DB", DEFAULT_TRACE_DB),
    )

    import uvicorn

    uvicorn.run(runtime_app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
