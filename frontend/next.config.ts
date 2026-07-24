import type { NextConfig } from "next";

// Sprint 9: baseline security headers (see docs/sprint9/security-notes.md), refined
// after a real staging deploy (see docs/staging/csp-tradeoff.md - the original
// script-src 'self' blocked Next.js's own inline hydration script and left the app
// stuck on "Loading" forever). Only applied to production builds (`next build && next
// start`) - dev mode has its own HMR/eval requirements this isn't trying to cover.
const isProduction = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  async headers() {
    const baseHeaders = [
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
    ];
    const productionHeaders = isProduction
      ? [
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              // 'unsafe-inline' on script-src is a known, documented tradeoff for
              // staging - see docs/staging/csp-tradeoff.md. Next.js's App Router
              // bootstraps hydration via an inline <script> in the initial HTML; a
              // bare `script-src 'self'` blocks that script outright, and the app
              // never hydrates (stuck on the initial server-rendered "Loading"
              // state forever, with a CSP violation in the console - exactly the
              // failure this fixes). The real fix is per-request nonces or content
              // hashes, not a blanket allowance - tracked as a follow-up, not done
              // here to keep this a minimal, verified staging fix.
              "script-src 'self' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data:",
              // Browser API traffic is same-origin; only server-side route
              // handlers connect to the configured backend origin.
              "connect-src 'self'",
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
