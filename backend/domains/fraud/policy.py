"""Freeze policy. Pure logic, no database access, so it can be unit-tested and reviewed on its own.

Rules
  1. Only STRONG links count (shared device or card). Shared-IP-only accounts never join a freeze.
  2. The candidate set (flagged account + strong-link members) must reach MIN_RING_SIZE accounts.
  3. The proposal is only ever a PROPOSED action. A human approves it through the API.
"""
from domains.fraud import config


def decide_freeze(seed_account: str, members: list[dict]) -> dict | None:
    targets = sorted({seed_account} | {m["account_id"] for m in members})
    if len(targets) < config.MIN_RING_SIZE:
        return None
    max_hops = max((m["hops"] for m in members), default=0)
    rule = (f"{len(targets)} accounts linked by shared device or card "
            f"(up to {max_hops} account-hops from {seed_account}); IP-only links excluded")
    evidence = [{"account_id": m["account_id"], "hops": m["hops"], "path": m["path"]}
                for m in members[:5]]
    return {"targets": targets, "rule": rule, "evidence": evidence}
