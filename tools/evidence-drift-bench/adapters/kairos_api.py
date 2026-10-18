"""Source-verified Kairos drift routes, with explicit local-test write gates."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class KairosAPIError(RuntimeError):
    """An HTTP, transport, or response-contract failure without credential leakage."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


Transport = Callable[[str, str, dict[str, Any] | None, str], dict[str, Any]]

# These require a changed original source. Other fixture semantics need a workflow
# endpoint, authority resolution, or status reads that generic impact does not offer.
IMPACT_TYPES = frozenset({
    "supplier_evidence_supersession", "outdated_emissions_estimate",
    "changed_supplier_relationship", "cybersecurity_risk_evidence",
    "stale_agent_memory", "direct_decision_invalidation",
    "multi_hop_dependency_invalidation", "cyclic_dependencies", "duplicate_events",
})
UNSUPPORTED = {
    "agent_memory_recall": "No evidence invalidation to trigger; recall state is not returned by /drift/impact.",
    "independently_supported_conclusion": "The impact endpoint does not subtract alternate current support.",
    "irrelevant_evidence_update": "The impact endpoint has no materiality or relevance input.",
    "conflicting_sources": "Authority and conflict resolution are not exposed for arbitrary fixtures.",
    "cross_tenant_isolation": "Requires a second site-bound test identity and a separate authorization check.",
    "approval_invalidation": "Generic impact does not revalidate approval revisions or action eligibility.",
}


def compatibility(scenario: dict[str, Any]) -> dict[str, str]:
    """State which fixture semantics the generic impact route can actually test."""
    kind = scenario["scenario_type"]
    if kind in IMPACT_TYPES and scenario["original_evidence"]["invalidated"] is True:
        return {"status": "SUPPORTED_IMPACT_ONLY", "reason": "Source to dependent reachability; no persisted validity status."}
    return {"status": "UNSUPPORTED", "reason": UNSUPPORTED.get(kind, "No verified route maps this fixture to an evidence change.")}


def require_loopback(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Kairos API must be an http:// loopback address for this write-capable adapter")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Kairos API URL must be a bare loopback origin")


class HTTPTransport:
    """Small injectable transport using only documented Kairos paths."""

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        require_loopback(base_url)
        if timeout_seconds <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._opener = build_opener(_NoRedirect)

    def __call__(self, method: str, path: str, payload: dict[str, Any] | None, token: str) -> dict[str, Any]:
        if not path.startswith(("/auth/me", "/drift/")) or path.startswith("//"):
            raise ValueError("Unverified Kairos path")
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            self.base_url + path, data=data, method=method,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise KairosAPIError(f"Kairos returned HTTP {exc.code} for {method} {path}", exc.code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise KairosAPIError(f"Kairos request failed for {method} {path}: {type(exc).__name__}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KairosAPIError(f"Kairos returned invalid JSON for {method} {path}") from exc
        if not isinstance(result, dict):
            raise KairosAPIError(f"Kairos returned a non-object for {method} {path}")
        return result


class _NoRedirect(HTTPRedirectHandler):
    """Never forward a test bearer token off the configured loopback origin."""

    def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise KairosAPIError(f"{name} must be an object")
    return value


def parse_impact(response: dict[str, Any], site_id: str, known_ids: set[str], root_id: str) -> frozenset[str]:
    """Validate actual ImpactResponse, including paths and accidental tenant leakage."""
    value = _object(response, "impact response")
    if value.get("site_id") != site_id or value.get("traversal_limited") is not False:
        raise KairosAPIError("Impact site mismatch or incomplete traversal")
    paths = value.get("impacted")
    if not isinstance(paths, list):
        raise KairosAPIError("Impact response must contain impacted list")
    found: set[str] = set()
    for item in paths:
        path_item = _object(item, "impact path")
        node_id, depth, path = (path_item.get(key) for key in ("node_id", "depth", "path"))
        if not isinstance(node_id, str) or node_id not in known_ids:
            raise KairosAPIError("Impact response contains unknown node")
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
            raise KairosAPIError("Impact depth is invalid")
        if not isinstance(path, list) or len(path) != depth + 1 or path[0] != root_id or path[-1] != node_id:
            raise KairosAPIError("Impact path is invalid")
        if any(not isinstance(part, str) or part not in known_ids for part in path):
            raise KairosAPIError("Impact path crosses fixture boundary")
        found.add(node_id)  # duplicate paths for the same dependent are stable
    return frozenset(found)


def build_impact_graph(scenario: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Translate only dependency semantics shared by the fixture and Kairos schema."""
    if compatibility(scenario)["status"] != "SUPPORTED_IMPACT_ONLY":
        raise ValueError("Scenario has no compatible Kairos impact mapping")
    nodes: dict[str, dict[str, Any]] = {}
    for node in scenario["nodes"]:
        label = {"evidence": "SourceVersion", "decision": "Decision", "memory": "Memory",
                 "supplier_relationship": "Claim"}.get(node["kind"])
        if label:
            nodes[node["id"]] = {"label": label, "node_id": node["id"], "properties": {
                "benchmark_scenario_id": scenario["scenario_id"], "synthetic": True,
            }}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(source: str, target: str, relationship: str) -> None:
        key = (source, target, relationship)
        edges[key] = {
            "source_label": nodes[source]["label"], "source_id": source,
            "target_label": nodes[target]["label"], "target_id": target,
            "relationship": relationship, "kind": "logical", "properties": {},
        }

    def claim_for(evidence_id: str) -> str:
        claim_id = evidence_id.replace(":evidence:", ":claim:")
        if claim_id not in nodes:
            nodes[claim_id] = {"label": "Claim", "node_id": claim_id, "properties": {
                "benchmark_scenario_id": scenario["scenario_id"], "synthetic": True,
            }}
            add(claim_id, evidence_id, "SUPPORTED_BY")
        return claim_id

    for relation in scenario["relationships"]:
        source, target, kind = (relation[key] for key in ("source", "target", "kind"))
        if kind == "SUPPORTS" and target in nodes and nodes[target]["label"] == "Decision":
            dependency = claim_for(source) if nodes[source]["label"] == "SourceVersion" else source
            add(target, dependency, "DEPENDS_ON")
        elif kind == "MEMORY_SOURCE" and target in nodes:
            add(target, claim_for(source), "DERIVED_FROM")
        elif kind == "DESCRIBES" and source in nodes and target in nodes:
            add(target, source, "SUPPORTED_BY")
        elif kind == "DEPENDS_ON" and source in nodes and target in nodes:
            add(target, source, "DEPENDS_ON")
    return list(nodes.values()), list(edges.values())


@dataclass(frozen=True)
class KairosImpactResult:
    affected_decisions: frozenset[str]
    unaffected_decisions: frozenset[str]
    impacted_memories: frozenset[str]
    latency_ms: float


class KairosAPIAdapter:
    """Exercise verified site-scoped drift routes with an explicit bearer identity."""

    def __init__(self, transport: Transport, token: str, site_id: str) -> None:
        if not token or not site_id.startswith("EDB_BENCH_") or len(site_id) > 64 or not site_id.replace("_", "").isalnum():
            raise ValueError("Explicit token and EDB_BENCH_ site id are required")
        self.transport, self.token, self.site_id = transport, token, site_id

    def preflight(self) -> dict[str, Any]:
        user = _object(self.transport("GET", "/auth/me", None, self.token), "user")
        if user.get("role") not in {"engineer", "reliability"} or user.get("site_id") != self.site_id:
            raise KairosAPIError("Test identity must be site-bound engineer or reliability; admin and bypass identities are refused")
        if user.get("user_id") in {None, "", "dev-user", "service-kairos-connector"}:
            raise KairosAPIError("Verified non-bypass test user id is required")
        health = _object(self.transport("GET", "/drift/health", None, self.token), "drift health")
        if health.get("reachable") is not True or health.get("site_graph_exists") is not False:
            raise KairosAPIError("Test graph must be reachable and absent before writes")
        return {"identity_verified": True, "role": user["role"], "site_id": self.site_id}

    def load_scenario(self, scenario: dict[str, Any]) -> set[str]:
        nodes, edges = build_impact_graph(scenario)
        for node in nodes:
            response = _object(self.transport("POST", f"/drift/nodes/{self.site_id}", node, self.token), "node response")
            if response.get("node_id") != node["node_id"] or response.get("label") != node["label"] or response.get("status") != "created":
                raise KairosAPIError("Node create response does not match request")
        for edge in edges:
            response = _object(self.transport("POST", f"/drift/edges/{self.site_id}", edge, self.token), "edge response")
            if any(response.get(key) != edge[key] for key in ("source_id", "target_id", "relationship")) or response.get("status") != "linked":
                raise KairosAPIError("Edge create response does not match request")
        return {node["node_id"] for node in nodes}

    def evaluate(self, scenario: dict[str, Any], known_ids: set[str]) -> KairosImpactResult:
        started = time.perf_counter_ns()
        response = self.transport("POST", f"/drift/impact/{self.site_id}",
                                  {"changed_ids": [scenario["source_evidence_id"]]}, self.token)
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        impacted = parse_impact(response, self.site_id, known_ids, scenario["source_evidence_id"])
        decisions = {node["id"] for node in scenario["nodes"] if node["kind"] == "decision" and node["tenant_id"] == scenario["tenant_id"]}
        memories = set(scenario["expected_memory_ids"])
        return KairosImpactResult(frozenset(impacted & decisions), frozenset(decisions - impacted),
                                  frozenset(impacted & memories), latency_ms)

    def check_foreign_site_denial(self, foreign_token: str) -> bool:
        foreign = _object(self.transport("GET", "/auth/me", None, foreign_token), "foreign user")
        if foreign.get("role") not in {"engineer", "reliability"} or foreign.get("site_id") in {None, self.site_id}:
            raise KairosAPIError("Foreign test token must belong to another site-bound staff user")
        try:
            self.transport("POST", f"/drift/impact/{self.site_id}", {"changed_ids": []}, foreign_token)
        except KairosAPIError as exc:
            if exc.status_code == 403:
                return True
            raise
        return False
