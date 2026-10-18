// Deterministic 3D placement for the hub overview graph. Pure (no Three.js), so it is unit-tested without WebGL.
// AIDTRACE sits at the origin. The other capabilities are spread over two shells so related ones sit near each other
// and no two nodes collide: the same ids always land in the same place, which keeps the scene stable between visits.

export type Vec3 = [number, number, number]

/** Capability ids in a fixed order. The order, not the data, decides placement. */
export const NODE_ORDER = [
  "resolveai", "greenchain", "consumer", "fraud", "cybersecurity", "agents",
  "memory", "evidence-drift", "graph", "simulations", "reports",
] as const

const INNER = new Set(["resolveai", "greenchain", "agents", "memory", "evidence-drift"])

/** Points on a sphere of `radius`, spread evenly (Fibonacci lattice), starting at `offset` of the golden turn. */
export function fibonacciSphere(count: number, radius: number, offset = 0): Vec3[] {
  const golden = Math.PI * (3 - Math.sqrt(5))
  return Array.from({ length: count }, (_, i) => {
    const y = count === 1 ? 0 : 1 - (i / (count - 1)) * 2
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = golden * (i + offset)
    return [Math.cos(theta) * r * radius, y * radius * 0.8, Math.sin(theta) * r * radius] as Vec3
  })
}

export function layoutCapabilities(ids: readonly string[]): Record<string, Vec3> {
  const out: Record<string, Vec3> = { overview: [0, 0, 0] }
  const known = NODE_ORDER.filter((id) => ids.includes(id))
  const extras = ids.filter((id) => id !== "overview" && !(NODE_ORDER as readonly string[]).includes(id)).sort()
  const ordered = [...known, ...extras]
  const inner = ordered.filter((id) => INNER.has(id))
  const outer = ordered.filter((id) => !INNER.has(id))
  fibonacciSphere(inner.length, 3.9).forEach((p, i) => { out[inner[i]] = p })
  fibonacciSphere(outer.length, 6.6, 0.5).forEach((p, i) => { out[outer[i]] = p })
  return out
}

export function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])
}

/** The smallest distance between any two placed nodes; the test uses it to prove nothing overlaps. */
export function minSeparation(positions: Record<string, Vec3>): number {
  const pts = Object.values(positions)
  let best = Infinity
  for (let i = 0; i < pts.length; i += 1) for (let j = i + 1; j < pts.length; j += 1) best = Math.min(best, distance(pts[i], pts[j]))
  return best
}
