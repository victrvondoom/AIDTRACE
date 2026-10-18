"""RESOLVE consumer module: proof checks against a live FalkorDB on the separate test graph.

Maps to the directive's proof list (numbers in the test docstrings):
  1 multi-domain routing, 2 cross-domain dependency, 3 missing document flips the strategy,
  4 contradictory source blocks, 5 relationship change changes the plan, 6 stale approval invalidated,
  7 FalkorDB removal gives no decision, 9 citation semantics, 10 API runs end to end.
"""
import json
import os
from pathlib import Path

import pytest

from api.services.consumer import actions, case_data, citations, engine, graphdb, simulate
from api.services.consumer.evaluate import SCENARIOS, _graph_scenario, _score

requires_falkordb = pytest.mark.skipif(not os.getenv("FALKORDB_TEST_URL"), reason="set FALKORDB_TEST_URL")

TEST_GRAPH = "resolve_test_consumer"
CONSUMER_DIR = Path(__file__).resolve().parents[1] / "api" / "services" / "consumer"


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("FALKORDB_URL", os.environ.get("FALKORDB_TEST_URL", "redis://127.0.0.1:1"))
    s = graphdb.open_store(graph_name=TEST_GRAPH)
    graphdb.write_case(s, case_data.build_case())
    yield s
    s.reset_synthetic_graph()


def _verdicts(result):
    return {v["strategy_id"]: v["verdict"] for v in result["verdicts"]}


# ---------- pure citation semantics (no database) ----------

def test_citation_requires_exact_condition_text_not_word_overlap():
    rule = {"condition_text": "pay only the amount not already refunded by the carrier", "source_id": "S"}
    sources = {"S": {"verified": True, "jurisdiction": "SYNTHETIC", "effective_date": "2026-01-01",
                     "excerpt": "We pay only the amount not already refunded by the carrier."}}
    assert citations.check_rule(rule, sources, set(), "2026-10-02", "SYNTHETIC") == []
    # Same words, different proposition: the carrier pays only the refunded amount.
    sources["S"]["excerpt"] = "We pay the carrier only the amount already refunded to the insured."
    assert "EXCERPT_MISMATCH" in citations.check_rule(rule, sources, set(), "2026-10-02", "SYNTHETIC")


def test_citation_reports_each_failed_property():
    rule = {"condition_text": "x y z", "source_id": "S"}
    sources = {"S": {"verified": False, "jurisdiction": "OTHER", "effective_date": "2027-01-01", "excerpt": "x y z"}}
    problems = citations.check_rule(rule, sources, {"SRC-7"}, "2026-10-02", "SYNTHETIC")
    assert problems == ["UNVERIFIED_SOURCE", "JURISDICTION_MISMATCH", "NOT_IN_FORCE", "SOURCE_CONFLICT"]


def test_normalize_unifies_quotes_and_punctuation():
    assert citations.normalize("Carrier’s  notice,”") == citations.normalize("carrier's notice")


def test_consumer_module_has_no_other_database():
    """Proof 7 (static part): the decision path never imports a second store."""
    forbidden = ("neo4j", "qdrant", "jsonl", "supabase", "redis")
    for path in CONSUMER_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for name in forbidden:
            assert f"import {name}" not in text and f"from {name}" not in text, f"{path.name} imports {name}"


# ---------- graph-dependent behaviour ----------

@requires_falkordb
def test_one_complaint_routes_to_three_specialists(store):
    """Proof 1: three domains, three specialists, each reporting."""
    result = engine.analyze(store)
    assert result["status"] == "OK"
    assert [s["domain"] for s in result["specialists"]] == ["DOM-AIR", "DOM-BKG", "DOM-INS"]
    assert all(s["local_view"] for s in result["specialists"])


@requires_falkordb
def test_graph_finds_dependency_that_single_domain_views_miss(store):
    """Proof 2: EVD-2 is needed by the insurance AND hotel strategies. No single specialist sees both."""
    result = engine.analyze(store)
    shared = {s["evidence_id"]: s for s in result["cross_domain"]["shared_evidence"]}
    assert set(shared["EVD-2"]["domains"]) == {"Booking and payments", "Travel insurance"}
    insurance = next(s for s in result["specialists"] if s["domain"] == "DOM-INS")
    assert {r["remedy_id"] for r in insurance["local_view"]} == {"REM-INS-FULL", "REM-INS-NET"}
    assert "REM-HOT-REFUND" not in json.dumps(insurance)
    dep = next(d for d in result["cross_domain"]["dependencies"] if d["condition"] == "CND-NET-CLM2")
    assert dep["depends_on"].startswith("EV-2")


@requires_falkordb
def test_missing_document_changes_strategy_and_ranks_first(store):
    """Proof 3: base case is INSUFFICIENT; attaching the carrier notice verifies two strategies."""
    base = engine.analyze(store)
    assert _verdicts(base)["STR-B"] == "INSUFFICIENT_EVIDENCE"
    assert base["plan"]["status"] == "NO_VERIFIED_STRATEGY"
    assert base["evidence_gaps"][0]["item_id"] == "EVD-2"
    assert base["evidence_gaps"][0]["verified_gain"] == 2
    graphdb.set_evidence_status(store, "EVD-2", "PRESENT")
    after = engine.analyze(store)
    assert _verdicts(after)["STR-B"] == "VERIFIED"
    assert _verdicts(after)["STR-D"] == "VERIFIED"
    assert after["plan"]["draft_strategy_id"] == "STR-B"
    assert after["plan"]["status"] == "NEEDS_USER_DECISION"


@requires_falkordb
def test_contradiction_rejects_claim_that_ignores_refund(store):
    """Proof 4a: the original claim (700) ignores the 240 refund; the graph expects 460. Rejected, never proposed."""
    result = engine.analyze(store)
    verdict = next(v for v in result["verdicts"] if v["strategy_id"] == "STR-A")
    assert verdict["verdict"] == "REJECTED"
    assert any("CLM-1 claims 700.00" in r and "460.00" in r for r in verdict["reasons"])
    assert "STR-A" not in result["plan"]["verified"]


@requires_falkordb
def test_contradictory_verified_source_blocks_conclusion(store):
    """Proof 4b: a verified insurer FAQ says the notice is NOT required. The insurance strategy is blocked."""
    graphdb.write_case(store, case_data.build_case({"evidence_status": {"EVD-2": "PRESENT"}, "add_sources": True}))
    result = engine.analyze(store)
    verdict = next(v for v in result["verdicts"] if v["strategy_id"] == "STR-B")
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert verdict["blocked_by"] == "SOURCE_CONFLICT"
    assert _verdicts(result)["STR-D"] == "VERIFIED"


@requires_falkordb
def test_placeholder_excerpt_stays_blocked_even_when_flagged_verified(store):
    """Proof 9: flagging the airline source verified does not make an unrelated placeholder citable."""
    graphdb.write_case(store, case_data.build_case({"source_verified": {"SRC-4": True}}))
    result = engine.analyze(store)
    verdict = next(v for v in result["verdicts"] if v["strategy_id"] == "STR-C")
    assert verdict["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert any("EXCERPT_MISMATCH" in r for r in verdict["reasons"])


@requires_falkordb
def test_modifying_a_relationship_changes_the_resolution(store):
    """Proof 5: removing the REFUNDS link (a data correction) flips the full-claim strategy to VERIFIED."""
    before = engine.analyze(store)
    assert _verdicts(before)["STR-A"] == "REJECTED"
    removed = graphdb.drop_decision_edge(store, "Evidence", "EVD-3", "REFUNDS", "Evidence", "EVD-1")
    assert removed == 1
    graphdb.set_evidence_status(store, "EVD-2", "PRESENT")
    after = engine.analyze(store)
    assert _verdicts(after)["STR-A"] == "VERIFIED"


@requires_falkordb
def test_stale_approval_is_invalidated_by_evidence_change(store):
    """Proof 6: approval binds to the revision; changing evidence afterwards invalidates it."""
    graphdb.set_evidence_status(store, "EVD-2", "PRESENT")
    result = engine.analyze(store)
    draft = result["draft"]
    assert draft and draft["strategy_id"] == "STR-B"
    approved = actions.approve(store, draft["action_id"], result["revision"])
    assert approved["status"] == "APPROVED_LOCAL"
    assert approved["external_submission"] == "disabled"
    graphdb.set_evidence_status(store, "EVD-3", "MISSING")
    assert actions.status_of(store, draft["action_id"])["status"] == "INVALIDATED"
    stale = actions.approve(store, draft["action_id"], result["revision"])
    assert stale["error"] == "STALE_REVISION"


@requires_falkordb
def test_what_if_runs_do_not_change_the_live_graph(store):
    """Simulation runs in an isolated graph and leaves the live revision untouched."""
    before = graphdb.compute_revision(store)["revision"]
    simulate.run_hypothesis(store, {"evidence_status": {"EVD-2": "PRESENT"}})
    assert graphdb.compute_revision(store)["revision"] == before
    assert store.query("MATCH (e:Evidence {id: 'EVD-2'}) RETURN e.status")[0][0] == "MISSING"


@requires_falkordb
def test_independent_cypher_check_agrees_with_verifier(store):
    graphdb.set_evidence_status(store, "EVD-2", "PRESENT")
    result = engine.analyze(store)
    assert result["independent_check"] == {"agrees": True, "mismatches": []}


@requires_falkordb
def test_scenario_expectations_hold_for_graph_and_baseline():
    """The evaluation labels are hand-written; the engine must meet them (S2 and S4 cover flip and block)."""
    for sc in [s for s in SCENARIOS if s["id"] in ("S2", "S4")]:
        ours, base = _graph_scenario(sc)
        score = _score(sc, ours, base)
        assert score["ours"]["verdict_accuracy"] == 1.0, sc["id"]
        assert score["ours"]["plan_matches_expected"], sc["id"]
        assert score["ours"]["unsupported_recommendations"] == 0


def test_falkordb_removal_gives_no_decision():
    """Proof 7: an unreachable FalkorDB raises GraphUnavailable. The engine never falls back."""
    with pytest.raises(graphdb.GraphUnavailable):
        graphdb.open_store(graph_name=TEST_GRAPH, url="redis://127.0.0.1:6399")




@requires_falkordb
def test_rerunning_analysis_keeps_a_valid_draft(store):
    """Re-running on an unchanged revision must not replace the draft the reviewer is looking at."""
    graphdb.set_evidence_status(store, "EVD-2", "PRESENT")
    first = engine.analyze(store)["draft"]
    second = engine.analyze(store)["draft"]
    assert first["action_id"] == second["action_id"]
    assert "Requested remedy: Amend insurance claim to net amount." in first["body"]


# ---------- native Kairos router: shared session, tenant-scoped graph, authenticated reviewer ----------

def _client(role="engineer", site="site_cons_test", user_id="u-reviewer"):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.dependencies import get_current_user, get_settings
    from api.routers.consumer import router
    app = FastAPI()
    app.include_router(router, prefix="/resolveai/consumer")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": user_id, "role": role, "site_id": site}
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(FALKORDB_URL=os.environ["FALKORDB_TEST_URL"])
    return TestClient(app)


@requires_falkordb
def test_router_runs_end_to_end_with_authenticated_reviewer_and_invalidates_stale_approval():
    c = _client()
    try:
        assert c.post("/resolveai/consumer/case/load", json={"overrides": {}}).status_code == 200
        assert c.post("/resolveai/consumer/evidence?evidence_id=EVD-2", json={"status": "PRESENT"}).status_code == 200
        run = c.post("/resolveai/consumer/analyze").json()
        assert run["status"] == "OK"
        graph = c.get("/resolveai/consumer/graph").json()["graph"]
        assert graph["nodes"] and graph["edges"]
        aid = run["draft"]["action_id"]
        ok = c.post(f"/resolveai/consumer/actions/approve?action_id={aid}", json={"revision": run["revision"], "reviewer": "forged"})
        assert ok.status_code == 200 and ok.json()["status"] == "APPROVED_LOCAL"
        from api.services.consumer.store import GraphStore as _GS
        props = str(_GS(os.environ["FALKORDB_TEST_URL"], "resolve_consumer_site_cons_test").query("MATCH (a:ProposedAction {id: $i}) RETURN properties(a)", {"i": aid}))
        assert "u-reviewer" in props and "forged" not in props  # the reviewer is the session user, not a client field
        c.post("/resolveai/consumer/evidence?evidence_id=EVD-3", json={"status": "MISSING"})
        listed = {a["action_id"]: a for a in c.get("/resolveai/consumer/actions").json()["actions"]}
        assert listed[aid]["status"] == "INVALIDATED"
        assert c.post(f"/resolveai/consumer/actions/approve?action_id={aid}", json={"revision": run["revision"]}).status_code == 409
    finally:
        _client().post("/resolveai/consumer/case/load", json={"overrides": {}})
        from api.services.consumer.store import GraphStore
        GraphStore(os.environ["FALKORDB_TEST_URL"], "resolve_consumer_site_cons_test").reset_synthetic_graph()


@requires_falkordb
def test_router_graphs_are_tenant_scoped_and_staff_only():
    a, b = _client(site="site_cons_a"), _client(site="site_cons_b")
    try:
        a.post("/resolveai/consumer/case/load", json={"overrides": {}})
        assert a.get("/resolveai/consumer/health").json()["case_loaded"] is True
        assert b.get("/resolveai/consumer/health").json()["case_loaded"] is False  # another site's graph is untouched
        assert _client(role="field_worker").get("/resolveai/consumer/state").status_code == 403
        assert _client(role="field_worker").post("/resolveai/consumer/analyze").status_code == 403
    finally:
        from api.services.consumer.store import GraphStore
        GraphStore(os.environ["FALKORDB_TEST_URL"], "resolve_consumer_site_cons_a").reset_synthetic_graph()
