const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL ?? "http://localhost:8083";

export const maxDuration = 300; // eval runs can take several minutes

async function proxyToFastAPI(req: Request, path: string[]): Promise<Response> {
  const subpath = path.join("/");
  const url = new URL(req.url);
  const target = `${FASTAPI_BASE_URL}/api/v1/eval/${subpath}${url.search}`;

  const init: RequestInit = { method: req.method };

  const contentType = req.headers.get("content-type") ?? "";
  if (contentType.includes("multipart/form-data")) {
    // Forward multipart upload (YAML file) without re-encoding
    init.body = req.body;
    init.duplex = "half";
    init.headers = { "content-type": contentType };
  } else if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
    init.headers = { "content-type": "application/json" };
  }

  try {
    const res = await fetch(target, init as RequestInit);
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    console.error("[eval-proxy] backend unreachable:", err);
    return new Response(JSON.stringify({ error: "FastAPI backend unreachable" }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }
}

export async function GET(req: Request, { params }: { params: { path: string[] } }) {
  return proxyToFastAPI(req, params.path);
}

export async function POST(req: Request, { params }: { params: { path: string[] } }) {
  return proxyToFastAPI(req, params.path);
}
