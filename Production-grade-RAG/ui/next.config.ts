import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // In Docker, Next.js rewrites /api/v1/* to FastAPI internally (server-side).
  // In Docker behind nginx, the browser sends /api/v1/* to nginx which routes to FastAPI,
  // so rewrites are only needed for local dev (Next.js at :3002, FastAPI at :8083).
  async rewrites() {
    const fastapiBase =
      process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8083";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${fastapiBase}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
