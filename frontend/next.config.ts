import type { NextConfig } from "next";

// Local development talks to the API on the host; deployment receives the
// public API URL through Railway. Keeping this in one place also makes
// same-origin rewrites work for requests that do not use the client helper.
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8002/api/v1";
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
