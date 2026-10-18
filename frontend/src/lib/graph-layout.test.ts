import { describe, expect, it } from "vitest";
import { circleLayout, FORCE_NODE_LIMIT, layeredLayout, layout, networkLayout, radialLayout, type LabEdge, type LabGraph } from "./graph-layout";

const node = (id: string) => ({ id, label: id, type: "node", props: {} });
const edge = (source: string, target: string): LabEdge => ({ source, target, rel: "LINKS", weight: 1, certainty: "definite", at: null, until: null, disabled: false });
const chain: LabGraph = { nodes: ["a", "b", "c", "d"].map(node), edges: [edge("a", "b"), edge("b", "c"), edge("a", "d"), edge("d", "c")] };
const cyclic: LabGraph = { nodes: ["x", "y", "z"].map(node), edges: [edge("x", "y"), edge("y", "z"), edge("z", "x")] };

const inUnit = (p: { x: number; y: number }) => p.x >= -1e-9 && p.x <= 1 + 1e-9 && p.y >= -1e-9 && p.y <= 1 + 1e-9 && Number.isFinite(p.x + p.y);

describe("graph layouts", () => {
  it("are deterministic and stay inside the unit square", () => {
    for (const kind of ["network", "layered", "radial"] as const) {
      const first = layout(kind, chain);
      expect(layout(kind, chain)).toEqual(first);
      expect(Object.keys(first).sort()).toEqual(["a", "b", "c", "d"]);
      expect(Object.values(first).every(inUnit)).toBe(true);
    }
  });

  it("layers respect edge direction on a DAG", () => {
    const p = layeredLayout(chain);
    for (const e of chain.edges) expect(p[e.source].x).toBeLessThan(p[e.target].x);
    expect(p.b.y).not.toBe(p.d.y);
  });

  it("terminates on cycles and self loops", () => {
    const looped = { ...cyclic, edges: [...cyclic.edges, edge("x", "x")] };
    expect(Object.values(layeredLayout(looped)).every(inUnit)).toBe(true);
    expect(Object.values(networkLayout(looped)).every(inUnit)).toBe(true);
  });

  it("radial puts the root at the centre and disconnected nodes on the outer ring", () => {
    const g: LabGraph = { nodes: [...chain.nodes, node("lone")], edges: chain.edges };
    const p = radialLayout(g, "a");
    expect(p.a).toEqual({ x: 0.5, y: 0.5 });
    const dist = (id: string) => Math.hypot(p[id].x - 0.5, p[id].y - 0.5);
    expect(dist("lone")).toBeGreaterThanOrEqual(dist("c"));
  });

  it("separates coincident and isolated nodes in the force layout", () => {
    const g: LabGraph = { nodes: ["p", "q", "r"].map(node), edges: [] };
    const p = networkLayout(g);
    expect(new Set(Object.values(p).map((v) => `${v.x.toFixed(3)},${v.y.toFixed(3)}`)).size).toBe(3);
  });

  it("falls back to a cheap layout above the force limit", () => {
    const big: LabGraph = { nodes: Array.from({ length: FORCE_NODE_LIMIT + 5 }, (_, i) => node(`n${i}`)), edges: [] };
    expect(Object.keys(networkLayout(big))).toHaveLength(FORCE_NODE_LIMIT + 5);
    expect(Object.keys(circleLayout(big))).toHaveLength(FORCE_NODE_LIMIT + 5);
  });

  it("handles an empty graph", () => {
    expect(layout("network", { nodes: [], edges: [] })).toEqual({});
    expect(layout("layered", { nodes: [], edges: [] })).toEqual({});
  });
});
