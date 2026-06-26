"use client";

import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useState } from "react";
import { NukeResults, PaperResults, type SearchHit } from "./PaperCard";
import { AgentSteps } from "./AgentSteps";

const API_BASE = "";

type KnowledgeSource = "arxiv" | "nuke";

interface RAGCopilotProps {
  knowledgeSource: KnowledgeSource;
  onKnowledgeSourceChange: (src: KnowledgeSource) => void;
}

export function RAGCopilot({ knowledgeSource, onKnowledgeSourceChange }: RAGCopilotProps) {
  const [lastSearchQuery, setLastSearchQuery] = useState("");
  const [lastSearchCount, setLastSearchCount] = useState(0);

  useCopilotReadable({
    description: "Current knowledge source and session state",
    value: JSON.stringify({
      knowledge_source: knowledgeSource,
      knowledge_source_label: knowledgeSource === "nuke" ? "Nuke 17.0 Reference" : "arXiv CS.AI Papers",
      last_search:
        lastSearchCount > 0
          ? `"${lastSearchQuery}" → ${lastSearchCount} results`
          : "none",
    }),
  });

  // Generative UI: LLM calls this when it infers the user wants to switch sources
  useCopilotAction({
    name: "set_knowledge_source",
    description:
      "Switch the active knowledge source. Call this when the user's question is clearly " +
      "about Nuke VFX software (nodes, compositing, reference guide) to switch to 'nuke', " +
      "or about AI/ML research papers to switch to 'arxiv'.",
    parameters: [
      {
        name: "source",
        type: "string",
        description: "Knowledge source to activate: 'arxiv' or 'nuke'",
        required: true,
      },
      {
        name: "reason",
        type: "string",
        description: "One-sentence reason for switching",
        required: false,
      },
    ],
    handler: async ({ source, reason }: { source: string; reason?: string }) => {
      const validated = source === "nuke" ? "nuke" : "arxiv";
      onKnowledgeSourceChange(validated);
      return { active: validated, reason };
    },
    render: ({
      status,
      result,
    }: {
      status: string;
      result?: { active: string; reason?: string };
    }) => {
      const active = result?.active ?? knowledgeSource;
      const label = active === "nuke" ? "Nuke 17.0 Reference" : "arXiv CS.AI Papers";
      const icon = active === "nuke" ? "🎬" : "📄";
      if (status === "executing") {
        return (
          <div className="status-badge">
            <div className="spinner" />
            Switching knowledge source…
          </div>
        );
      }
      return (
        <div className="source-switch-result">
          <span className={`source-chip ${active}`}>
            {icon} {label}
          </span>
          {result?.reason && (
            <p className="source-switch-reason">{result.reason}</p>
          )}
        </div>
      );
    },
  });

  useCopilotAction({
    name: "search_papers",
    description:
      "Search the active knowledge base using hybrid BM25 + vector search. " +
      "Use when the user wants to find, browse, or list results on a topic. " +
      "Searches arXiv papers when knowledge_source is 'arxiv', " +
      "or Nuke documentation when knowledge_source is 'nuke'.",
    parameters: [
      {
        name: "query",
        type: "string",
        description: "Search query — topic, keyword, node name, or paper title",
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
      const res = await fetch(`${API_BASE}/api/v1/hybrid-search/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          size: Math.min(size, 10),
          use_hybrid: true,
          knowledge_source: knowledgeSource,
        }),
      });
      if (!res.ok) throw new Error(`Search failed: ${res.status}`);
      const data = await res.json();
      const hits: SearchHit[] = data.hits ?? [];
      setLastSearchQuery(query);
      setLastSearchCount(hits.length);
      return { hits, knowledge_source: knowledgeSource };
    },
    render: ({
      status,
      result,
    }: {
      status: string;
      result?: { hits: SearchHit[]; knowledge_source: string };
    }) => {
      if (status === "executing") {
        const label = knowledgeSource === "nuke" ? "Nuke docs" : "arXiv papers";
        return (
          <div className="status-badge">
            <div className="spinner" />
            Searching {label}…
          </div>
        );
      }
      const hits = Array.isArray(result?.hits) ? result.hits : [];
      return result?.knowledge_source === "nuke" ? (
        <NukeResults hits={hits} />
      ) : (
        <PaperResults hits={hits} />
      );
    },
  });

  useCopilotAction({
    name: "ask_question",
    description:
      "Ask a question and get an AI-powered answer grounded in the active knowledge base. " +
      "Use when the user wants a direct answer, explanation, or summary. " +
      "Works for both arXiv research questions and Nuke VFX technical questions.",
    parameters: [
      {
        name: "query",
        type: "string",
        description: "The question to answer",
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
          knowledge_source: knowledgeSource,
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
            Retrieving context and generating answer…
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
                Sources ({result.chunks_used} chunks · {result.search_mode}):
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
      "Use the full agentic RAG pipeline with LangGraph reasoning: guardrails, document grading, " +
      "query rewriting, and multi-step retrieval. Use for complex or nuanced questions " +
      "that may require multiple retrieval attempts. Works with both arXiv and Nuke knowledge sources.",
    parameters: [
      {
        name: "query",
        type: "string",
        description: "Complex question for agentic reasoning",
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
          knowledge_source: knowledgeSource,
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
            Running agentic reasoning pipeline…
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
    knowledgeSource === "nuke"
      ? "Hi! I can help you explore the Nuke 17.0 reference guide. Try:\n\n" +
        '• "How does the Blur node work?"\n' +
        '• "Find nodes for color grading"\n' +
        '• "Explain the Merge node compositing modes"'
      : "Hi! I can help you explore AI and ML research papers. Try:\n\n" +
        '• "What are vision transformers?"\n' +
        '• "Find papers on diffusion models"\n' +
        '• "Explain RLHF with citations"';

  return (
    <CopilotSidebar
      defaultOpen={true}
      labels={{
        title:
          knowledgeSource === "nuke"
            ? "Nuke Docs Assistant"
            : "arXiv Research Assistant",
        initial: greeting,
      }}
      instructions={
        "You are an AI assistant with access to two knowledge bases: " +
        "(1) arXiv CS.AI research papers and (2) Foundry Nuke 17.0 VFX software documentation. " +
        `The currently active knowledge source is: ${knowledgeSource === "nuke" ? "Nuke 17.0 Reference" : "arXiv CS.AI Papers"}. ` +
        "When a user's question clearly relates to Nuke VFX software (nodes, compositing, effects), " +
        "call set_knowledge_source with source='nuke' BEFORE answering. " +
        "When it relates to AI/ML research, call set_knowledge_source with source='arxiv'. " +
        "Then use ask_question for direct answers, search_papers to browse results, " +
        "or ask_agentic for complex multi-step reasoning. " +
        "Always cite sources when available."
      }
    />
  );
}
