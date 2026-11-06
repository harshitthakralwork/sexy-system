import type { NextConfig } from "next";

// Browser requests stay same-origin so the HttpOnly session cookie belongs to
// the frontend domain. Railway supplies the upstream target server-side only.
// Docker Compose exposes the local API on 8000. Keep the same default here and
// in start-local.bat so the dashboard cannot proxy to a stale 8002 process.
const apiBaseUrl = process.env.API_BACKEND_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const apiOrigin = apiBaseUrl.replace(/\/api\/v1\/?$/, "");

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiBaseUrl}/:path*`,
      },
      {
        source: "/health/:path*",
        destination: `${apiOrigin}/health/:path*`,
      },
    ];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
