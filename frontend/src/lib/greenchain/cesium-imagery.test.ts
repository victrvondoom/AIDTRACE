import { describe, expect, it } from "vitest"
import { contentSecurityPolicy } from "../../../next.config"
import { imageryOptions, latestViirsDate, originOf, SATELLITE_TILE_ORIGINS } from "./cesium-imagery"

describe("cesium imagery catalogue", () => {
  it("asks NASA for yesterday's composite (UTC)", () => {
    expect(latestViirsDate(new Date("2026-10-18T00:30:00Z"))).toBe("2026-10-17")
    expect(latestViirsDate(new Date("2026-03-01T23:59:00Z"))).toBe("2026-02-28")
  })

  it("lists a bundled offline fallback and requires attribution on every source", () => {
    const options = imageryOptions(new Date("2026-10-18T12:00:00Z"))
    expect(options.some((o) => o.key === "offline" && o.kind === "bundled")).toBe(true)
    expect(options.every((o) => o.attribution.length > 10)).toBe(true)
    expect(options.find((o) => o.key === "viirs")?.template).toContain("2026-10-17")
  })

  it("only exposes the ion source when a token is configured", () => {
    expect(imageryOptions(new Date(), false).some((o) => o.key === "ion")).toBe(false)
    expect(imageryOptions(new Date(), true).some((o) => o.key === "ion")).toBe(true)
  })

  it("keeps every remote tile host inside the Content-Security-Policy allow-list", () => {
    const csp = contentSecurityPolicy("https://api.example.com", false)
    for (const option of imageryOptions()) {
      if (!option.template) continue
      expect(SATELLITE_TILE_ORIGINS as readonly string[]).toContain(originOf(option.template))
      expect(csp).toContain(originOf(option.template))
    }
  })
})
