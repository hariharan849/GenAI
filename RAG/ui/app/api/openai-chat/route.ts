import OpenAI from "openai";
import type {
  ResponseInput,
  ResponseInputItem,
} from "openai/resources/responses/responses";

export const maxDuration = 90;

const ALLOWED_SOURCES = ["nuke"] as const;
type KnowledgeSource = (typeof ALLOWED_SOURCES)[number];

const FASTAPI_ROUTES: Record<string, string> = {
  search_docs: "/api/v1/hybrid-search/",
  ask_question: "/api/v1/ask",
  ask_agentic: "/api/v1/ask-agentic",
};

const tools: OpenAI.Responses.Tool[] = [
  {
    type: "function",
    name: "search_docs",
    description:
      "Search the Nuke 17.0 documentation using hybrid BM25 + vector search. Use when the user wants to find or browse results on a topic.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query" },
        size: {
          type: "number",
          description: "Results to return (default: 5)",
          minimum: 1,
          maximum: 10,
        },
      },
      required: ["query"],
    },
    strict: false,
  },
  {
    type: "function",
    name: "ask_question",
    description:
      "Get an AI-powered answer grounded in the Nuke 17.0 documentation. Use for direct questions needing explanation or summary.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "The question to answer" },
      },
      required: ["query"],
    },
    strict: false,
  },
  {
    type: "function",
    name: "ask_agentic",
    description:
      "Use the full agentic RAG pipeline with multi-step reasoning, document grading, and query rewriting. Use for complex questions.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Complex question for agentic reasoning" },
      },
      required: ["query"],
    },
    strict: false,
  },
];

function systemPrompt(knowledgeSource: KnowledgeSource): string {
  void knowledgeSource;
  return (
    "You are an AI assistant with access to the Foundry Nuke 17.0 VFX software documentation. " +
    "Use search_docs to find and browse results. Use ask_question for direct answers. " +
    "Use ask_agentic for complex multi-step questions. Always cite sources when available. " +
    "Do not answer from general knowledge when the question is about Nuke — use the tools."
  );
}

export async function POST(req: Request) {
  let body: { messages?: unknown; knowledgeSource?: unknown };
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid JSON" }), { status: 400 });
  }

  const { messages, knowledgeSource } = body;

  if (!ALLOWED_SOURCES.includes(knowledgeSource as KnowledgeSource)) {
    return new Response(
      JSON.stringify({ error: `knowledgeSource must be one of: ${ALLOWED_SOURCES.join(", ")}` }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
  const ks = knowledgeSource as KnowledgeSource;

  if (!Array.isArray(messages)) {
    return new Response(JSON.stringify({ error: "messages must be an array" }), { status: 400 });
  }

  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();
  let writerClosed = false;

  async function safeWrite(chunk: string) {
    if (writerClosed) return;
    try {
      await writer.write(encoder.encode(chunk));
    } catch {
      writerClosed = true;
    }
  }

  async function safeClose() {
    if (writerClosed) return;
    writerClosed = true;
    try {
      await writer.close();
    } catch {
      // already closed
    }
  }

  (async () => {
    try {
      const cappedMessages = (messages as { role: "user" | "assistant"; content: string }[]).slice(
        -20
      );
      const input: ResponseInput = [
        { role: "system", content: systemPrompt(ks) } as ResponseInputItem,
        ...(cappedMessages as ResponseInputItem[]),
      ];

      let previousResponseId: string | undefined;
      let pendingToolOutputs: { type: "function_call_output"; call_id: string; output: string }[] =
        [];
      let iterations = 0;

      while (iterations++ < 10) {
        const streamInput: ResponseInput = previousResponseId
          ? pendingToolOutputs
          : input;

        const stream = await openai.responses.create({
          model: process.env.OPENAI_MODEL ?? "gpt-4o-mini",
          stream: true,
          tools,
          input: streamInput,
          ...(previousResponseId ? { previous_response_id: previousResponseId } : {}),
        });

        // Collect completed tool calls (use output_item.done — arguments are complete)
        const toolCalls: { name: string; arguments: string; call_id: string }[] = [];

        for await (const event of stream) {
          if (
            event.type === "response.output_item.done" &&
            event.item.type === "function_call"
          ) {
            toolCalls.push({
              name: event.item.name,
              arguments: event.item.arguments ?? "",
              call_id: event.item.call_id,
            });
          }
          if (event.type === "response.output_text.delta") {
            await safeWrite(event.delta + "\n");
          }
          if (event.type === "response.completed") {
            previousResponseId = event.response.id;
          }
        }

        if (toolCalls.length === 0) break;

        // Dispatch ALL tool calls in parallel (v1 fix)
        console.log(
          `[openai-chat] dispatching ${toolCalls.length} tool call(s):`,
          toolCalls.map((tc) => tc.name).join(", ")
        );

        const results = await Promise.all(
          toolCalls.map(async (tc) => {
            if (!Object.keys(FASTAPI_ROUTES).includes(tc.name)) {
              return { call_id: tc.call_id, output: JSON.stringify({ error: "unknown tool" }) };
            }
            let args: Record<string, unknown>;
            try {
              args = JSON.parse(tc.arguments || "{}");
            } catch {
              return {
                call_id: tc.call_id,
                output: JSON.stringify({ error: "bad tool arguments" }),
              };
            }
            const result = await callFastAPI(tc.name, args, ks);
            console.log(
              `[openai-chat] tool_result: ${tc.name}`,
              JSON.stringify(result).slice(0, 200)
            );
            return { call_id: tc.call_id, output: JSON.stringify(result) };
          })
        );

        pendingToolOutputs = results.map((r) => ({
          type: "function_call_output" as const,
          call_id: r.call_id,
          output: r.output,
        }));

        // Guard: previousResponseId must be set before chaining
        if (!previousResponseId) {
          await safeWrite("ERROR: response ID missing, cannot continue tool loop\n");
          break;
        }
      }
    } catch (err) {
      await safeWrite(`ERROR: ${(err as Error).message}\n`);
    } finally {
      await safeClose();
    }
  })();

  return new Response(readable, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

async function callFastAPI(
  toolName: string,
  args: Record<string, unknown>,
  knowledgeSource: KnowledgeSource
) {
  const base = process.env.FASTAPI_INTERNAL_URL ?? process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";
  const timeoutMs = toolName === "ask_agentic" ? 90_000 : 30_000;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  // search_docs caps size at 10 to match FastAPI schema (ge=1, le=100 but UI max is 10)
  if (toolName === "search_docs" && typeof args.size === "number") {
    args = { ...args, size: Math.min(args.size as number, 10) };
  }

  try {
    const res = await fetch(`${base}${FASTAPI_ROUTES[toolName]}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...args, knowledge_source: knowledgeSource }),
      signal: controller.signal,
    });
    if (!res.ok) return { error: `FastAPI ${res.status}` };
    return await res.json();
  } catch (err) {
    console.error("[openai-chat] tool call failed:", toolName, err);
    return { error: "Backend unreachable or timed out" };
  } finally {
    clearTimeout(timeout);
  }
}
