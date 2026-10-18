"""Pure policy tests: no database needed."""
from domains.fraud import policy


def _member(acc: str, hops: int) -> dict:
    return {"account_id": acc, "hops": hops, "path": [], "rels": []}


def test_ring_at_or_above_minimum_is_proposed():
    decision = policy.decide_freeze("RA3", [_member("RA1", 1), _member("RA2", 1)])
    assert decision is not None
    assert decision["targets"] == ["RA1", "RA2", "RA3"]


def test_ring_below_minimum_is_rejected():
    assert policy.decide_freeze("HH1", []) is None


def test_targets_are_unique_and_sorted():
    decision = policy.decide_freeze("RB1", [_member("RB4", 3), _member("RB2", 1), _member("RB1", 1)])
    assert decision["targets"] == ["RB1", "RB2", "RB4"]


def test_rule_text_states_ip_links_are_excluded():
    decision = policy.decide_freeze("RB1", [_member("RB2", 1), _member("RB3", 2)])
    assert "IP-only links excluded" in decision["rule"]
    assert "up to 2 account-hops" in decision["rule"]
