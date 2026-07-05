import {
  CopilotRuntime,
  OpenAIAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import OpenAI from "openai";
import { NextRequest } from "next/server";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const runtime = new CopilotRuntime();

const serviceAdapter = new OpenAIAdapter({
  openai,
  model: process.env.OPENAI_MODEL ?? "gpt-4o-mini",
});

const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
  runtime,
  serviceAdapter,
  endpoint: "/api/copilotkit",
});

export const GET = async (req: NextRequest) => {
  const { pathname } = new URL(req.url);
  if (pathname.endsWith("/threads")) {
    return new Response(JSON.stringify({ threads: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }
  return new Response("Not found", { status: 404 });
};
export const POST = handleRequest;
