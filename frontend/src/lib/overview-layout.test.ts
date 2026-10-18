import { describe, expect, it } from "vitest"
import { fibonacciSphere, layoutCapabilities, minSeparation, NODE_ORDER } from "./overview-layout"

const IDS = ["overview", ...NODE_ORDER]

describe("overview 3D layout", () => {
  it("places AIDTRACE at the origin and every other capability somewhere distinct", () => {
    const pos = layoutCapabilities(IDS)
    expect(pos.overview).toEqual([0, 0, 0])
    expect(Object.keys(pos).sort()).toEqual([...IDS].sort())
    expect(minSeparation(pos)).toBeGreaterThan(1.8) // cards never overlap
  })

  it("is deterministic and independent of input order", () => {
    expect(layoutCapabilities(IDS)).toEqual(layoutCapabilities([...IDS].reverse()))
  })

  it("keeps working when a capability is missing or unknown", () => {
    const pos = layoutCapabilities(["overview", "resolveai", "zeta", "alpha"])
    expect(Object.keys(pos).sort()).toEqual(["alpha", "overview", "resolveai", "zeta"])
    expect(minSeparation(pos)).toBeGreaterThan(1)
  })

  it("spreads points over a sphere of the requested radius", () => {
    for (const [x, y, z] of fibonacciSphere(8, 4)) expect(Math.hypot(x, y / 0.8, z)).toBeCloseTo(4, 5)
    expect(fibonacciSphere(1, 4)).toHaveLength(1)
  })
})
