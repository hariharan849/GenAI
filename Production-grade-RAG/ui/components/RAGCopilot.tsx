"use client";

import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useState } from "react";
import { NukeResults, type SearchHit } from "./NukeResults";
import { AgentSteps } from "./AgentSteps";

const API_BASE = "";
const KNOWLEDGE_SOURCE = "nuke";

export function RAGCopilot() {
  const [lastSearchQuery, setLastSearchQuery] = useState("");
  const [lastSearchCount, setLastSearchCount] = useState(0);

  useCopilotReadable({
    description: "Current Nuke documentation assistant session state",
    value: JSON.stringify({
      knowledge_source: KNOWLEDGE_SOURCE,
      knowledge_source_label: "Nuke 17.0 Reference",
      last_search:
        lastSearchCount > 0
          ? `"${lastSearchQuery}" -> ${lastSearchCount} results`
          : "none",
    }),
  });

  useCopilotAction({
    name: "search_docs",
    description:
      "Search the Nuke 17.0 documentation using hybrid BM25 + vector search. " +
      "Use when the user wants to find, browse, or list Nuke reference results on a topic.",
    parameters: [
      {
        name: "query",
        type: "string",
        description: "Search query: topic, keyword, node name, or technique",
        required: true,
      },
      {
        name: "size",
        type: "number",
        description: "Number of results to return (default: 5, max: 10)",
        required: false,
      },
    ],
    handler: async ({ query, size = 5 }: { query: string; size?: number }) => {
      const res = await fetch(`${API_BASE}/api/v1/hybrid-search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          size: Math.min(size, 10),
          use_hybrid: true,
          knowledge_source: KNOWLEDGE_SOURCE,
        }),
      });
      if (!res.ok) throw new Error(`Search failed: ${res.status}`);
      const data = await res.json();
      const hits: SearchHit[] = data.hits ?? [];
      setLastSearchQuery(query);
      setLastSearchCount(hits.length);
      return { hits };
    },
    render: ({
      status,
      result,
    }: {
      status: string;
      result?: { hits: SearchHit[] };
    }) => {
      if (status === "executing") {
        return (
          <div className="status-badge">
            <div className="spinner" />
            Searching Nuke docs...
          </div>
        );
      }
      const hits = Array.isArray(result?.hits) ? result.hits : [];
      return <NukeResults hits={hits} />;
    },
  });

  useCopilotAction({
    name: "ask_question",
    description:
      "Ask a question and get an AI-powered answer grounded in the Nuke 17.0 documentation. " +
      "Use when the user wants a direct answer, explanation, or summary.",
    parameters: [
      {
        name: "query",
        type: "string",
        description: "The Nuke documentation question to answer",
        required: true,
      },
    ],
    handler: async ({ query }: { query: string }) => {
      const res = await fetch(`${API_BASE}/api/v1/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          top_k: 3,
          use_hybrid: true,
          knowledge_source: KNOWLEDGE_SOURCE,
        }),
      });
      if (!res.ok) throw new Error(`Ask failed: ${res.status}`);
      return await res.json();
    },
    render: ({
      status,
      result,
    }: {
      status: string;
      result?: { answer: string; sources: string[]; chunks_used: number; search_mode: string };
    }) => {
      if (status === "executing") {
        return (
          <div className="status-badge">
            <div className="spinner" />
            Retrieving context and generating answer...
          </div>
        );
      }
      if (!result) return <></>;
      return (
        <div className="agent-steps">
          <div className="answer-block">{result.answer}</div>
          {result.sources?.length > 0 && (
            <div className="sources-list">
              <p style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.5rem" }}>
                Sources ({result.chunks_used} chunks | {result.search_mode}):
              </p>
              {result.sources.slice(0, 3).map((src, i) => (
                <a key={i} href={src} target="_blank" rel="noopener noreferrer">
                  {src.replace(/^https?:\/\//, "").split("/").slice(0, 4).join("/")}
                </a>
              ))}
            </div>
          )}
        </div>
      );
    },
  });

  useCopilotAction({
    name: "ask_agentic",
    description:
      "Use the full Nuke documentation RAG pipeline with LangGraph reasoning: guardrails, " +
      "document grading, query rewriting, and multi-step retrieval. Use for complex or nuanced questions.",
    parameters: [
      {
        name: "query",
        type: "string",
        description: "Complex Nuke question for agentic reasoning",
        required: true,
      },
    ],
    handler: async ({ query }: { query: string }) => {
      const res = await fetch(`${API_BASE}/api/v1/ask-agentic`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          top_k: 3,
          use_hybrid: true,
          knowledge_source: KNOWLEDGE_SOURCE,
        }),
      });
      if (!res.ok) throw new Error(`Agentic ask failed: ${res.status}`);
      return await res.json();
    },
    render: ({
      status,
      result,
    }: {
      status: string;
      result?: { answer: string; reasoning_steps: string[]; sources: string[]; retrieval_attempts: number };
    }) => {
      if (status === "executing") {
        return (
          <div className="status-badge">
            <div className="spinner" />
            Running agentic reasoning pipeline...
          </div>
        );
      }
      if (!result) return <></>;
      return (
        <AgentSteps
          steps={result.reasoning_steps ?? []}
          answer={result.answer}
          sources={result.sources ?? []}
        />
      );
    },
  });

  const greeting =
    "Hi! I can help you explore the Nuke 17.0 reference guide. Try:\n\n" +
    '- "How does the Blur node work?"\n' +
    '- "Find nodes for color grading"\n' +
    '- "Explain the Merge node compositing modes"';

  return (
    <CopilotSidebar
      defaultOpen={true}
      labels={{
        title: "Nuke Docs Assistant",
        initial: greeting,
      }}
      instructions={
        "You are an AI assistant with access to the Foundry Nuke 17.0 VFX software documentation. " +
        "Use ask_question for direct answers, search_docs to browse Nuke reference results, " +
        "or ask_agentic for complex multi-step reasoning. " +
        "Stay within Nuke, compositing, and VFX documentation topics. Always cite sources when available."
      }
    />
  );
}
