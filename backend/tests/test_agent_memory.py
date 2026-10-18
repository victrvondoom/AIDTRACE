"""Evidence-aware agent memory against real FalkorDB (disposable graphs, synthetic ids)."""
from __future__ import annotations

import os
import uuid

import pytest

from api.services.drift.model import ContractError
from api.services.drift.store import FalkorDriftStore
from api.services.memory.agent_memory import AgentMemory


@pytest.fixture
def mem():
    url = os.getenv("FALKORDB_TEST_URL")
    if not url:
        pytest.skip("set FALKORDB_TEST_URL to run FalkorDB integration coverage")
    store = FalkorDriftStore(url, graph_prefix=f"pytest_{uuid.uuid4().hex[:12]}", query_timeout_ms=5000, max_depth=10)
    sites = [f"site_{uuid.uuid4().hex[:8]}", f"site_{uuid.uuid4().hex[:8]}"]
    try:
        yield AgentMemory(store, sites[0]), AgentMemory(store, sites[1]), store
    finally:
        for s in sites:
            if store.graph_name(s) in store._client.list_graphs():
                store._graph(s).delete()
        store.close()


def seed(m: AgentMemory) -> None:
    """Two independent branches: price (source A) and emissions (source B). Only the price branch is superseded in most tests."""
    for letter in ("A", "B"):
        m.record_source(document_id=f"doc-{letter}", source_id=f"src-{letter}-v1", title=f"Dataset {letter}", authority_level=3, confidence=0.9, content_sha256=f"sha-{letter}")
        m.record_claim(claim_id=f"claim-{letter}-v1", source_id=f"src-{letter}-v1", fact_key=f"fact_{letter}", fact_value=100)
        m.register_agent(f"agent-{letter}", f"Agent {letter}")
        m.remember(memory_id=f"mem-{letter}", agent_id=f"agent-{letter}", kind="SEMANTIC", summary=f"Fact {letter} is 100", claim_ids=[f"claim-{letter}-v1"])
    m.propose_decision(decision_id="dec-A", summary="Choose supplier on fact A", memory_ids=["mem-A"], claim_ids=[],
                       conditions=[{"key": "fact_A", "op": ">=", "value": 50, "material": True}], plan_id="plan-A", plan_summary="Plan", action_id="act-A", action_summary="Order")
    m.propose_decision(decision_id="dec-B", summary="Choose on fact B", memory_ids=["mem-B"], claim_ids=[],
                       conditions=[{"key": "fact_B", "op": ">=", "value": 50, "material": True}], plan_id="plan-B", plan_summary="Plan", action_id="act-B", action_summary="Order")


NEW_A = {"document_id": "doc-A", "source_id": "src-A-v2", "title": "Dataset A", "authority_level": 2, "confidence": 0.95, "version_label": "v2"}


def test_agents_share_memory_and_recall_records_what_influenced_them(mem) -> None:
    a, _, _ = mem
    seed(a)
    got = a.recall(agent_id="agent-B", fact_key="fact_A")
    assert [u["id"] for u in got["usable"]] == ["mem-A"] and got["blocked"] == []
    assert got["influenced_by"] == ["mem-A"] and got["usable"][0]["sources"][0]["id"] == "src-A-v1"
    assert any(e["rel"] == "RECALLED_IN" for e in a.store.edges_of(a.site, "mem-A")["out"])


def test_copies_of_one_source_are_not_independent_corroboration(mem) -> None:
    a, _, _ = mem
    for sid in ("copy-1", "copy-2"):
        a.record_source(document_id=f"doc-{sid}", source_id=sid, title="Mirror", content_sha256="same-bytes")
        a.record_claim(claim_id=f"c-{sid}", source_id=sid, fact_key="k", fact_value=1)
    a.register_agent("ag", "Agent")
    out = a.remember(memory_id="m1", agent_id="ag", kind="SEMANTIC", summary="k is 1", claim_ids=["c-copy-1", "c-copy-2"])
    assert out["independent_sources"] == 1


def test_superseding_a_source_marks_only_its_dependants_and_blocks_recall(mem) -> None:
    a, _, store = mem
    seed(a)
    result = a.supersede_source(old_source_id="src-A-v1", new_source=NEW_A, new_claims=[{"claim_id": "claim-A-v2", "fact_key": "fact_A", "fact_value": 40, "replaces": "claim-A-v1"}], change_id="chg-1")
    by_id = {x["id"]: x for x in result["invalidated"]}
    assert result["verdict"] == "REPLACE"
    assert by_id["mem-A"]["after"] == "STALE" and by_id["dec-A"]["after"] == "STALE" and by_id["plan-A"]["after"] == "STALE"
    assert by_id["claim-A-v1"]["after"] == "SUPERSEDED"
    assert set(by_id) == {"claim-A-v1", "mem-A", "dec-A", "plan-A", "act-A"}  # nothing from branch B
    assert store.read_node(a.site, "mem-B")["properties"]["status"] == "VALID"
    assert store.read_node(a.site, "act-B")["properties"]["status"] == "PENDING"
    got = a.recall(agent_id="agent-B", fact_key="fact_A")
    assert got["usable"] == [] and got["blocked"][0]["blocked_reason"]
    assert [u["id"] for u in a.recall(agent_id="agent-A", fact_key="fact_B")["usable"]] == ["mem-B"]


def test_a_stale_decision_cannot_be_approved_and_says_why(mem) -> None:
    a, _, _ = mem
    seed(a)
    assert a.approve_action("act-A", "reviewer@example")["approved"] is True
    a.supersede_source(old_source_id="src-A-v1", new_source=NEW_A, new_claims=[{"claim_id": "claim-A-v2", "fact_key": "fact_A", "fact_value": 40, "replaces": "claim-A-v1"}], change_id="chg-2")
    state = a.eligibility("act-A")
    assert state["eligible"] is False and state["approval_current"] is False
    assert any("STALE" in r for r in state["reasons"])
    refused = a.approve_action("act-A", "reviewer@example")
    assert refused["approved"] is False and refused["reasons"]
    assert a.store.read_node(a.site, "act-A")["properties"]["status"] == "SUSPENDED"


def test_reevaluation_produces_a_new_revision_that_needs_a_fresh_approval(mem) -> None:
    a, _, store = mem
    seed(a)
    first = a.approve_action("act-A", "reviewer@example")
    a.supersede_source(old_source_id="src-A-v1", new_source=NEW_A, new_claims=[{"claim_id": "claim-A-v2", "fact_key": "fact_A", "fact_value": 120, "replaces": "claim-A-v1"}], change_id="chg-3")
    a.remember(memory_id="mem-A2", agent_id="agent-A", kind="SEMANTIC", summary="Fact A is now 120", claim_ids=["claim-A-v2"])
    out = a.reevaluate_decision(decision_id="dec-A", new_dependency_ids=["mem-A2"], current_facts={"fact_A": ("claim-A-v2", 120)}, reason="Dataset A revised")
    assert out["status"] == "VALID" and out["revision"]["revision_n"] == 2
    assert a.eligibility("act-A")["eligible"] is True
    assert a.eligibility("act-A")["approval_current"] is False  # the old approval pinned revision 1
    second = a.approve_action("act-A", "reviewer@example")
    assert second["approved"] is True and second["graph_revision"] != first["graph_revision"]
    assert a.eligibility("act-A")["approval_current"] is True
    # a later change to the same dependency would make that approval unusable again
    store.update_node_properties(a.site, "Memory", "mem-A2", {"status": "STALE"})
    assert a.eligibility("act-A")["eligible"] is False


def test_a_decision_whose_conditions_no_longer_hold_is_invalidated(mem) -> None:
    a, _, _ = mem
    seed(a)
    a.supersede_source(old_source_id="src-A-v1", new_source=NEW_A, new_claims=[{"claim_id": "claim-A-v2", "fact_key": "fact_A", "fact_value": 40, "replaces": "claim-A-v1"}], change_id="chg-4")
    a.remember(memory_id="mem-A2", agent_id="agent-A", kind="SEMANTIC", summary="Fact A is now 40", claim_ids=["claim-A-v2"])
    out = a.reevaluate_decision(decision_id="dec-A", new_dependency_ids=["mem-A2"], current_facts={"fact_A": ("claim-A-v2", 40)}, reason="Dataset A revised")
    assert out["status"] == "INVALIDATED" and a.eligibility("act-A")["eligible"] is False


def test_a_weaker_or_unverified_source_contests_but_never_replaces(mem) -> None:
    a, _, store = mem
    seed(a)
    weak = {**NEW_A, "source_id": "src-A-weak", "authority_level": 5}
    out = a.supersede_source(old_source_id="src-A-v1", new_source=weak, new_claims=[], change_id="chg-5")
    assert out["verdict"] == "CONTEST" and out["invalidated"] == []
    unverified = {**NEW_A, "source_id": "src-A-unv", "verification": "UNVERIFIED"}
    assert a.supersede_source(old_source_id="src-A-v1", new_source=unverified, new_claims=[], change_id="chg-6")["verdict"] == "CONTEST"
    assert store.read_node(a.site, "mem-A")["properties"]["status"] == "VALID"
    low = {**NEW_A, "source_id": "src-A-low", "confidence": 0.3}
    assert a.supersede_source(old_source_id="src-A-v1", new_source=low, new_claims=[], change_id="chg-7")["verdict"] == "REJECT"


def test_the_same_change_twice_has_no_second_effect(mem) -> None:
    a, _, _ = mem
    seed(a)
    args = dict(old_source_id="src-A-v1", new_source=NEW_A, new_claims=[{"claim_id": "claim-A-v2", "fact_key": "fact_A", "fact_value": 40, "replaces": "claim-A-v1"}], change_id="chg-8")
    first = a.supersede_source(**args)
    again = a.supersede_source(**args)
    assert again["duplicate"] is True and again["invalidated"] == first["invalidated"]


def test_memory_derived_from_memory_is_reached_transitively_and_cycles_terminate(mem) -> None:
    a, _, _ = mem
    seed(a)
    a.remember(memory_id="mem-A-derived", agent_id="agent-B", kind="EPISODIC", summary="B reused A's fact", from_memories=["mem-A"])
    a.store.link(a.site, "Memory", "mem-A", "DERIVED_FROM", "Memory", "mem-A-derived")  # a deliberate cycle
    result = a.supersede_source(old_source_id="src-A-v1", new_source=NEW_A, new_claims=[], change_id="chg-9")
    assert "mem-A-derived" in {x["id"] for x in result["invalidated"]}


def test_nothing_can_be_remembered_from_a_superseded_claim(mem) -> None:
    a, _, _ = mem
    seed(a)
    a.supersede_source(old_source_id="src-A-v1", new_source=NEW_A, new_claims=[], change_id="chg-10")
    with pytest.raises(ContractError, match="not ACTIVE"):
        a.remember(memory_id="late", agent_id="agent-A", kind="SEMANTIC", summary="x", claim_ids=["claim-A-v1"])


def test_sites_never_see_each_others_memory(mem) -> None:
    a, b, _ = mem
    seed(a)
    assert b.recall(agent_id="x", fact_key="fact_A")["usable"] == []
    assert b.snapshot()["memories"] == []
    assert len(a.snapshot()["memories"]) == 2


INVESTIGATION = {"mode": "retrieval_only", "llm_used": False, "evidence": [
    {"title": "IRDAI Master Circular", "authority": "IRDAI", "retrieved_chunk": "Claims shall be settled within 30 days of the last document.", "confidence": 0.58, "chunk_id": "k1", "evidence_scores": {"authority_score": 1.0}},
    {"title": "IRDAI Master Circular (mirror)", "authority": "IRDAI", "retrieved_chunk": "Claims  shall be settled within"
                                                                                            " 30 days of the last document.", "confidence": 0.55, "chunk_id": "k2", "evidence_scores": {"authority_score": 1.0}},
    {"title": "Policy wording", "authority": "Unknown", "retrieved_chunk": "Pre-existing disease waiting period is 48 months.", "confidence": 0.49, "chunk_id": "k3", "evidence_scores": {"authority_score": 0.5}},
]}


def test_a_resolveai_investigation_becomes_memory_another_agent_can_recall_until_its_source_changes(mem) -> None:
    from api.services.memory.resolveai_memory import remember_investigation

    a, _, _ = mem
    out = remember_investigation(a, case_id="case-1", institution="Acme Health", domain="health_insurance", investigation=INVESTIGATION)
    assert out["remembered"] is True
    assert len(out["claims"]) == 2  # the mirrored passage is one source, not two
    assert out["independent_sources"] == 2 and out["verified"] is False  # one passage has no known authority
    recalled = a.recall(agent_id="agent:greenchain-scorer", fact_key="evidence_for_case:case-1")
    assert [m["id"] for m in recalled["usable"]] == [out["memory_id"]]
    assert {h["recalled_by"] for h in a.handoffs()} == {"agent:greenchain-scorer"}
    assert a.handoffs()[0]["produced_by"] == "agent:resolveai-investigator" and a.handoffs()[0]["usable"] is True

    source_id = next(s["id"] for s in recalled["usable"][0]["sources"] if s["document_id"] == "ra:doc:IRDAI_Master_Circular")
    a.supersede_source(old_source_id=source_id, change_id="chg-ra", new_source={"document_id": "ra:doc:IRDAI_Master_Circular", "source_id": "ra:src:v2", "title": "IRDAI Master Circular 2026",
                                                                                 "authority_level": 1, "confidence": 0.99}, new_claims=[])
    after = a.recall(agent_id="agent:fraud-investigator", fact_key="evidence_for_case:case-1")
    assert after["usable"] == [] and after["blocked"][0]["id"] == out["memory_id"]
    assert [h["usable"] for h in a.handoffs()] == [False]


def test_an_investigation_with_no_evidence_remembers_nothing(mem) -> None:
    from api.services.memory.resolveai_memory import remember_investigation

    a, _, _ = mem
    out = remember_investigation(a, case_id="case-2", institution="x", domain="banking", investigation={"evidence": []})
    assert out["remembered"] is False and a.snapshot()["memories"] == []
