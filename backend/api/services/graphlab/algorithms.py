"""Graph Lab: bounded, deterministic graph-reasoning algorithms for Kairos.

These are standard algorithms (BFS closure, Dinic max-flow / min-cut, Tarjan SCC, Brandes betweenness,
PageRank, label propagation, Dijkstra) written from scratch. The 98 research READMEs were used only as
requirement hypotheses; no third-party code is copied here. Every function is pure: it takes a
normalized `Graph` plus parameters and returns plain JSON data, so results are reproducible and testable
without a database or a language model. A model never decides a verdict, a cut or an authorization.

Edge direction convention: `source -> target` reads "source depends on / flows to target". Evidence
graphs use "dependent -> dependency" (as the Evidence Drift store does); flow graphs use "from -> to".
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

MAX_NODES = 2000
MAX_EDGES = 10000
INF = 1e15
EPS = 1e-9
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/#-]{0,127}$")
BAD_STATUS = {"SUPERSEDED", "RETRACTED", "STALE", "DISPUTED", "REVOKED"}


class GraphError(ValueError):
    """The submitted graph or parameters violate the Graph Lab contract."""


@dataclass
class Graph:
    nodes: dict[str, dict[str, Any]]
    edges: list[dict[str, Any]]
    out: dict[str, list[int]] = field(default_factory=dict)
    inc: dict[str, list[int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.out = {n: [] for n in self.nodes}
        self.inc = {n: [] for n in self.nodes}
        for i, edge in enumerate(self.edges):
            self.out[edge["source"]].append(i)
            self.inc[edge["target"]].append(i)

    def public(self) -> dict[str, Any]:
        return {"nodes": [{"id": k, **v} for k, v in self.nodes.items()], "edges": self.edges}


def _scalar(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    return str(value)[:200]


def _f(value: Any, default: float) -> float:
    """Numeric property or `default`; untrusted props never raise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    return float(value)


def normalize_graph(payload: Any) -> Graph:
    """Validate an untrusted `{nodes, edges}` payload and return a bounded, canonical Graph."""
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("edges"), list):
        raise GraphError("graph must be an object with 'nodes' and 'edges' lists")
    if len(payload["nodes"]) > MAX_NODES or len(payload["edges"]) > MAX_EDGES:
        raise GraphError(f"graph exceeds {MAX_NODES} nodes or {MAX_EDGES} edges")
    nodes: dict[str, dict[str, Any]] = {}
    for raw in payload["nodes"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not _ID.fullmatch(raw["id"]):
            raise GraphError("every node needs a safe string id")
        if raw["id"] in nodes:
            raise GraphError(f"duplicate node id: {raw['id']}")
        props = raw.get("props") if isinstance(raw.get("props"), dict) else {}
        nodes[raw["id"]] = {
            "label": str(raw.get("label") or raw["id"])[:120],
            "type": str(raw.get("type") or "node")[:40],
            "props": {str(k)[:40]: _scalar(v) for k, v in list(props.items())[:24]},
        }
    edges: list[dict[str, Any]] = []
    for raw in payload["edges"]:
        if not isinstance(raw, dict) or raw.get("source") not in nodes or raw.get("target") not in nodes:
            raise GraphError("every edge needs existing 'source' and 'target' node ids")
        weight = raw.get("weight", 1)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0:
            raise GraphError("edge weight must be a finite number >= 0")
        certainty = raw.get("certainty", "definite")
        if certainty not in ("definite", "maybe"):
            raise GraphError("edge certainty must be 'definite' or 'maybe'")
        edges.append({
            "source": raw["source"], "target": raw["target"],
            "rel": str(raw.get("rel") or "LINKS")[:40], "weight": float(weight),
            "certainty": certainty, "at": _stamp(raw.get("at")), "until": _stamp(raw.get("until")),
            "disabled": bool(raw.get("disabled", False)),
        })
    return Graph(nodes, edges)


def _stamp(value: Any) -> str | None:
    return None if value in (None, "") else _parse_time(value).isoformat()


def _parse_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise GraphError(f"not an ISO-8601 timestamp: {str(value)[:40]}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _ids(graph: Graph, values: Any, name: str, *, required: bool = True) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        values = []
    unknown = [v for v in values if v not in graph.nodes]
    if unknown:
        raise GraphError(f"unknown node(s) for '{name}': {', '.join(map(str, unknown[:5]))}")
    if required and not values:
        raise GraphError(f"'{name}' needs at least one node")
    return sorted(set(values))


def _int(params: dict, key: str, default: int, lo: int, hi: int) -> int:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= int(value) <= hi:
        raise GraphError(f"'{key}' must be an integer between {lo} and {hi}")
    return int(value)


def _live(graph: Graph, i: int) -> bool:
    return not graph.edges[i]["disabled"]


# --------------------------------------------------------------------------- blast radius
def blast_radius(graph: Graph, params: dict) -> dict:
    """Which records are affected when `changed` nodes change, with definite vs possible impact."""
    changed = _ids(graph, params.get("changed"), "changed")
    reverse = params.get("direction", "reverse") != "forward"
    depth_cap = _int(params, "max_depth", 12, 1, 32)

    def reach(definite_only: bool) -> dict[str, tuple[int, list[int]]]:
        best: dict[str, tuple[int, list[int]]] = {c: (0, []) for c in changed}
        queue = deque(changed)
        while queue:
            node = queue.popleft()
            depth, path = best[node]
            if depth >= depth_cap:
                continue
            adj = graph.inc[node] if reverse else graph.out[node]
            for i in sorted(adj, key=lambda k: (graph.edges[k]["source" if reverse else "target"], k)):
                edge = graph.edges[i]
                if edge["disabled"] or (definite_only and edge["certainty"] != "definite"):
                    continue
                nxt = edge["source"] if reverse else edge["target"]
                if nxt not in best:
                    best[nxt] = (depth + 1, [*path, i])
                    queue.append(nxt)
        return best

    possible, definite = reach(False), reach(True)
    node_marks = {c: "changed" for c in changed}
    edge_marks: dict[str, str] = {}
    rows = []
    through: dict[str, int] = {}
    for node, (depth, path) in sorted(possible.items(), key=lambda kv: (kv[1][0], kv[0])):
        if node in changed:
            continue
        sure = node in definite
        use = definite[node][1] if sure else path
        node_marks[node] = "impacted" if sure else "possible"
        for i in use:
            edge_marks.setdefault(str(i), "impact" if sure else "possible")
            origin = graph.edges[i]["target" if reverse else "source"]
            if origin not in changed:
                through[origin] = through.get(origin, 0) + 1
        rows.append({"node": node, "depth": depth if not sure else definite[node][0],
                     "certainty": "definite" if sure else "possible", "path": _path_ids(graph, use, reverse)})
    return {
        "summary": {"changed": len(changed), "definite": len(definite) - len(changed),
                    "possible_only": len(possible) - len(definite), "max_depth_reached": max((r["depth"] for r in rows), default=0)},
        "findings": rows,
        "hotspots": [{"node": n, "paths_through": c} for n, c in sorted(through.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
        "node_marks": node_marks, "edge_marks": edge_marks,
        "notes": ["'possible' means the only connecting paths include a 'maybe' edge; it prompts review, it does not prove impact."],
    }


def _path_ids(graph: Graph, edge_path: list[int], reverse: bool) -> list[str]:
    if not edge_path:
        return []
    first = graph.edges[edge_path[0]]
    ids = [first["target"] if reverse else first["source"]]
    ids += [graph.edges[i]["source" if reverse else "target"] for i in edge_path]
    return ids


# --------------------------------------------------------------------------- flow / min cut
class _Flow:
    """Dinic max-flow on an array-backed residual graph."""

    def __init__(self, n: int) -> None:
        self.n, self.head, self.to, self.cap = n, [[] for _ in range(n)], [], []

    def add(self, u: int, v: int, c: float) -> int:
        idx = len(self.to)
        self.to += [v, u]
        self.cap += [c, 0.0]
        self.head[u].append(idx)
        self.head[v].append(idx + 1)
        return idx

    def maxflow(self, s: int, t: int) -> float:
        flow = 0.0
        while flow < INF:
            level = [-1] * self.n
            level[s] = 0
            queue = deque([s])
            while queue:
                u = queue.popleft()
                for e in self.head[u]:
                    if self.cap[e] > EPS and level[self.to[e]] < 0:
                        level[self.to[e]] = level[u] + 1
                        queue.append(self.to[e])
            if level[t] < 0:
                break
            it = [0] * self.n
            while True:
                pushed = self._augment(s, t, level, it)
                if pushed <= EPS:
                    break
                flow += pushed
                if flow >= INF:
                    return flow
        return flow

    def _augment(self, s: int, t: int, level: list[int], it: list[int]) -> float:
        stack: list[int] = []
        u = s
        while True:
            if u == t:
                f = min(self.cap[e] for e in stack)
                for e in stack:
                    self.cap[e] -= f
                    self.cap[e ^ 1] += f
                return f
            advanced = False
            while it[u] < len(self.head[u]):
                e = self.head[u][it[u]]
                v = self.to[e]
                if self.cap[e] > EPS and level[v] == level[u] + 1:
                    stack.append(e)
                    u = v
                    advanced = True
                    break
                it[u] += 1
            if not advanced:
                if not stack:
                    return 0.0
                level[u] = -1
                e = stack.pop()
                u = self.to[e ^ 1]
                it[u] += 1

    def residual_reach(self, s: int) -> set[int]:
        seen, queue = {s}, deque([s])
        while queue:
            u = queue.popleft()
            for e in self.head[u]:
                if self.cap[e] > EPS and self.to[e] not in seen:
                    seen.add(self.to[e])
                    queue.append(self.to[e])
        return seen


def _reaches(graph: Graph, sources: list[str], targets: set[str], cut_edges: set[int], cut_nodes: set[str]) -> bool:
    """Independent BFS used to verify a proposed cut; shares no code with the flow solver."""
    seen = {s for s in sources if s not in cut_nodes}
    queue = deque(seen)
    while queue:
        u = queue.popleft()
        if u in targets:
            return True
        for i in graph.out[u]:
            e = graph.edges[i]
            if e["disabled"] or i in cut_edges or e["target"] in cut_nodes or e["target"] in seen:
                continue
            seen.add(e["target"])
            queue.append(e["target"])
    return False


def _node_cost(graph: Graph, name: str) -> float:
    return max(_f(graph.nodes[name]["props"].get("cost", 1), 1.0), 0.0)


def min_cut(graph: Graph, params: dict) -> dict:
    """Cheapest set of edges (or nodes) whose removal severs every sources -> targets path."""
    sources, targets = _ids(graph, params.get("sources"), "sources"), _ids(graph, params.get("targets"), "targets")
    if set(sources) & set(targets):
        raise GraphError("a node cannot be both a source and a target")
    mode = params.get("mode", "edges")
    if mode not in ("edges", "nodes"):
        raise GraphError("mode must be 'edges' or 'nodes'")
    marks = {s: "source" for s in sources} | {t: "target" for t in targets}
    if not _reaches(graph, sources, set(targets), set(), set()):
        return {"summary": {"mode": mode, "paths_exist_before": False, "already_isolated": True, "cut_cost": 0, "cut_size": 0,
                            "residual_path_exists": False, "verified": True},
                "findings": [], "node_marks": marks, "edge_marks": {}, "notes": ["Sources already cannot reach targets."]}
    names = list(graph.nodes)
    pos = {n: i for i, n in enumerate(names)}
    n = len(names)
    # edge mode: node i. node mode: node i = in-half, n + i = out-half. Super source/sink follow.
    size = 2 * n + 2 if mode == "nodes" else n + 2
    ss, tt = size - 2, size - 1
    flow = _Flow(size)
    edge_ref: dict[int, int] = {}
    node_ref: dict[int, str] = {}
    out_half = (lambda i: n + i) if mode == "nodes" else (lambda i: i)
    if mode == "nodes":
        for name, i in pos.items():
            node_ref[flow.add(i, n + i, INF if name in sources or name in targets else _node_cost(graph, name))] = name
    for i, e in enumerate(graph.edges):
        if not e["disabled"]:
            edge_ref[flow.add(out_half(pos[e["source"]]), pos[e["target"]], INF if mode == "nodes" else e["weight"])] = i
    for s in sources:
        flow.add(ss, pos[s], INF)
    for t in targets:
        flow.add(out_half(pos[t]), tt, INF)
    max_flow = flow.maxflow(ss, tt)
    if max_flow >= INF:
        return {"summary": {"mode": mode, "paths_exist_before": True, "cut_possible": False, "verified": False},
                "findings": [], "node_marks": marks, "edge_marks": {},
                "notes": ["No node cut exists: a source links directly to a target."]}
    reach = flow.residual_reach(ss)
    cut_edges = {edge_ref[idx] for idx in edge_ref if flow.to[idx ^ 1] in reach and flow.to[idx] not in reach and flow.cap[idx] <= EPS}
    cut_nodes = {name for idx, name in node_ref.items() if flow.to[idx ^ 1] in reach and flow.to[idx] not in reach}
    still = _reaches(graph, sources, set(targets), cut_edges, cut_nodes)
    cost = sum(graph.edges[i]["weight"] for i in cut_edges) if mode == "edges" else sum(_node_cost(graph, x) for x in cut_nodes)
    findings = [{"edge": i, "source": graph.edges[i]["source"], "target": graph.edges[i]["target"],
                 "rel": graph.edges[i]["rel"], "cost": graph.edges[i]["weight"]} for i in sorted(cut_edges)]
    findings += [{"node": x, "cost": _node_cost(graph, x)} for x in sorted(cut_nodes)]
    return {
        "summary": {"mode": mode, "paths_exist_before": True, "max_flow": round(max_flow, 6), "cut_cost": round(cost, 6),
                    "cut_size": len(findings), "residual_path_exists": still, "verified": (not still) and abs(cost - max_flow) < 1e-6},
        "findings": findings, "node_marks": marks | {x: "cut" for x in cut_nodes}, "edge_marks": {str(i): "cut" for i in cut_edges},
        "notes": ["Verified by an independent reachability check on a copy with the cut applied. Model-only: no real control was changed."],
    }


# --------------------------------------------------------------------------- centrality
def _adjacency(graph: Graph, undirected: bool = False) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {n: [] for n in graph.nodes}
    for e in graph.edges:
        if e["disabled"]:
            continue
        adj[e["source"]].append(e["target"])
        if undirected:
            adj[e["target"]].append(e["source"])
    return adj


def _betweenness(adj: dict[str, list[str]]) -> dict[str, float]:
    nodes = list(adj)
    bc = dict.fromkeys(nodes, 0.0)
    for s in nodes:
        stack: list[str] = []
        pred: dict[str, list[str]] = {v: [] for v in nodes}
        sigma = dict.fromkeys(nodes, 0.0)
        dist = dict.fromkeys(nodes, -1)
        sigma[s], dist[s] = 1.0, 0
        queue = deque([s])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = dict.fromkeys(nodes, 0.0)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    return bc


def _closure(graph: Graph, roots: list[str], forward: bool) -> set[str]:
    seen, queue = set(roots), deque(roots)
    while queue:
        u = queue.popleft()
        for i in (graph.out[u] if forward else graph.inc[u]):
            e = graph.edges[i]
            v = e["target"] if forward else e["source"]
            if not e["disabled"] and v not in seen:
                seen.add(v)
                queue.append(v)
    return seen


def chokepoints(graph: Graph, params: dict) -> dict:
    """Single nodes that sit on every sources -> targets path (patch/containment chokepoints)."""
    sources, targets = _ids(graph, params.get("sources"), "sources"), set(_ids(graph, params.get("targets"), "targets"))
    if set(sources) & targets:
        raise GraphError("a node cannot be both a source and a target")
    marks = {s: "source" for s in sources} | {t: "target" for t in targets}
    if not _reaches(graph, sources, targets, set(), set()):
        return {"summary": {"paths_exist": False, "chokepoints": 0}, "findings": [], "node_marks": marks, "edge_marks": {},
                "notes": ["No path from sources to targets; nothing to cut."]}
    candidates = sorted((_closure(graph, sources, True) & _closure(graph, sorted(targets), False)) - set(sources) - targets)
    found = [c for c in candidates if not _reaches(graph, sources, targets, set(), {c})]
    betw = _betweenness(_adjacency(graph)) if len(graph.nodes) <= 600 else {}
    ranked = sorted(found, key=lambda c: (-betw.get(c, 0.0), c))
    return {
        "summary": {"paths_exist": True, "chokepoints": len(ranked), "candidates_on_paths": len(candidates)},
        "findings": [{"node": c, "betweenness": round(betw.get(c, 0.0), 4)} for c in ranked],
        "node_marks": marks | {c: "chokepoint" for c in ranked}, "edge_marks": {},
        "notes": ["Removing any listed node alone disconnects every source from every target (verified by BFS)."],
    }


# --------------------------------------------------------------------------- cycles
def _scc(adj: dict[str, list[str]]) -> list[list[str]]:
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0
    for root in adj:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        work = [(root, iter(adj[root]))]
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(adj[w])))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                out.append(sorted(comp))
    return out


def cycles(graph: Graph, params: dict) -> dict:
    """Bounded simple-cycle enumeration (circular money flow, swap loops) plus strongly connected rings."""
    max_len, min_len = _int(params, "max_length", 5, 2, 8), _int(params, "min_length", 2, 2, 8)
    limit = _int(params, "limit", 100, 1, 500)
    order = sorted(graph.nodes)
    rank = {n: i for i, n in enumerate(order)}
    best: dict[tuple[str, str], int] = {}
    for i, e in enumerate(graph.edges):
        key = (e["source"], e["target"])
        if not e["disabled"] and e["source"] != e["target"] and (key not in best or e["weight"] > graph.edges[best[key]]["weight"]):
            best[key] = i
    nbrs: dict[str, list[str]] = {n: [] for n in order}
    for (u, v) in sorted(best):
        nbrs[u].append(v)
    found: list[list[str]] = []
    truncated = False

    def walk(start: str, node: str, path: list[str]) -> None:
        nonlocal truncated
        for nxt in nbrs[node]:
            if truncated:
                return
            if nxt == start and len(path) >= min_len:
                if len(found) >= limit:
                    truncated = True
                    return
                found.append(list(path))
            elif rank[nxt] > rank[start] and nxt not in path and len(path) < max_len:
                path.append(nxt)
                walk(start, nxt, path)
                path.pop()

    for start in order:
        walk(start, start, [start])
    node_marks: dict[str, str] = {}
    edge_marks: dict[str, str] = {}
    rows = []
    for ring in found:
        edge_ids = [best[(ring[k], ring[(k + 1) % len(ring)])] for k in range(len(ring))]
        node_marks.update({node: "cycle" for node in ring})
        edge_marks.update({str(i): "cycle" for i in edge_ids})
        weights = [graph.edges[i]["weight"] for i in edge_ids]
        rows.append({"nodes": ring, "length": len(ring), "total_weight": round(sum(weights), 4), "min_weight": round(min(weights), 4)})
    rows.sort(key=lambda r: (-r["min_weight"], r["nodes"]))
    rings = [c for c in _scc(_adjacency(graph)) if len(c) > 1]
    return {"summary": {"cycles": len(rows), "truncated": truncated, "rings": len(rings), "largest_ring": max((len(c) for c in rings), default=0)},
            "findings": rows, "rings": rings, "node_marks": node_marks, "edge_marks": edge_marks,
            "notes": ["min_weight is the amount that can circulate through the whole loop; a cycle is a lead, not proof of fraud."]}


# --------------------------------------------------------------------------- communities / ranking
def communities(graph: Graph, params: dict) -> dict:
    """Label-propagation communities, PageRank hubs and bridge nodes."""
    nodes = sorted(graph.nodes)
    size = max(len(nodes), 1)
    und: dict[str, dict[str, float]] = {n: {} for n in nodes}
    for e in graph.edges:
        if not e["disabled"] and e["source"] != e["target"]:
            w = max(e["weight"], 1e-6)
            und[e["source"]][e["target"]] = und[e["source"]].get(e["target"], 0) + w
            und[e["target"]][e["source"]] = und[e["target"]].get(e["source"], 0) + w
    label = {n: n for n in nodes}
    for _ in range(20):
        moved = False
        for n in nodes:
            if not und[n]:
                continue
            tally: dict[str, float] = {}
            for m, w in und[n].items():
                tally[label[m]] = tally.get(label[m], 0) + w
            top = min(tally, key=lambda k: (-tally[k], k))
            if top != label[n] and tally[top] > tally.get(label[n], 0) + EPS:
                label[n], moved = top, True
        if not moved:
            break
    groups: dict[str, list[str]] = {}
    for n in nodes:
        groups.setdefault(label[n], []).append(n)
    ordered = sorted(groups.values(), key=lambda g: (-len(g), g[0]))
    community_of = {n: k for k, g in enumerate(ordered) for n in g}
    damping, rank = 0.85, dict.fromkeys(nodes, 1 / size)
    out_w = {n: sum(graph.edges[i]["weight"] or 1e-6 for i in graph.out[n] if _live(graph, i)) for n in nodes}
    for _ in range(60):
        nxt = dict.fromkeys(nodes, (1 - damping) / size + damping * sum(rank[n] for n in nodes if not out_w[n]) / size)
        for e in graph.edges:
            if not e["disabled"] and out_w[e["source"]]:
                nxt[e["target"]] += damping * rank[e["source"]] * (e["weight"] or 1e-6) / out_w[e["source"]]
        rank = nxt
    betw = _betweenness(_adjacency(graph, undirected=True)) if len(nodes) <= 600 else {}
    rows = [{"node": n, "community": community_of[n], "pagerank": round(rank[n], 5), "betweenness": round(betw.get(n, 0.0), 3),
             "degree": len(und[n])} for n in nodes]
    rows.sort(key=lambda r: (-r["pagerank"], r["node"]))
    hubs = [r["node"] for r in rows[:3]]
    bridges = sorted((r["node"] for r in rows if r["betweenness"] > 0 and len({community_of[m] for m in und[r["node"]]}) > 1),
                     key=lambda x: (-betw.get(x, 0), x))[:3]
    return {"summary": {"nodes": len(nodes), "communities": len(ordered), "largest_community": len(ordered[0]) if ordered else 0,
                        "top_hub": hubs[0] if hubs else None},
            "findings": rows[:50], "node_marks": {n: f"community:{community_of[n]}" for n in nodes},
            "node_badges": {h: "hub" for h in hubs} | {b: "bridge" for b in bridges}, "node_metric": {n: rank[n] for n in nodes},
            "edge_marks": {}, "notes": ["Communities are unlabeled structure (label propagation); they are leads for review, not conclusions."]}


# --------------------------------------------------------------------------- temporal as-of
def as_of(graph: Graph, params: dict) -> dict:
    """Show which relationships were valid at a past moment and who owned what then."""
    stamps = sorted({s for e in graph.edges for s in (e["at"], e["until"]) if s})
    at = _parse_time(params["at"]) if params.get("at") else _parse_time(stamps[-1]) if stamps else datetime.now(UTC)
    hidden = set()
    for i, e in enumerate(graph.edges):
        start = _parse_time(e["at"]) if e["at"] else None
        end = _parse_time(e["until"]) if e["until"] else None
        if (start and start > at) or (end and end <= at):
            hidden.add(i)
    visible_nodes = {graph.edges[i][k] for i in range(len(graph.edges)) if i not in hidden for k in ("source", "target")}
    owners: dict[str, tuple[str, str]] = {}
    for i, e in enumerate(graph.edges):
        if i in hidden or e["rel"] not in ("OWNS", "OWNED_BY") or not e["at"]:
            continue
        asset, owner = (e["target"], e["source"]) if e["rel"] == "OWNS" else (e["source"], e["target"])
        if asset not in owners or e["at"] > owners[asset][1]:
            owners[asset] = (owner, e["at"])
    return {"summary": {"as_of": at.isoformat(), "visible_edges": len(graph.edges) - len(hidden), "hidden_edges": len(hidden),
                        "visible_nodes": len(visible_nodes)},
            "findings": [{"asset": a, "owner": o, "since": s} for a, (o, s) in sorted(owners.items())], "timeline": stamps,
            "node_marks": {n: "hidden" for n in graph.nodes if n not in visible_nodes}, "edge_marks": {str(i): "hidden" for i in hidden},
            "notes": ["Elements without a timestamp are treated as always valid."]}


# --------------------------------------------------------------------------- decision gate
def decision_gate(graph: Graph, params: dict) -> dict:
    """PROCEED / HOLD / REVIEW / INSUFFICIENT_EVIDENCE for a decision, from the evidence it depends on."""
    decision = _ids(graph, params.get("decision"), "decision")[0]
    required = [str(k) for k in (params.get("required_types") or []) if k]
    now = _parse_time(params["now"]) if params.get("now") else datetime.now(UTC)
    closure = sorted(_closure(graph, [decision], True) - {decision})
    holds, reviews = [], []
    for n in closure:
        props = graph.nodes[n]["props"]
        if str(props.get("status", "")).upper() in BAD_STATUS:
            holds.append({"node": n, "reason": f"status {props['status']}"})
        if props.get("expires_at") and _parse_time(props["expires_at"]) <= now:
            holds.append({"node": n, "reason": f"expired {props['expires_at']}"})
        if str(props.get("verification", "")).upper() in ("UNVERIFIED", "PENDING"):
            reviews.append({"node": n, "reason": f"verification {props['verification']}"})
    present = {graph.nodes[n]["type"] for n in closure if str(graph.nodes[n]["props"].get("status", "")).upper() not in BAD_STATUS}
    missing = [{"type": k, "reason": "no current evidence of this type supports the decision"} for k in required if k not in present]
    digest = hashlib.sha256(json.dumps([[n, graph.nodes[n]["props"].get("status"), graph.nodes[n]["props"].get("version")] for n in closure],
                                       sort_keys=True).encode()).hexdigest()
    reviewed = graph.nodes[decision]["props"].get("reviewed_digest")
    if reviewed and reviewed != digest[:16]:
        reviews.append({"node": decision, "reason": "approval was recorded against different evidence (digest mismatch)"})
    # A confirmed blocker must dominate a separate missing-evidence condition: reporting only
    # INSUFFICIENT_EVIDENCE would hide the known stale/expired evidence that already requires HOLD.
    verdict = ("HOLD" if holds else "INSUFFICIENT_EVIDENCE" if missing or not closure else "REVIEW" if reviews else "PROCEED")
    marks = {decision: verdict.lower()} | {x["node"]: "review" for x in reviews if x["node"] != decision} | {x["node"]: "blocker" for x in holds}
    return {"summary": {"verdict": verdict, "evidence_items": len(closure), "closure_digest": digest[:16]},
            "findings": [{"kind": "hold", **x} for x in holds] + [{"kind": "review", **x} for x in reviews]
                        + [{"kind": "missing", **x} for x in missing],
            "node_marks": marks, "edge_marks": {},
            "notes": ["Unknown or absent evidence never produces PROCEED. A model cannot raise a verdict."]}


# --------------------------------------------------------------------------- contamination / verdict
def contamination(graph: Graph, params: dict) -> dict:
    """How much of each record rests on retracted evidence, weighted by how strongly it depends on it."""
    retracted = set(_ids(graph, params.get("retracted"), "retracted"))
    flag_at = min(max(_f(params.get("flag_at", 0.25), 0.25), 0.0), 1.0)
    score = {n: (1.0 if n in retracted else 0.0) for n in graph.nodes}
    for _ in range(len(graph.nodes) + 5):
        delta = 0.0
        for n in graph.nodes:
            total = sum(graph.edges[i]["weight"] for i in graph.out[n] if _live(graph, i))
            if n in retracted or total <= 0:
                continue
            value = sum(graph.edges[i]["weight"] * score[graph.edges[i]["target"]] for i in graph.out[n] if _live(graph, i)) / total
            delta, score[n] = max(delta, abs(value - score[n])), value
        if delta < 1e-9:
            break
    rows = sorted(({"node": n, "contamination": round(s, 4)} for n, s in score.items() if s > 0 and n not in retracted),
                  key=lambda r: (-r["contamination"], r["node"]))
    marks = {n: "retracted" for n in retracted} | {r["node"]: ("contaminated" if r["contamination"] >= flag_at else "exposed") for r in rows}
    return {"summary": {"retracted": len(retracted), "flagged": sum(1 for r in rows if r["contamination"] >= flag_at), "exposed": len(rows)},
            "findings": rows, "node_marks": marks, "edge_marks": {},
            "notes": ["Score = weighted share of a record's dependencies that are retracted or themselves contaminated."]}


def claim_verdict(graph: Graph, params: dict) -> dict:
    """SUPPORTED / REFUTED / CONTESTED / UNVERIFIED from authority-weighted SUPPORTS and REFUTES edges."""
    claim = _ids(graph, params.get("claim"), "claim")[0]
    side = {"SUPPORTS": 0.0, "REFUTES": 0.0}
    rows, edge_marks, node_marks = [], {}, {}
    for i in graph.inc[claim]:
        e = graph.edges[i]
        if e["disabled"] or e["rel"] not in side:
            continue
        props = graph.nodes[e["source"]]["props"]
        live = str(props.get("status", "")).upper() not in BAD_STATUS
        strength = e["weight"] * _f(props.get("authority"), 50.0) / 100 * (1 if live else 0)
        side[e["rel"]] += strength
        rows.append({"evidence": e["source"], "relation": e["rel"], "strength": round(strength, 4), "live": live})
        edge_marks[str(i)] = e["rel"].lower()
        node_marks[e["source"]] = e["rel"].lower() if live else "retracted"
    total = side["SUPPORTS"] + side["REFUTES"]
    margin = abs(side["SUPPORTS"] - side["REFUTES"]) / total if total > EPS else 0.0
    verdict = "UNVERIFIED" if total <= EPS else "CONTESTED" if margin < 0.2 else "SUPPORTED" if side["SUPPORTS"] > side["REFUTES"] else "REFUTED"
    rows.sort(key=lambda r: (-r["strength"], r["evidence"]))
    return {"summary": {"verdict": verdict, "support": round(side["SUPPORTS"], 4), "refute": round(side["REFUTES"], 4), "margin": round(margin, 3)},
            "findings": rows, "node_marks": node_marks | {claim: verdict.lower()}, "edge_marks": edge_marks,
            "notes": ["Superseded or retracted evidence carries zero weight. CONTESTED means the sides are within 20% of each other."]}


# --------------------------------------------------------------------------- routing
def _dijkstra(graph: Graph, source: str, target: str, blocked: set[str]) -> tuple[float, list[int]] | None:
    dist, prev, heap = {source: 0.0}, {}, [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        if u == target:
            path: list[int] = []
            while u != source:
                path.append(prev[u])
                u = graph.edges[prev[u]]["source"]
            return d, path[::-1]
        for i in graph.out[u]:
            e = graph.edges[i]
            if e["disabled"] or e["target"] in blocked:
                continue
            nd = d + e["weight"]
            if nd < dist.get(e["target"], math.inf) - EPS:
                dist[e["target"]], prev[e["target"]] = nd, i
                heapq.heappush(heap, (nd, e["target"]))
    return None


def route(graph: Graph, params: dict) -> dict:
    """Cheapest route that avoids disrupted nodes, compared with the undisrupted baseline."""
    source, target = _ids(graph, params.get("source"), "source")[0], _ids(graph, params.get("target"), "target")[0]
    avoid = set(_ids(graph, params.get("avoid"), "avoid", required=False))
    avoid |= {n for n, v in graph.nodes.items() if v["props"].get("disrupted") is True}
    avoid -= {source, target}
    base, best = _dijkstra(graph, source, target, set()), _dijkstra(graph, source, target, avoid)
    steps = [{"from": graph.edges[i]["source"], "to": graph.edges[i]["target"], "rel": graph.edges[i]["rel"], "cost": graph.edges[i]["weight"]}
             for i in (best[1] if best else [])]
    return {"summary": {"reachable": best is not None, "cost": round(best[0], 4) if best else None,
                        "baseline_cost": round(base[0], 4) if base else None,
                        "detour_cost": round(best[0] - base[0], 4) if best and base else None, "avoided": sorted(avoid)},
            "findings": steps, "node_marks": {source: "source", target: "target"} | {a: "disrupted" for a in avoid},
            "edge_marks": {str(i): "route" for i in (best[1] if best else [])},
            "notes": ["Unreachable means no route exists without a disrupted node; the answer is never guessed."]}
