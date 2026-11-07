import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

/**
 * API_PROXY_TARGET (server-side, e.g. https://routeproof-api.onrender.com): when set, /api/v1/* is proxied to the
 * backend so the HttpOnly session cookie is first-party. Pair it with NEXT_PUBLIC_API_URL="" (relative URLs) and
 * TRUST_PROXY_HEADERS=true on the backend so rate limits see the real client address.
 */
const proxyTarget = (process.env.API_PROXY_TARGET ?? "").replace(/\/$/, "");

// The browser only talks to this origin, plus the API origin when it is called directly (local dev, no proxy).
const apiOrigin = (() => {
  try { return process.env.NEXT_PUBLIC_API_URL ? new URL(process.env.NEXT_PUBLIC_API_URL).origin : isDev ? "http://localhost:8000" : ""; }
  catch { return ""; }
})();

// Static CSP (no nonces, so pages stay statically renderable). React never renders strings as HTML here and the
// codebase has no dangerouslySetInnerHTML; 'unsafe-inline' for scripts is needed by Next's inline bootstrap without
// nonces, while everything else (connect, img, frames, objects, forms, base) is locked to this origin.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' blob: data:",
  "font-src 'self'",
  `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""}${isDev ? " ws: wss:" : ""}`,
  "worker-src 'self'",
  "manifest-src 'self'",
  "media-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return proxyTarget ? [{ source: "/api/v1/:path*", destination: `${proxyTarget}/api/v1/:path*` }] : [];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Permissions-Policy", value: "camera=(self), geolocation=(self), microphone=()" },
          ...(isDev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]),
        ],
      },
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }] },
    ];
  },
};

export default nextConfig;
