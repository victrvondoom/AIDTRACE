"""Kairos adapter for the migrated GreenChain engines.

Everything numeric here comes from GreenChain's own code (`_enrich_manufacturer`, `compute_composite_scores`,
`rescore_transport`: CatBoost-first q10/q50/q90 (legacy XGBoost supported), USEEIO, Ember, ND-GAIN, GLEC). This module only (1) supplies a clearly
labelled ILLUSTRATIVE candidate set for demo mode, (2) turns scored results into a Graph Lab graph and persists it
in FalkorDB, and (3) re-ranks when a supplier or an input dataset is removed.

Demo candidates are NOT real suppliers and their certifications are NOT verified evidence. Live discovery
(`/greenchain/search`) needs the Dedalus and search keys and is reported NOT_CONNECTED without them.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

# Reference datasets ship inside backend/ (the Docker build context); the integrations copy is the fallback.
_HERE = Path(__file__).resolve().parent
_DEFAULT_DATA = _HERE / "data" if (_HERE / "data").is_dir() else _HERE.parents[2] / "integrations" / "greenchain" / "data"
os.environ.setdefault("GREENCHAIN_DATA_DIR", str(_DEFAULT_DATA))  # must precede the ml_runtime imports below

from . import main as gc  # noqa: E402
from .ml_scorer import compute_composite_scores  # noqa: E402
from .naics_classifier import classify_naics  # noqa: E402

DEMO_NOTICE = ("Illustrative candidates for demonstration. They are not real suppliers, and their certifications are "
               "not verified evidence. Emissions are modelled intensities, not factory-specific measurements.")
DATASETS = {  # public reference data behind every estimate: id -> (label, version note)
    "USEEIO": ("EPA USEEIO v1.3 supply-chain factors", "v1.3 (USD 2022)"),
    "EMBER": ("Ember electricity grid intensity", "yearly release"),
    "GLEC": ("GLEC transport emission factors", "framework default factors"),
    "NDGAIN": ("ND-GAIN climate vulnerability", "2023"),
}
_DEMO = [  # name, country, certifications, revenue USD m, renewable share, disclosure
    ("Illustrative Packaging A", "VN", ["iso14001"], 30, 0.20, "none"),
    ("Illustrative Packaging B", "DE", ["iso14001", "cdp_a"], 80, 0.60, "cdp"),
    ("Illustrative Packaging C", "MX", ["iso14001"], 45, 0.30, "none"),
    ("Illustrative Packaging D", "PT", ["iso14001", "cdp_b"], 55, 0.55, "cdp"),
    ("Illustrative Packaging E", "CN", [], 120, 0.10, "none"),
]
_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


def _id(prefix: str, value: str) -> str:
    return f"{prefix}:{_SAFE.sub('_', value.strip())[:90]}"


def demo_candidates() -> list[dict[str, Any]]:
    # The last entry plays the incumbent supplier; the rest are alternatives for the same component.
    return [{"name": n, "country": c, "certifications": list(certs), "disclosure_status": d, "component": "Corrugated packaging",
             "is_current": n == _DEMO[-1][0], "emission_factor": {"revenue_usd_m": rev, "renewable_pct": ren}}
            for n, c, certs, rev, ren, d in _DEMO]


def apply_factor_revision(enriched: list[dict[str, Any]], revision: dict[str, Any] | None) -> None:
    """Scale the modelled manufacturing emissions of every supplier in `revision["country"]` by `revision["factor"]`.

    This is a COUNTERFACTUAL for "an emission factor was revised": the caller states the country and the factor, and the real
    composite scorer then re-ranks. It is not a claim that any published dataset changed by that amount."""
    if not revision:
        return
    country, factor = str(revision["country"]).upper(), float(revision["factor"])
    for r in enriched:
        if str(r.get("country", "")).upper() != country:
            continue
        ef = r.get("emission_factor") or {}
        for key in ("q10_tco2e", "q50_tco2e", "q90_tco2e"):
            if ef.get(key) is not None:
                ef[key] = float(ef[key]) * factor


def score_candidates(raw: list[dict[str, Any]], *, product: str = "cardboard packaging", destination: str = "US",
                     transport_mode: str = "sea", quantity: int = 10_000, weights: dict[str, float] | None = None,
                     revision: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Enrich (real ML + reference lookups) then rank (real composite scorer). Deterministic for a given input."""
    industry = classify_naics(product)
    weight = gc._shipment_weight_kg(quantity)
    mode = gc._normalise_transport_mode(transport_mode)
    enriched = [r for r in (gc._enrich_manufacturer(c, destination=destination.upper(), transport_mode=mode, weight_kg=weight,
                                                    industry=industry) for c in raw) if r is not None]
    apply_factor_revision(enriched, revision)
    return compute_composite_scores(enriched, transport_mode=mode, weights=gc._normalise_weights(weights))


def demo_scenario(*, transport_mode: str = "sea", weights: dict[str, float] | None = None) -> dict[str, Any]:
    scored = score_candidates(demo_candidates(), transport_mode=transport_mode, weights=weights)
    return {"mode": "ILLUSTRATIVE_DEMO", "notice": DEMO_NOTICE, "product": "cardboard packaging", "destination": "US",
            "transport_mode": transport_mode, "results": scored}


def rank_without(raw: list[dict[str, Any]], removed: str, **kwargs: Any) -> dict[str, Any]:
    """What changes if `removed` leaves the candidate pool? Both rankings come from the same scorer."""
    before = score_candidates(raw, **kwargs)
    after = score_candidates([c for c in raw if c.get("name") != removed], **kwargs) if len(raw) > 1 else []
    rank_before = {r["name"]: r["rank"] for r in before}
    return {"removed": removed, "top_before": before[0]["name"] if before else None, "top_after": after[0]["name"] if after else None,
            "recommendation_changes": bool(before and after and before[0]["name"] != after[0]["name"]),
            "rank_changes": [{"name": r["name"], "from": rank_before.get(r["name"]), "to": r["rank"]} for r in after
                             if rank_before.get(r["name"]) != r["rank"]]}


def scenario_graph(scored: list[dict[str, Any]], *, scenario_id: str = "greenchain-demo", product: str = "cardboard packaging") -> dict[str, Any]:
    """Graph Lab graph, edges `dependent -> dependency`: Decision -> Supplier -> {Certification, Country, Estimate -> Dataset}."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(nid: str, kind: str, label: str, **props: Any) -> str:
        nodes.setdefault(nid, {"id": nid, "type": kind, "label": label[:80], "props": props})
        return nid

    def edge(src: str, dst: str, rel: str, **extra: Any) -> None:
        edges.append({"source": src, "target": dst, "rel": rel, "weight": 1, **extra})

    scen = node(_id("scenario", scenario_id), "Scenario", f"Sourcing: {product}", product=product)
    for ds, (label, version) in DATASETS.items():
        node(_id("dataset", ds), "Dataset", label, version=version, status="CURRENT")
    if scored:
        top = scored[0]
        decision = node(_id("decision", scenario_id), "Decision", f"Recommend {top['name']}", status="PROPOSED", recommended=top["name"])
        edge(decision, scen, "DECIDES")
    for r in scored:
        sup = node(_id("supplier", r["name"]), "Supplier", r["name"], rank=r.get("rank"), env_rating=r.get("env_rating"),
                   total_tco2e=(r.get("scores") or {}).get("total_tco2e"), country=r.get("country"))
        edge(sup, scen, "QUOTES_FOR")
        if r.get("rank") == 1 and scored:
            edge(_id("decision", scenario_id), sup, "RECOMMENDS")
        edge(sup, node(_id("country", r.get("country", "??")), "Country", r.get("country", "??")), "LOCATED_IN")
        for cert in r.get("certifications") or []:
            cid = node(_id("cert", f"{r['name']}-{cert}"), "Certification", cert, status="UNVERIFIED", verification="UNVERIFIED")
            edge(sup, cid, "HOLDS", certainty="maybe")  # claimed, not verified, so impact through it is only possible
        ef = r.get("emission_factor") or {}
        est = node(_id("estimate", r["name"]), "Estimate", f"{r['name']} emissions", q10=ef.get("q10_tco2e"), q50=ef.get("q50_tco2e"),
                   q90=ef.get("q90_tco2e"), basis="MODELLED_NOT_MEASURED")
        edge(sup, est, "ESTIMATED_BY")
        for ds in ("USEEIO", "EMBER", "GLEC", "NDGAIN"):
            edge(est, _id("dataset", ds), "BASED_ON")
    return {"nodes": list(nodes.values()), "edges": edges}


_LABELS = {"Scenario", "Decision", "Supplier", "Country", "Certification", "Estimate", "Dataset"}
_RELS = {"DECIDES", "QUOTES_FOR", "RECOMMENDS", "LOCATED_IN", "HOLDS", "ESTIMATED_BY", "BASED_ON"}


def persist_graph(store: Any, graph: dict[str, Any]) -> dict[str, int]:
    """Write a scenario graph into a tenant-scoped FalkorDB graph (labels and relationships are allow-listed)."""
    by_label: dict[str, list[dict]] = {}
    for n in graph["nodes"]:
        if n["type"] not in _LABELS:
            raise ValueError(f"unsupported node type: {n['type']}")
        props = {k: v for k, v in n["props"].items() if isinstance(v, (str, int, float, bool))}
        by_label.setdefault(n["type"], []).append({"id": n["id"], "label": n["label"], **props})
    for label, rows in by_label.items():
        store.query(f"UNWIND $rows AS r MERGE (n:{label} {{id: r.id}}) SET n += r", {"rows": rows})
    index = {n["id"]: n["type"] for n in graph["nodes"]}
    by_rel: dict[tuple[str, str, str], list[dict]] = {}
    for e in graph["edges"]:
        if e["rel"] not in _RELS:
            raise ValueError(f"unsupported relationship: {e['rel']}")
        by_rel.setdefault((index[e["source"]], e["rel"], index[e["target"]]), []).append(
            {"a": e["source"], "b": e["target"], "certainty": e.get("certainty", "definite")})
    for (sl, rel, dl), rows in by_rel.items():
        store.query(f"UNWIND $rows AS r MATCH (a:{sl} {{id: r.a}}) MATCH (b:{dl} {{id: r.b}}) MERGE (a)-[x:{rel}]->(b) SET x.certainty = r.certainty",
                    {"rows": rows})
    return {"nodes": len(graph["nodes"]), "edges": len(graph["edges"])}


def read_graph(store: Any) -> dict[str, Any]:
    nodes = [{"id": r[0], "type": r[1][0], "label": r[2] or r[0], "props": {k: v for k, v in (r[3] or {}).items()
                                                                              if k not in ("id", "label") and isinstance(v, (str, int, float, bool))}}
             for r in store.query("MATCH (n) RETURN n.id, labels(n), n.label, properties(n)")]
    edges = [{"source": r[0], "target": r[1], "rel": r[2], "weight": 1, "certainty": r[3] or "definite"}
             for r in store.query("MATCH (a)-[x]->(b) RETURN a.id, b.id, type(x), x.certainty")]
    return {"nodes": nodes, "edges": edges}


def deep_copy(value: Any) -> Any:  # tiny helper so callers never mutate cached demo payloads
    return copy.deepcopy(value)
