import { describe, expect, it } from "vitest";
import nextConfig, { contentSecurityPolicy } from "../../next.config";

// L2
describe("security headers", () => {
  it("ships CSP, nosniff, referrer and permissions policies on every route", async () => {
    const [rule] = await nextConfig.headers!();
    const h = Object.fromEntries(rule.headers.map((x) => [x.key, x.value]));
    expect(rule.source).toBe("/:path*");
    expect(h["X-Content-Type-Options"]).toBe("nosniff");
    expect(h["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(h["Permissions-Policy"]).toContain("microphone=(self)");
    expect(h["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
  });

  it("allows only the API origin, the satellite tile hosts and the YouTube embed off-site", () => {
    const csp = contentSecurityPolicy("https://api.example.com/v1", false);
    expect(csp).toContain("connect-src 'self' https://api.example.com https://services.arcgisonline.com https://gibs.earthdata.nasa.gov;");
    expect(csp).toContain("img-src 'self' data: blob: https://services.arcgisonline.com https://gibs.earthdata.nasa.gov;");
    expect(csp).not.toContain("cesium.com");
    expect(csp).toContain("worker-src 'self' blob:;");
    // CesiumJS starts its workers from nested blob URLs; without blob: in script-src the globe renders no Earth surface.
    expect(csp).toMatch(/script-src [^;]*blob:/);
    expect(csp).toContain("frame-src https://www.youtube-nocookie.com;");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).not.toContain("unsafe-eval");
  });

  it("adds no API origin when the API is same-origin (/api), instead of a stray token", () => {
    const csp = contentSecurityPolicy("/api", false);
    expect(csp).toContain("connect-src 'self' https://services.arcgisonline.com https://gibs.earthdata.nasa.gov;");
    expect(csp).not.toMatch(/connect-src[^;]*null/);
    expect(csp).not.toContain("localhost:8000");
  });

  it("opens Cesium ion hosts only when a token is configured", () => {
    expect(contentSecurityPolicy("https://api.example.com", false, true)).toContain("https://api.cesium.com");
  });

  it("allows eval only in development and survives a bad API url", () => {
    expect(contentSecurityPolicy("::nope", true)).toContain("'unsafe-eval'");
    expect(contentSecurityPolicy(undefined, false)).toContain("http://localhost:8000");
  });

  it("sends the retired overview, catalogue and supply-chain pages into the workspace", async () => {
    const redirects = await nextConfig.redirects!();
    for (const source of ["/overview", "/workspace", "/supply-chain"]) {
      expect(redirects).toContainEqual(expect.objectContaining({ source, destination: "/hub" }));
    }
  });

  it("lets the dev server hydrate from either loopback name", () => {
    expect(nextConfig.allowedDevOrigins).toEqual(expect.arrayContaining(["127.0.0.1", "localhost"]));
  });
});
