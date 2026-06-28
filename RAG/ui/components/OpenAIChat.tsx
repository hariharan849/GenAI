"use client";

import { useEffect, useRef, useState } from "react";

type KnowledgeSource = "nuke";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface OpenAIChatProps {
  knowledgeSource: KnowledgeSource;
}

const GREETING =
  "Hi! I can help you explore the Nuke 17.0 reference guide. Try:\n\n" +
  '• "How does the Blur node work?"\n' +
  '• "Find nodes for color grading"\n' +
  '• "Explain the Merge node compositing modes"';

export function OpenAIChat({ knowledgeSource }: OpenAIChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streamText, setStreamText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justMounted, setJustMounted] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Show mount notice briefly then clear
    const t = setTimeout(() => setJustMounted(false), 3000);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamText]);

  // Cancel any in-flight request on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  async function send() {
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { role: "user", content: input.trim() };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setStreamText("");
    setError(null);
    setIsLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/openai-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages,
          knowledgeSource,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error ?? `HTTP ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!; // keep incomplete last chunk

        for (const line of lines) {
          if (!line) continue;
          if (line.startsWith("ERROR: ")) {
            throw new Error(line.slice(7));
          }
          accumulated += line;
          setStreamText(accumulated);
        }
      }

      // Flush any remaining buffer content
      if (buffer) {
        accumulated += buffer;
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: accumulated || "(no response)" },
      ]);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message);
      }
    } finally {
      setStreamText("");
      setIsLoading(false);
      abortRef.current = null;
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="openai-chat-panel">
      <div className="openai-chat-header">
        <span className="openai-chat-title">Nuke Docs Assistant</span>
        <span className="openai-chat-badge">OpenAI Responses API</span>
      </div>

      {justMounted && (
        <div className="openai-chat-notice">
          Conversation cleared — now in OpenAI mode
        </div>
      )}

      {error && (
        <div className="openai-chat-error status-badge" style={{ color: "#dc2626", background: "#fef2f2", margin: "0.5rem 1rem" }}>
          <span>Error: {error}</span>
          <button
            onClick={() => setError(null)}
            style={{ marginLeft: "0.5rem", background: "none", border: "none", cursor: "pointer", color: "#dc2626", fontWeight: 700 }}
          >
            ×
          </button>
        </div>
      )}

      <div className="openai-chat-messages">
        {/* Greeting */}
        <div className="openai-msg assistant">
          <div className="openai-msg-content" style={{ whiteSpace: "pre-wrap" }}>
            {GREETING}
          </div>
        </div>

        {messages.map((msg, i) => (
          <div key={i} className={`openai-msg ${msg.role}`}>
            <div className="openai-msg-content" style={{ whiteSpace: "pre-wrap" }}>
              {msg.content}
            </div>
          </div>
        ))}

        {/* In-flight streaming message */}
        {isLoading && (
          <div className="openai-msg assistant">
            {streamText ? (
              <div className="openai-msg-content" style={{ whiteSpace: "pre-wrap" }}>
                {streamText}
                <span className="openai-cursor" />
              </div>
            ) : (
              <div className="status-badge" style={{ margin: "0.25rem 0" }}>
                <div className="spinner" />
                Searching knowledge base…
              </div>
            )}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="openai-chat-input-row">
        <textarea
          className="openai-chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about Nuke nodes, compositing, VFX…"
          rows={2}
          disabled={isLoading}
        />
        <button
          className={`openai-chat-send source-btn${isLoading ? "" : " active"}`}
          onClick={send}
          disabled={isLoading || !input.trim()}
          style={{ pointerEvents: isLoading ? "none" : "auto" }}
        >
          {isLoading ? <div className="spinner" /> : "Send"}
        </button>
      </div>
    </div>
  );
}
