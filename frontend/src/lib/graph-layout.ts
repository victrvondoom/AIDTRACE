// Pure, deterministic graph layouts for Graph Lab. Positions are normalised to the unit square so any
// renderer (SVG here) can scale them. No randomness: the same graph always lays out the same way.

export interface LabNode { id: string; label: string; type: string; props: Record<string, string | number | boolean | null> }
export interface LabEdge {
  source: string; target: string; rel: string; weight: number; certainty: "definite" | "maybe";
  at: string | null; until: string | null; disabled: boolean;
}
export interface LabGraph { nodes: LabNode[]; edges: LabEdge[] }
export interface Point { x: number; y: number }
export type Positions = Record<string, Point>
export type LayoutKind = "network" | "layered" | "radial"

export const FORCE_NODE_LIMIT = 300;

const sortedIds = (g: LabGraph) => g.nodes.map((n) => n.id).sort();

function normalise(raw: Positions): Positions {
  const ids = Object.keys(raw);
  if (!ids.length) return raw;
  const xs = ids.map((i) => raw[i].x), ys = ids.map((i) => raw[i].y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const out: Positions = {};
  for (const id of ids) {
    out[id] = { x: x1 === x0 ? 0.5 : (raw[id].x - x0) / (x1 - x0), y: y1 === y0 ? 0.5 : (raw[id].y - y0) / (y1 - y0) };
  }
  return out;
}

function undirected(g: LabGraph): Record<string, string[]> {
  const adj: Record<string, string[]> = Object.fromEntries(g.nodes.map((n) => [n.id, [] as string[]]));
  for (const e of g.edges) {
    if (e.source !== e.target) { adj[e.source].push(e.target); adj[e.target].push(e.source); }
  }
  for (const k of Object.keys(adj)) adj[k] = [...new Set(adj[k])].sort();
  return adj;
}

/** Evenly spaced ring; used as the seed for the force layout and as the large-graph fallback. */
export function circleLayout(g: LabGraph): Positions {
  const ids = sortedIds(g);
  const out: Positions = {};
  ids.forEach((id, i) => {
    const a = (2 * Math.PI * i) / Math.max(ids.length, 1) - Math.PI / 2;
    out[id] = { x: 0.5 + 0.5 * Math.cos(a), y: 0.5 + 0.5 * Math.sin(a) };
  });
  return out;
}

/** Fruchterman-Reingold from a deterministic circular seed with anti-overlap and center-gravity forces. */
export function networkLayout(g: LabGraph, iterations = 140): Positions {
  const ids = sortedIds(g);
  if (ids.length > FORCE_NODE_LIMIT) return radialLayout(g);
  const pos: Positions = circleLayout(g);
  const k = Math.sqrt(1 / Math.max(ids.length, 1)) * 0.85;
  const edges = g.edges.filter((e) => e.source !== e.target);
  let temp = 0.14;
  for (let step = 0; step < iterations; step++) {
    const disp: Positions = Object.fromEntries(ids.map((i) => [i, { x: 0, y: 0 }]));
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = pos[ids[i]], b = pos[ids[j]];
        let dx = a.x - b.x, dy = a.y - b.y;
        let d = Math.hypot(dx, dy);
        if (d < 1e-6) { dx = 1e-3 * (i + 1); dy = 1e-3 * (j + 1); d = Math.hypot(dx, dy); }
        // Anti-clustering: stronger repulsion when nodes get too close to prevent dense clumps
        const f = d < k * 0.4 ? (k * k * 2.2) / Math.max(d, 0.005) : (k * k) / d;
        disp[ids[i]].x += (dx / d) * f; disp[ids[i]].y += (dy / d) * f;
        disp[ids[j]].x -= (dx / d) * f; disp[ids[j]].y -= (dy / d) * f;
      }
    }
    for (const e of edges) {
      const a = pos[e.source], b = pos[e.target];
      if (!a || !b) continue;
      const dx = a.x - b.x, dy = a.y - b.y, d = Math.max(Math.hypot(dx, dy), 1e-6);
      // Bound attractive force so highly connected cliques do not collapse into single points
      const f = Math.min((d * d) / k, k * 3.5);
      disp[e.source].x -= (dx / d) * f; disp[e.source].y -= (dy / d) * f;
      disp[e.target].x += (dx / d) * f; disp[e.target].y += (dy / d) * f;
    }
    // Gentle gravity to center to keep components balanced
    for (const id of ids) {
      disp[id].x += (0.5 - pos[id].x) * 0.04;
      disp[id].y += (0.5 - pos[id].y) * 0.04;
      const d = Math.max(Math.hypot(disp[id].x, disp[id].y), 1e-9);
      const m = Math.min(d, temp);
      pos[id] = { x: pos[id].x + (disp[id].x / d) * m, y: pos[id].y + (disp[id].y / d) * m };
    }
    temp = Math.max(temp * 0.97, 0.002);
  }
  return normalise(pos);
}

/** Left-to-right layers along edge direction (longest path), cycle-safe, ordered by neighbour barycentre. */
export function layeredLayout(g: LabGraph): Positions {
  const ids = sortedIds(g);
  const layer: Record<string, number> = Object.fromEntries(ids.map((i) => [i, 0]));
  const edges = g.edges.filter((e) => e.source !== e.target);
  for (let pass = 0; pass < ids.length; pass++) {
    let moved = false;
    for (const e of edges) {
      if (layer[e.target] < layer[e.source] + 1 && layer[e.source] + 1 < ids.length) { layer[e.target] = layer[e.source] + 1; moved = true; }
    }
    if (!moved) break;
  }
  const depth = Math.max(...Object.values(layer), 0);
  const columns: string[][] = Array.from({ length: depth + 1 }, () => []);
  for (const id of ids) columns[layer[id]].push(id);
  const adj = undirected(g);
  const row: Record<string, number> = {};
  columns.forEach((c) => c.forEach((id, i) => { row[id] = i; }));
  for (let sweep = 0; sweep < 3; sweep++) {
    for (const col of columns) {
      const bary = (id: string) => {
        const ns = adj[id].filter((n) => layer[n] !== layer[id]);
        return ns.length ? ns.reduce((s, n) => s + row[n], 0) / ns.length : row[id];
      };
      col.sort((a, b) => bary(a) - bary(b) || a.localeCompare(b));
      col.forEach((id, i) => { row[id] = i; });
    }
  }
  const out: Positions = {};
  columns.forEach((col, c) => col.forEach((id, i) => {
    out[id] = { x: depth === 0 ? 0.5 : c / depth, y: (i + 0.5) / col.length };
  }));
  return out;
}

/** Concentric rings by hop distance from a root (default: the best-connected node). */
export function radialLayout(g: LabGraph, root?: string): Positions {
  const ids = sortedIds(g);
  if (!ids.length) return {};
  const adj = undirected(g);
  const start = root && adj[root] ? root : [...ids].sort((a, b) => adj[b].length - adj[a].length || a.localeCompare(b))[0];
  const level: Record<string, number> = { [start]: 0 };
  const queue = [start];
  while (queue.length) {
    const u = queue.shift() as string;
    for (const v of adj[u]) if (!(v in level)) { level[v] = level[u] + 1; queue.push(v); }
  }
  const far = Math.max(...Object.values(level), 0) + 1;
  for (const id of ids) if (!(id in level)) level[id] = far;
  const rings: Record<number, string[]> = {};
  for (const id of ids) (rings[level[id]] ||= []).push(id);
  const out: Positions = {};
  const maxLevel = Math.max(...Object.keys(rings).map(Number));
  for (const [lv, members] of Object.entries(rings)) {
    const r = maxLevel === 0 ? 0 : (Number(lv) / maxLevel) * 0.5;
    members.forEach((id, i) => {
      const a = (2 * Math.PI * i) / members.length - Math.PI / 2 + Number(lv) * 0.35;
      out[id] = { x: 0.5 + r * Math.cos(a), y: 0.5 + r * Math.sin(a) };
    });
  }
  return out;
}

export function layout(kind: LayoutKind, g: LabGraph, root?: string): Positions {
  return kind === "layered" ? layeredLayout(g) : kind === "radial" ? radialLayout(g, root) : networkLayout(g);
}
