const FASTAPI_BASE_URL =
  process.env.FASTAPI_INTERNAL_URL ?? process.env.FASTAPI_BASE_URL ?? "http://localhost:8083";

export const maxDuration = 300;

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function proxyToFastAPI(req: Request, path: string[] = []): Promise<Response> {
  const subpath = path.join("/");
  const url = new URL(req.url);
  const target = `${FASTAPI_BASE_URL}/api/v1/eval/${subpath}${url.search}`;
  const contentType = req.headers.get("content-type") ?? "";

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers: {},
  };

  if (contentType.includes("multipart/form-data")) {
    init.body = req.body;
    init.duplex = "half";
    init.headers = { "content-type": contentType };
  } else if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
    init.headers = { "content-type": "application/json" };
  }

  try {
    const res = await fetch(target, init);
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (err) {
    console.error("[eval-proxy] backend unreachable:", err);
    return Response.json({ error: "FastAPI backend unreachable" }, { status: 502 });
  }
}

export async function GET(req: Request, context: RouteContext) {
  const params = await context.params;
  return proxyToFastAPI(req, params.path);
}

export async function POST(req: Request, context: RouteContext) {
  const params = await context.params;
  return proxyToFastAPI(req, params.path);
}
