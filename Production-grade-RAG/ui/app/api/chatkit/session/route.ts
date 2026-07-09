import OpenAI from "openai";

export const runtime = "nodejs";

export async function POST() {
  const workflowId = process.env.OPENAI_CHATKIT_WORKFLOW_ID;
  if (!workflowId) {
    return Response.json(
      {
        error:
          "OPENAI_CHATKIT_WORKFLOW_ID is not configured. Create a ChatKit workflow in OpenAI and set this env var.",
      },
      { status: 500 }
    );
  }

  const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const session = await client.beta.chatkit.sessions.create({
    user: "nuke-rag-local-user",
    workflow: {
      id: workflowId,
    },
    chatkit_configuration: {
      history: {
        enabled: true,
        recent_threads: 10,
      },
      file_upload: {
        enabled: false,
      },
    },
    rate_limits: {
      max_requests_per_1_minute: 10,
    },
  });

  return Response.json({
    client_secret: session.client_secret,
    expires_at: session.expires_at,
  });
}
