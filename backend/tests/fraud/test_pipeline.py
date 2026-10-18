"""End-to-end checks against a real FalkorDB instance, on the separate test graph.

Each assertion compares what the agent finds with the planted ground truth from graph/seed.py.
"""
import random

import pytest

from domains.fraud import actions
from domains.fraud.investigator import Investigator
from domains.fraud.tools import GraphTools
from domains.fraud import seed
from domains.fraud.store import GraphStore
import os
requires_falkordb = pytest.mark.skipif(not os.getenv("FALKORDB_TEST_URL"), reason="set FALKORDB_TEST_URL")

pytestmark = requires_falkordb


@pytest.fixture(scope="module")
def world():
    store = GraphStore(url=os.environ.get("FALKORDB_TEST_URL", "redis://127.0.0.1:1"), graph_name="fraud_test_pipeline")
    data = seed.build_dataset(random.Random(seed.SEED))
    seed.load(store, data)
    return {"store": store, "tools": GraphTools(store), "truth": data["truth"]}


def _member_ids(members):
    return sorted(m["account_id"] for m in members)


def test_ring_a_is_found_from_the_flagged_account(world):
    ring_a = world["truth"]["rings"]["RING_A"]
    members = world["tools"].ring_members("RA3")
    assert _member_ids(members) == sorted(a for a in ring_a if a != "RA3")


def test_ring_b_chain_needs_multi_hop_walk(world):
    members = {m["account_id"]: m for m in world["tools"].ring_members("RB1")}
    assert set(members) == {"RB2", "RB3", "RB4"}
    # RB1 -> RB4 crosses three shared nodes (device, card, device): three account-hops.
    assert members["RB4"]["hops"] == 3
    assert members["RB2"]["hops"] == 1


def test_household_decoy_has_only_weak_links(world):
    assert world["tools"].ring_members("HH1") == []
    weak = [w["account_id"] for w in world["tools"].weak_links("HH1")]
    assert weak == ["HH2"]


def test_propose_freeze_matches_planted_ring(world):
    result = world["tools"].propose_freeze("RA3", run_id="test-ring-a")
    assert "proposed" in result, result
    assert result["proposed"]["targets"] == sorted(world["truth"]["rings"]["RING_A"])
    assert result["proposed"]["status"] == "PROPOSED"


def test_propose_freeze_refuses_household_decoy(world):
    result = world["tools"].propose_freeze("HH1", run_id="test-decoy")
    assert "rejected" in result
    assert "proposed" not in result


def test_deterministic_investigation_proposes_both_rings_and_never_the_decoy(world):
    events = []
    tools = GraphTools(world["store"], recorder=lambda rec: events.append({"type": "query", **rec}))
    Investigator(tools, events.append, run_id="test-run").run(use_llm=False)
    proposals = [e["action"]["targets"] for e in events if e["type"] == "proposal"]
    flat = {acc for targets in proposals for acc in targets}
    assert set(world["truth"]["rings"]["RING_A"]) <= flat
    assert set(world["truth"]["rings"]["RING_B"]) <= flat
    assert not (set(world["truth"]["decoy"]) & flat)
    assert events[-1]["type"] == "done" and events[-1]["mode"] == "deterministic"
    assert any(e["type"] == "query" for e in events), "every graph query must be recorded for the trace"


def test_approval_executes_once_and_writes_a_receipt(world):
    store, tools = world["store"], world["tools"]
    action = tools.propose_freeze("RB1", run_id="test-approve")["proposed"]
    done = actions.approve(store, action["action_id"])
    assert done["status"] == "EXECUTED"
    assert done["frozen_accounts"] == sorted(world["truth"]["rings"]["RING_B"])
    assert len(done["receipt"]) == 64
    frozen = store.query("MATCH (a:Account) WHERE a.id IN $ids RETURN a.status",
                         {"ids": done["frozen_accounts"]})
    assert all(row[0] == "FROZEN" for row in frozen)
    again = actions.approve(store, action["action_id"])
    assert "error" in again
