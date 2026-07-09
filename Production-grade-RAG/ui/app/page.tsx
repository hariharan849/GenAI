"use client";

import { useState } from "react";
import { RAGCopilot } from "@/components/RAGCopilot";
import { ChatKitPanel } from "@/components/ChatKitPanel";

type ChatProvider = "copilotkit" | "chatkit";

const PROVIDERS: { id: ChatProvider; label: string; description: string }[] = [
  {
    id: "copilotkit",
    label: "CopilotKit",
    description: "Sidebar assistant with CopilotKit actions and generative UI results.",
  },
  {
    id: "chatkit",
    label: "ChatKit",
    description: "Embedded OpenAI ChatKit experience backed by a ChatKit workflow.",
  },
];

export default function Home() {
  const [chatProvider, setChatProvider] = useState<ChatProvider>("copilotkit");
  const activeProvider = PROVIDERS.find((provider) => provider.id === chatProvider);

  return (
    <>
      <main className="main-content assistant-panel-open">
        <div className="home-header">
          <div className="hero">
            <h1>Nuke Docs Assistant</h1>
            <p>
              Search and ask questions over the Foundry Nuke 17.0 reference guide using
              hybrid semantic + keyword search and agentic multi-step reasoning.
            </p>
          </div>
          <div className="home-actions">
            <div className="provider-switch" role="group" aria-label="Chat provider">
              {PROVIDERS.map((provider) => (
                <button
                  key={provider.id}
                  aria-pressed={chatProvider === provider.id}
                  className={`provider-switch-btn ${chatProvider === provider.id ? "active" : ""}`}
                  type="button"
                  onClick={() => setChatProvider(provider.id)}
                >
                  {provider.label}
                </button>
              ))}
            </div>
            <a href="/eval" className="eval-link">Eval Console</a>
          </div>
        </div>
        <p className="provider-picker-desc">{activeProvider?.description}</p>

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

      {chatProvider === "chatkit" && <ChatKitPanel />}
      {chatProvider === "copilotkit" && <RAGCopilot />}
    </>
  );
}
