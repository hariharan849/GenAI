"use client";

import { RAGCopilot } from "@/components/RAGCopilot";

export default function Home() {
  return (
    <>
      <main className="main-content">
        <div className="home-header">
          <div className="hero">
            <h1>Nuke Docs Assistant</h1>
            <p>
              Search and ask questions over the Foundry Nuke 17.0 reference guide using
              hybrid semantic + keyword search and agentic multi-step reasoning.
            </p>
          </div>
          <a href="/eval" className="eval-link">Eval Console</a>
        </div>

        <div className="capabilities">
          <div className="capability-card">
            <h3>Ask a Question</h3>
            <p>Get answers about Nuke nodes, compositing, and VFX techniques with doc citations.</p>
          </div>
          <div className="capability-card">
            <h3>Search</h3>
            <p>Hybrid BM25 + vector search across Nuke node reference pages.</p>
          </div>
          <div className="capability-card">
            <h3>Agentic RAG</h3>
            <p>Multi-step reasoning with query rewriting, document grading, and guardrails.</p>
          </div>
        </div>
      </main>

      <RAGCopilot />
    </>
  );
}
