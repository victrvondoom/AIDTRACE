import { describe, expect, it } from "vitest"
import { arcPoints, greatCircleDistanceKm, pointAlong } from "./globe-arcs"

const shanghai = { lat: 31.23, lng: 121.47 }
const losAngeles = { lat: 34.05, lng: -118.24 }

describe("globe arcs", () => {
  it("measures great-circle distance", () => {
    expect(greatCircleDistanceKm(shanghai, losAngeles)).toBeGreaterThan(10_000)
    expect(greatCircleDistanceKm(shanghai, losAngeles)).toBeLessThan(10_800)
    expect(greatCircleDistanceKm(shanghai, shanghai)).toBe(0)
  })

  it("starts and ends on the surface at the given points and peaks in the middle", () => {
    const pts = arcPoints(shanghai, losAngeles, { segments: 32 })
    expect(pts).toHaveLength(33)
    expect(pts[0].lat).toBeCloseTo(shanghai.lat, 4)
    expect(pts[0].lng).toBeCloseTo(shanghai.lng, 4)
    expect(pts[32].lat).toBeCloseTo(losAngeles.lat, 4)
    expect(pts[32].lng).toBeCloseTo(losAngeles.lng, 4)
    expect(pts[0].height).toBe(0)
    expect(pts[32].height).toBeCloseTo(0, 6)
    expect(pts[16].height).toBeGreaterThan(pts[4].height)
    expect(Math.max(...pts.map((p) => p.height))).toBeLessThanOrEqual(1_900_000)
  })

  it("is a degenerate two-point arc when origin and destination coincide", () => {
    expect(arcPoints(shanghai, shanghai)).toHaveLength(2)
  })

  it("interpolates along an arc without wrapping the long way round the antimeridian", () => {
    const pts = arcPoints(shanghai, losAngeles)
    const mid = pointAlong(pts, 0.5)
    // Shanghai to Los Angeles crosses the Pacific, so the midpoint is near the antimeridian, not over Eurasia.
    expect(Math.abs(mid.lng)).toBeGreaterThan(150)
    expect(pointAlong(pts, 0).lat).toBeCloseTo(shanghai.lat, 4)
    expect(pointAlong(pts, 1).lat).toBeCloseTo(losAngeles.lat, 4)
    expect(pointAlong(pts, 5)).toEqual(pointAlong(pts, 1))
  })
})
