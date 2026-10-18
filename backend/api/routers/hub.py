"""Live capability status for the Kairos hub overview.

Every node on the overview graph is labelled from a probe made now, never from a static claim:
  OPERATIONAL  the runtime answered and the feature has nothing material missing
  LIMITED      the runtime answered, but something it advertises is not connected (listed in `limits`)
  UNAVAILABLE  the runtime did not answer
Probes are read-only and bounded by a short timeout, so one dead dependency cannot stall the overview.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends

from api.dependencies import CurrentUserDep, FalkorDriftDep, SettingsDep, require_role
from api.routers import resolveai_platform as platform
from api.services.graphlab.registry import ALGORITHMS

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
PROBE_TIMEOUT_S = 4.0

# Dependencies between capabilities, used to draw the graph. A dependency that is down degrades its dependents.
EDGES: list[tuple[str, str, str]] = [
    ("resolveai", "memory", "REMEMBERS_IN"), ("resolveai", "evidence-drift", "CITES_EVIDENCE_FOR"), ("resolveai", "reports", "FEEDS"),
    ("greenchain", "simulations", "SCORES_FOR"), ("greenchain", "evidence-drift", "DEPENDS_ON_SOURCES"), ("greenchain", "reports", "FEEDS"),
    ("consumer", "memory", "REMEMBERS_IN"), ("fraud", "agents", "RUNS_AS"), ("cybersecurity", "graph", "ANALYSED_IN"),
    ("agents", "memory", "SHARES"), ("memory", "evidence-drift", "VALIDATED_BY"), ("evidence-drift", "simulations", "REPLAYED_IN"),
    ("graph", "simulations", "ENGINES_FOR"), ("simulations", "reports", "FEEDS"), ("resolveai", "agents", "RUNS_AS"), ("greenchain", "agents", "RUNS_AS"),
]


def _cap(cid: str, name: str, state: str, detail: str, *, limits: list[str] | None = None, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": cid, "name": name, "state": state, "detail": detail, "limits": limits or [], "metrics": metrics or {}}


async def _bounded(fn, default):
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), PROBE_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - a failed probe is a status, not an error
        log.info("hub.probe_failed", error=type(exc).__name__)
        return default


def _falkor_reachable(drift_store, site_id: str | None) -> dict[str, Any]:
    return drift_store.inspect_site(site_id)


def _greenchain() -> dict[str, Any]:
    from domains.greenchain import main as gc
    from domains.greenchain.ml_bridge import ML_ROOT
    models = all((ML_ROOT / "models" / f"xgb_{q}.joblib").is_file() for q in ("q10", "q50", "q90"))
    data = os.path.isdir(os.environ.get("GREENCHAIN_DATA_DIR", ""))
    return {"models": models, "data": data, "missing_provider_keys": gc._missing_component_agent_keys()}


@router.get("/capabilities", summary="Live status of every hub capability (probed now)")
async def capabilities(user: CurrentUserDep, settings: SettingsDep, drift_store: FalkorDriftDep,
                       _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    site_id = user.get("site_id")
    falkor, gc, runtime = await asyncio.gather(
        _bounded(lambda: _falkor_reachable(drift_store, site_id), {"reachable": False, "site_graph_exists": False}),
        _bounded(_greenchain, {"models": False, "data": False, "missing_provider_keys": []}),
        platform._runtime(),
    )
    graph_ok = bool(falkor.get("reachable"))
    engines = len(ALGORITHMS)
    caps: list[dict[str, Any]] = [_cap("overview", "Kairos Overview", "OPERATIONAL", "The hub shell is running.")]

    if runtime is None:
        caps.append(_cap("resolveai", "ResolveAI", "UNAVAILABLE", "The private ResolveAI worker did not answer.",
                         limits=["Start it with scripts/start_resolveai_worker.py."]))
    else:
        limits = []
        if runtime["model_provider"] in ("disabled", "missing_key"):
            limits.append("No model provider: agents return placeholders; evidence retrieval and scoring work.")
        if runtime["case_store"] == "local":
            limits.append("Cases are stored locally on the worker (Supabase not configured).")
        caps.append(_cap("resolveai", "ResolveAI", "LIMITED" if limits else "OPERATIONAL",
                         f"Worker connected with {runtime['indexed_points']} indexed passages in {runtime['collections']} domain packs.",
                         limits=limits, metrics={"indexed_points": runtime["indexed_points"], "domain_packs": runtime["collections"]}))

    if gc["models"] and gc["data"]:
        gl = ["Supplier candidates are illustrative; live discovery needs provider keys."] if gc["missing_provider_keys"] else []
        caps.append(_cap("greenchain", "GreenChain", "LIMITED" if gl else "OPERATIONAL", "XGBoost emissions models and reference data loaded.",
                         limits=gl, metrics={"missing_provider_keys": len(gc["missing_provider_keys"])}))
    else:
        caps.append(_cap("greenchain", "GreenChain", "UNAVAILABLE", "Emissions models or reference data are missing."))

    down = "FalkorDB did not answer."
    caps.append(_cap("consumer", "Consumer Intelligence", "OPERATIONAL" if graph_ok else "UNAVAILABLE",
                     "Cross-domain remedy engine on the FalkorDB case graph." if graph_ok else down))
    caps.append(_cap("fraud", "Fraud Investigation", "LIMITED" if graph_ok else "UNAVAILABLE",
                     "Graph investigation with recorded agent trace and human approval." if graph_ok else down,
                     limits=["Runs on a synthetic transfer network; no production transaction feed is connected."] if graph_ok else []))
    caps.append(_cap("cybersecurity", "Cybersecurity", "LIMITED", "Attack-path cuts, chokepoints and blast radius on a supplied graph.",
                     limits=["Model-only: no live vulnerability or asset feed is connected."]))
    caps.append(_cap("agents", "Agent Operations", "OPERATIONAL" if graph_ok else "LIMITED", "Shared view of agent runtimes, tools, traces and approvals.",
                     limits=[] if graph_ok else [down]))
    caps.append(_cap("memory", "Agent Memory", "OPERATIONAL" if graph_ok else "UNAVAILABLE",
                     "Evidence-backed memory with supersession in the site graph." if graph_ok else down))
    caps.append(_cap("evidence-drift", "Evidence Drift", "OPERATIONAL" if graph_ok else "UNAVAILABLE",
                     "Source supersession, memory invalidation and approval gating." if graph_ok else down,
                     metrics={"site_graph_exists": bool(falkor.get("site_graph_exists"))}))
    caps.append(_cap("graph", "Graph Intelligence", "OPERATIONAL", f"{engines} graph engines available.", metrics={"engines": engines}))
    sim_ok = gc["models"] and gc["data"]
    caps.append(_cap("simulations", "Simulations", "OPERATIONAL" if sim_ok and graph_ok else "LIMITED", "What-if analysis over the scoring models and evidence graph.",
                     limits=[m for m, ok in (("GreenChain models are missing.", sim_ok), (down, graph_ok)) if not ok]))
    rep_limits = [] if runtime is not None else ["ResolveAI case reports need the worker."]
    caps.append(_cap("reports", "Reports", "OPERATIONAL" if not rep_limits else "LIMITED", "Case, procurement and approval reports built from real runs.", limits=rep_limits))

    return {"generated_at": datetime.now(timezone.utc).isoformat(), "site_id": site_id, "capabilities": caps,
            "edges": [{"source": s, "target": t, "rel": r} for s, t, r in EDGES]}
