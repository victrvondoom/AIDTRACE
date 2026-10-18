"""Synthetic fraud-network generator. Plants known rings so the investigation can be checked.

Run:  python -m domains.fraud.seed     (rebuilds the synthetic graph namespace)
Writes ground truth to backend/data/ground_truth.json for tests and the demo "expected vs actual".

Planted structure
  RING_A  5 accounts sharing one device; two of them also share a card.       (should be found)
  RING_B  4 accounts in a CHAIN: B1-device-B2-card-B3-device-B4.               (needs 6 hops; should be found)
  DECOY   2 accounts (a household) that share only an IP address.             (must NOT be frozen)
  NORMAL  60 accounts, unique device/card, with light random IP sharing.      (noise)
"""
import json
import random
from datetime import UTC, datetime, timedelta

from domains.fraud import config
from domains.fraud.store import GraphStore

SEED = 42


def build_dataset(rng: random.Random) -> dict:
    accounts, devices, cards, ips, links, txns = [], [], [], [], [], []
    truth = {"rings": {}, "decoy": [], "flagged_transactions": []}
    start = datetime(2026, 10, 1, tzinfo=UTC)

    def add_account(acc_id: str, name: str):
        accounts.append({"id": acc_id, "name": name, "status": "ACTIVE"})

    def link(acc: str, rel: str, target: str):
        links.append({"a": acc, "rel": rel, "t": target})

    def txn(txn_id: str, acc: str, amount: float, flagged: bool, minutes: int):
        txns.append({"id": txn_id, "from": acc, "amount": amount, "flagged": flagged,
                     "ts": (start + timedelta(minutes=minutes)).isoformat()})

    # RING_A — shared device, plus a shared card between two members
    ring_a = [f"RA{i}" for i in range(1, 6)]
    for acc in ring_a:
        add_account(acc, f"Ring A member {acc}")
        link(acc, "USED_DEVICE", "DEV-RA")
    devices.append({"id": "DEV-RA"})
    cards.append({"id": "CARD-RA"})
    link("RA1", "OWNS_CARD", "CARD-RA")
    link("RA2", "OWNS_CARD", "CARD-RA")
    truth["rings"]["RING_A"] = ring_a
    flagged_a = "TX-RA-001"
    txn(flagged_a, "RA3", 4_820.00, True, 60)
    truth["flagged_transactions"].append({"id": flagged_a, "account": "RA3", "ring": "RING_A"})

    # RING_B — chain of shared devices and cards, so only a multi-hop walk connects B1 to B4
    ring_b = [f"RB{i}" for i in range(1, 5)]
    for acc in ring_b:
        add_account(acc, f"Ring B member {acc}")
    devices.extend([{"id": "DEV-RB1"}, {"id": "DEV-RB2"}])
    cards.append({"id": "CARD-RB2"})
    link("RB1", "USED_DEVICE", "DEV-RB1")
    link("RB2", "USED_DEVICE", "DEV-RB1")
    link("RB2", "OWNS_CARD", "CARD-RB2")
    link("RB3", "OWNS_CARD", "CARD-RB2")
    link("RB3", "USED_DEVICE", "DEV-RB2")
    link("RB4", "USED_DEVICE", "DEV-RB2")
    truth["rings"]["RING_B"] = ring_b
    flagged_b = "TX-RB-001"
    txn(flagged_b, "RB1", 9_150.00, True, 90)
    truth["flagged_transactions"].append({"id": flagged_b, "account": "RB1", "ring": "RING_B"})

    # DECOY — household on one IP. Weak signal only; must be excluded from any freeze.
    decoy = ["HH1", "HH2"]
    for acc in decoy:
        add_account(acc, f"Household {acc}")
    ips.append({"addr": "203.0.113.10"})
    for acc in decoy:
        link(acc, "LOGGED_FROM", "203.0.113.10")
    truth["decoy"] = decoy
    txn("TX-HH-001", "HH1", 42.50, False, 30)

    # NORMAL — noise
    normal = [f"N{i:02d}" for i in range(1, 61)]
    for acc in normal:
        add_account(acc, f"Customer {acc}")
        dev, card = f"DEV-{acc}", f"CARD-{acc}"
        ip = f"198.51.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        devices.append({"id": dev})
        cards.append({"id": card})
        ips.append({"addr": ip})
        link(acc, "USED_DEVICE", dev)
        link(acc, "OWNS_CARD", card)
        link(acc, "LOGGED_FROM", ip)
    for i in range(12):  # occasional shared public IP between two normal customers
        a, b = rng.sample(normal, 2)
        shared = f"203.0.113.{100 + i}"
        ips.append({"addr": shared})
        link(a, "LOGGED_FROM", shared)
        link(b, "LOGGED_FROM", shared)
    for i in range(40):
        acc = rng.choice(normal)
        txn(f"TX-N-{i:03d}", acc, round(rng.uniform(5, 400), 2), False, 10 + i * 7)

    return {"accounts": accounts, "devices": devices, "cards": cards, "ips": ips,
            "links": links, "txns": txns, "truth": truth}


def load(store: GraphStore, data: dict) -> dict:
    store.reset_synthetic_graph()
    store.query("CREATE INDEX FOR (a:Account) ON (a.id)")
    store.query("UNWIND $rows AS r CREATE (:Account {id: r.id, name: r.name, status: r.status})",
                {"rows": data["accounts"]})
    store.query("UNWIND $rows AS r CREATE (:Device {id: r.id})", {"rows": data["devices"]})
    store.query("UNWIND $rows AS r CREATE (:Card {id: r.id})", {"rows": data["cards"]})
    store.query("UNWIND $rows AS r CREATE (:IP {addr: r.addr})", {"rows": data["ips"]})
    for rel, label, key in [
        ("USED_DEVICE", "Device", "id"),
        ("OWNS_CARD", "Card", "id"),
        ("LOGGED_FROM", "IP", "addr"),
    ]:
        rows = [link for link in data["links"] if link["rel"] == rel]
        store.query(
            f"UNWIND $rows AS r MATCH (a:Account {{id: r.a}}) MATCH (t:{label} {{{key}: r.t}}) "
            f"CREATE (a)-[:{rel}]->(t)",
            {"rows": rows},
        )
    store.query(
        "UNWIND $rows AS r MATCH (a:Account {id: r.from}) "
        "CREATE (t:Transaction {id: r.id, amount: r.amount, ts: r.ts, flagged: r.flagged})-[:FROM]->(a)",
        {"rows": data["txns"]},
    )
    return {
        "accounts": len(data["accounts"]), "devices": len(data["devices"]),
        "cards": len(data["cards"]), "ips": len(data["ips"]),
        "links": len(data["links"]), "transactions": len(data["txns"]),
    }


def main() -> None:
    data = build_dataset(random.Random(SEED))
    store = GraphStore()
    counts = load(store, data)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "ground_truth.json").write_text(json.dumps(data["truth"], indent=2))
    print(f"Seeded graph '{store.graph_name}': {counts}")
    print(f"Ground truth written to {config.DATA_DIR / 'ground_truth.json'}")


if __name__ == "__main__":
    main()
