import type { NextConfig } from "next";

// Sprint 9: baseline security headers (see docs/sprint9/security-notes.md). CSP is
// scoped tightly enough that it could interfere with Next.js dev-mode's HMR/eval
// requirements, so it's only applied to production builds (`next build && next
// start`) - the other headers carry no such risk and apply unconditionally.
const isProduction = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  async headers() {
    const baseHeaders = [
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
    ];
    const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
    const productionHeaders = isProduction
      ? [
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data:",
              `connect-src 'self' ${apiOrigin}`.trim(),
              "frame-ancestors 'none'",
              "base-uri 'self'",
            ].join("; "),
          },
        ]
      : [];
    return [
      {
        source: "/:path*",
        headers: [...baseHeaders, ...productionHeaders],
      },
    ];
  },
};

export default nextConfig;
