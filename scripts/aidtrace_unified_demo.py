"""Run the existing Evidence Drift and coordination modules in a fresh FalkorDB namespace.

Set AIDTRACE_DEMO_FALKORDB_URL to a disposable local/test FalkorDB instance. The script refuses
to use FALKORDB_URL and will not reuse an existing generated graph namespace.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from uuid import uuid4
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.services.coordination.coordinator import CoordinatorAgent
from api.services.coordination.graph_store import CoordinationGraphStore
from api.services.drift.demo_workflow import run_evidence_supersession
from api.services.drift.store import FalkorDriftStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", help="Optional unique suffix for this isolated demo graph")
    args = parser.parse_args()
    url = os.environ.get("AIDTRACE_DEMO_FALKORDB_URL", "").strip()
    if not url:
        print("Set AIDTRACE_DEMO_FALKORDB_URL to a disposable local/test FalkorDB URL. FALKORDB_URL is intentionally not used.", file=sys.stderr)
        return 2

    namespace = (args.namespace or uuid4().hex[:16]).strip()
    if not namespace or len(namespace) > 32 or not namespace.replace("-", "").replace("_", "").isalnum():
        print("Namespace must contain 1-32 letters, numbers, underscores, or hyphens.", file=sys.stderr)
        return 2
    site_id = f"aidtrace_demo_{namespace}"
    graph_prefix = f"aidtrace_demo_{namespace}"
    drift = FalkorDriftStore(url, graph_prefix=graph_prefix)
    try:
        readiness = drift.inspect_site(site_id)
        if readiness["site_graph_exists"]:
            print("Refusing to reuse an existing demo graph. Choose a new --namespace.", file=sys.stderr)
            return 2

        drift_result = run_evidence_supersession(drift, site_id)
        coordination_store = CoordinationGraphStore(drift_store=drift, site_id=site_id)
        coordinator = CoordinatorAgent(coordination_store)
        run = coordinator.plan_investigation(
            goal="Check synthetic source-version IDs and report current industrial adapter readiness.",
            domain="industrial",
            site_id=site_id,
            context_ids=[drift_result["source_before"], drift_result["source_after"]],
        )
        execution = coordinator.execute_investigation(run.run_id)
        evidence_task = next(task for task in execution["tasks"]
                             if task["capability_id"] == "core.graph_evidence_lookup")
        summary_task = next(task for task in execution["tasks"]
                            if task["capability_id"] == "core.deterministic_summary")

        summary = {
            "demo_data": "synthetic only",
            "backend": "FalkorDB",
            "graph_isolated": True,
            "source_supersession": drift_result["authority_verdict"],
            "affected_paths": len(drift_result["impact_paths"]),
            "prior_approval_matches_current_revision": drift_result["human_review"]["matches_current_revision"],
            "action_eligibility": drift_result["action_eligibility"],
            "coordination": {
                "workers": 2,
                "task_count": len(execution["tasks"]),
                "event_count": execution["event_count"],
                "evidence_ids_present": len(evidence_task["result_data"]["found"]),
                "evidence_ids_missing": len(evidence_task["result_data"]["missing_ids"]),
                "domain_analysis_performed": execution["domain_analysis_performed"],
                "domain_adapter_outcome": summary_task["result_data"]["outcome"],
            },
            "limitations": [
                "The synthetic drift case validates existing source invalidation and revision-bound approval behavior only.",
                "Coordination checks graph node presence and registry readiness; it does not perform industrial diagnosis.",
                "The generated isolated graph is retained for inspection and is not automatically deleted.",
            ],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if drift_result["action_eligibility"] == "SUSPENDED" else 1
    finally:
        drift.close()


if __name__ == "__main__":
    raise SystemExit(main())
