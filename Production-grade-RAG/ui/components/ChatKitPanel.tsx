"use client";

import { ChatKit, useChatKit } from "@openai/chatkit-react";
import { useState } from "react";

const STARTER_PROMPTS = [
  {
    label: "Blur node",
    prompt: "How does the Blur node work in Nuke?",
    icon: "book-open" as const,
  },
  {
    label: "Color grading",
    prompt: "Find Nuke nodes for color grading and explain when to use them.",
    icon: "search" as const,
  },
  {
    label: "Merge modes",
    prompt: "Explain the Merge node compositing modes with examples.",
    icon: "sparkle" as const,
  },
];

export function ChatKitPanel() {
  const [error, setError] = useState<string | null>(null);

  const { control } = useChatKit({
    api: {
      async getClientSecret(existingClientSecret) {
        if (existingClientSecret) {
          return existingClientSecret;
        }

        const res = await fetch("/api/chatkit/session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data.error ?? `ChatKit session failed: ${res.status}`);
        }
        return data.client_secret;
      },
    },
    header: {
      enabled: true,
      title: { text: "Nuke Docs ChatKit" },
    },
    history: { enabled: true },
    composer: {
      placeholder: "Ask about Nuke nodes, compositing, or VFX workflows...",
      attachments: { enabled: false },
    },
    startScreen: {
      greeting: "Ask the Nuke 17.0 reference guide.",
      prompts: STARTER_PROMPTS,
    },
    theme: {
      colorScheme: "light",
      radius: "soft",
      density: "normal",
      color: {
        accent: { primary: "#2563eb", level: 2 },
        grayscale: { hue: 220, tint: 2 },
      },
    },
    onError(event) {
      setError(event.error.message);
    },
  });

  return (
    <div className="chatkit-shell">
      {error && (
        <div className="chatkit-error">
          <strong>ChatKit error</strong>
          <span>{error}</span>
        </div>
      )}
      <ChatKit control={control} className="chatkit-frame" />
    </div>
  );
}
