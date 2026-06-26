"use client";

import { useState } from "react";
import { RAGCopilot } from "@/components/RAGCopilot";

type KnowledgeSource = "arxiv" | "nuke";

const SOURCES: { id: KnowledgeSource; label: string; icon: string; description: string }[] = [
  {
    id: "arxiv",
    label: "arXiv CS.AI",
    icon: "📄",
    description: "Search and Q&A over indexed arXiv CS.AI research papers.",
  },
  {
    id: "nuke",
    label: "Nuke 17.0",
    icon: "🎬",
    description: "Browse and query the Foundry Nuke VFX reference guide.",
  },
];

export default function Home() {
  const [knowledgeSource, setKnowledgeSource] = useState<KnowledgeSource>("arxiv");

  return (
    <>
      <main className="main-content">
        <div className="hero">
          <h1>AI Knowledge Assistant</h1>
          <p>
            Search and ask questions across multiple knowledge bases — arXiv CS.AI research
            papers and the Foundry Nuke 17.0 reference guide — using hybrid semantic + keyword
            search and agentic multi-step reasoning.
          </p>
        </div>

        {/* Knowledge source picker */}
        <div className="source-picker-section">
          <p className="source-picker-label">Active knowledge base</p>
          <div className="source-picker">
            {SOURCES.map((src) => (
              <button
                key={src.id}
                className={`source-btn ${knowledgeSource === src.id ? "active" : ""}`}
                onClick={() => setKnowledgeSource(src.id)}
              >
                <span className="source-btn-icon">{src.icon}</span>
                <span className="source-btn-label">{src.label}</span>
              </button>
            ))}
          </div>
          <p className="source-picker-desc">
            {SOURCES.find((s) => s.id === knowledgeSource)?.description}
          </p>
        </div>

        <div className="capabilities">
          <div className="capability-card">
            <h3>Ask a Question</h3>
            <p>
              {knowledgeSource === "nuke"
                ? "Get answers about Nuke nodes, compositing, and VFX techniques with doc citations."
                : "Get AI-generated answers grounded in indexed arXiv papers with source citations."}
            </p>
          </div>
          <div className="capability-card">
            <h3>Search</h3>
            <p>
              {knowledgeSource === "nuke"
                ? "Hybrid BM25 + vector search across Nuke node reference pages."
                : "Hybrid BM25 + vector search across paper titles, abstracts, and full text."}
            </p>
          </div>
          <div className="capability-card">
            <h3>Agentic RAG</h3>
            <p>Multi-step reasoning with query rewriting, document grading, and guardrails.</p>
          </div>
        </div>
      </main>

      <RAGCopilot
        knowledgeSource={knowledgeSource}
        onKnowledgeSourceChange={setKnowledgeSource}
      />
    </>
  );
}
