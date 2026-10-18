import type { NextConfig } from "next";
import { SATELLITE_TILE_ORIGINS } from "./src/lib/greenchain/cesium-imagery";

// The one cross-origin host the browser talks to is the API (NEXT_PUBLIC_API_URL, baked in at build).
function apiOrigin(apiUrl: string | undefined): string {
  // A relative URL ("/api") is same-origin, which 'self' already covers: add nothing.
  if (apiUrl?.startsWith("/")) return "";
  try {
    return new URL(apiUrl ?? "http://localhost:8000").origin;
  } catch {
    return "http://localhost:8000";
  }
}

/** Content-Security-Policy. `script-src` keeps 'unsafe-inline' on purpose: Next 16 emits inline
 *  bootstrap and RSC-payload scripts on every page, so a hash cannot cover them, and a nonce would
 *  need per-request rendering, which turns the static landing page and every cached shell dynamic.
 *  The rest is tight: no plugins, no foreign frames, no off-site form posts, and only the API,
 *  YouTube's cookie-less embed and self-hosted fonts are reachable. */
export function contentSecurityPolicy(apiUrl: string | undefined, dev = false, ionEnabled = false): string {
  const api = apiOrigin(apiUrl);
  // The Cesium globe fetches satellite tiles straight from these hosts (as images, and via fetch for decoding).
  // Cesium ion hosts are only reachable when a token is configured for the deployment.
  const tiles = [...SATELLITE_TILE_ORIGINS, ...(ionEnabled ? ["https://api.cesium.com", "https://*.cesium.com"] : [])].join(" ");
  return [
    "default-src 'self'",
    // `blob:` is required by CesiumJS: its TaskProcessor starts each web worker from a blob wrapper that then imports a second blob URL, and
    // script-src governs that nested import. Without it every worker fails silently, no Earth tile ever finishes loading and the globe renders
    // as empty space (markers and routes still draw because they need no worker). Blob URLs can only be minted by same-origin script.
    `script-src 'self' 'unsafe-inline' blob:${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${tiles}`,
    "font-src 'self' data:",
    "media-src 'self' blob:",
    `connect-src ${["'self'", api, tiles].filter(Boolean).join(" ")}`,
    "frame-src https://www.youtube-nocookie.com",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

const nextConfig: NextConfig = {
  // Development only: the dev server refuses hot-reload and client hydration from any host it does not list, so a page opened at
  // 127.0.0.1 (instead of localhost) rendered as a permanent skeleton. Both loopback names now work against the same server.
  allowedDevOrigins: ["127.0.0.1", "localhost"],

  // Emit a self-contained production server (.next/standalone/server.js)
  // for a minimal, non-root Docker runtime image. Windows local builds avoid EBUSY lock on standalone.
  output: process.env.BUILD_STANDALONE === "true" ? "standalone" : undefined,

  // The dev-tools overlay defaults to a Next.js logo pinned bottom-left, which
  // lands inside every screenshot tools/capture_landing_shots.sh takes for the
  // landing page. Dev-only overlay, so this has no effect on the production build.
  devIndicators: false,

  // The overview used to live at /management; old bookmarks and links keep working.
  async redirects() {
    return [
      { source: "/management/:path*", destination: "/overview/:path*", permanent: true },
      // The workspace absorbed these three pages (risk overview, feature catalogue, supply-chain globe); old links land in it.
      { source: "/overview", destination: "/hub", permanent: false },
      { source: "/workspace", destination: "/hub", permanent: false },
      { source: "/supply-chain", destination: "/hub", permanent: false },
    ];
  },

  // Same-origin API gateway: with NEXT_PUBLIC_API_URL=/api the browser only ever talks to this origin and
  // Next forwards /api/* to the private backend (API_INTERNAL_URL). Additive: an absolute NEXT_PUBLIC_API_URL
  // keeps working exactly as before.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.API_INTERNAL_URL || (process.env.API_HOSTPORT ? `http://${process.env.API_HOSTPORT}` : "http://localhost:8000")}/:path*` }];
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: contentSecurityPolicy(process.env.NEXT_PUBLIC_API_URL, process.env.NODE_ENV !== "production", Boolean(process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN)),
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Voice notes need the microphone on this origin only; nothing else is used.
          { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=(), payment=(), usb=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
