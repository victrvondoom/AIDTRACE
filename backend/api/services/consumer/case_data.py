"""Synthetic consumer case for RESOLVE remedy investigation (Graph Hacks, Track 01, FalkorDB).

Everything here is invented for testing: people, institutions, policy clauses, amounts and dates.
Policy and terms excerpts are SYNTHETIC FIXTURES that stand in for documents the user would supply.
A source with verified=False is a placeholder, and nothing in the system treats it as law.

build_case(overrides) returns plain Python lists so the same case can be written to the main
consumer graph, or to an isolated what-if graph (see simulate.py), without any drift between them.

Overrides understood:
  evidence_status:   {"EVD-2": "PRESENT"}           change an evidence item's status
  source_verified:   {"SRC-4": True}                 flip a source's verified flag
  drop_edges:        [["Evidence","EVD-3","REFUNDS","Evidence","EVD-1"]]   remove a relationship
  add_sources:       True                            add the conflicting insurer FAQ (SRC-7)
"""
import copy

CASE_ID = "CASE-001"
JURISDICTION = "SYNTHETIC"
EVENT_DATE = "2026-10-02"
COMPLAINT = (
    "My flight was cancelled. The airline refunded part of the ticket, my travel insurer rejected "
    "the claim, and I am still being charged for the hotel, which was non-refundable."
)

POLICY_EXCERPT = (
    "Travel cancellation cover. We pay only the amount not already refunded by the carrier. "
    "A cancellation claim requires the carrier's written cancellation notice, which must be attached."
)
HOTEL_EXCERPT = (
    "Non-refundable rate. Refund only where the guest provides the carrier's written cancellation notice."
)
AIRLINE_PLACEHOLDER = "NO OFFICIAL SOURCE ATTACHED. Placeholder: the refund rule text has not been verified."
CONFLICT_EXCERPT = (
    "Travel cancellation cover. Claims do not require the carrier's written cancellation notice."
)


def _nodes(ov: dict) -> list[tuple[str, dict]]:
    ev = {"EVD-1": "PRESENT", "EVD-2": "MISSING", "EVD-3": "PRESENT", "EVD-4": "PRESENT",
          "EVD-5": "PRESENT", "EVD-6": "PRESENT"}
    ev.update(ov.get("evidence_status", {}))
    ver = {"SRC-1": True, "SRC-3": True, "SRC-4": False}
    ver.update(ov.get("source_verified", {}))

    nodes: list[tuple[str, dict]] = [
        ("CitizenCase", {"id": CASE_ID, "title": "Cancelled flight, partial refund, rejected claim, "
                                                  "non-refundable hotel (synthetic)",
                         "jurisdiction": JURISDICTION, "event_date": EVENT_DATE, "complaint": COMPLAINT}),
        ("Domain", {"id": "DOM-AIR", "name": "Airline"}),
        ("Domain", {"id": "DOM-INS", "name": "Travel insurance"}),
        ("Domain", {"id": "DOM-BKG", "name": "Booking and payments"}),
        ("Institution", {"id": "INS-AIR", "name": "Skyway Air (synthetic)", "kind": "airline"}),
        ("Institution", {"id": "INS-TRV", "name": "Harbor Travel Insurance (synthetic)", "kind": "insurer"}),
        ("Institution", {"id": "INS-HTL", "name": "StayFast Hotels (synthetic)", "kind": "booking"}),
        ("Event", {"id": "EV-1", "type": "CARRIER_CANCELLATION", "date": "2026-10-02", "amount": 0.0}),
        ("Event", {"id": "EV-2", "type": "REFUND_PAYMENT", "date": "2026-10-03", "amount": 240.0}),
        ("Event", {"id": "EV-3", "type": "CLAIM_SUBMITTED", "date": "2026-10-04", "amount": 0.0}),
        ("Event", {"id": "EV-4", "type": "CLAIM_REJECTED", "date": "2026-10-06", "amount": 0.0}),
        ("Event", {"id": "EV-5", "type": "HOTEL_CHARGE", "date": "2026-10-01", "amount": 300.0}),
        ("Claim", {"id": "CLM-1", "amount": 700.0, "status": "REJECTED", "basis": "as submitted"}),
        ("Claim", {"id": "CLM-2", "amount": 460.0, "status": "DRAFT", "basis": "amended, refund deducted"}),
        ("Evidence", {"id": "EVD-1", "type": "TICKET_RECEIPT", "amount": 400.0, "status": ev["EVD-1"]}),
        ("Evidence", {"id": "EVD-2", "type": "CARRIER_CANCELLATION_NOTICE", "amount": 0.0,
                      "status": ev["EVD-2"]}),
        ("Evidence", {"id": "EVD-3", "type": "REFUND_STATEMENT", "amount": 240.0, "status": ev["EVD-3"]}),
        ("Evidence", {"id": "EVD-4", "type": "INSURER_REJECTION_LETTER", "amount": 0.0, "status": ev["EVD-4"]}),
        ("Evidence", {"id": "EVD-5", "type": "HOTEL_BOOKING_TERMS", "amount": 0.0, "status": ev["EVD-5"]}),
        ("Evidence", {"id": "EVD-6", "type": "HOTEL_CHARGE_STATEMENT", "amount": 300.0, "status": ev["EVD-6"]}),
        ("Source", {"id": "SRC-1", "title": "Travel cancellation policy wording (synthetic)",
                    "kind": "POLICY_WORDING", "jurisdiction": JURISDICTION, "effective_date": "2026-01-01",
                    "verified": ver["SRC-1"], "excerpt": POLICY_EXCERPT}),
        ("Source", {"id": "SRC-3", "title": "Hotel booking terms (synthetic)", "kind": "HOTEL_TERMS",
                    "jurisdiction": JURISDICTION, "effective_date": "2026-01-01",
                    "verified": ver["SRC-3"], "excerpt": HOTEL_EXCERPT}),
        ("Source", {"id": "SRC-4", "title": "Airline refund rule (not yet sourced)", "kind": "REFUND_RULE",
                    "jurisdiction": JURISDICTION, "effective_date": "",
                    "verified": ver["SRC-4"], "excerpt": AIRLINE_PLACEHOLDER}),
        ("Rule", {"id": "RUL-INS-1", "text": "Insurer pays only the amount not already refunded by the carrier",
                  "condition_text": "pay only the amount not already refunded by the carrier",
                  "source_id": "SRC-1"}),
        ("Rule", {"id": "RUL-INS-2", "text": "Cancellation claim requires the carrier's written cancellation notice",
                  "condition_text": "requires the carrier's written cancellation notice",
                  "source_id": "SRC-1"}),
        ("Rule", {"id": "RUL-HOT-1", "text": "Hotel refund only where the carrier's written cancellation notice is provided",
                  "condition_text": "refund only where the guest provides the carrier's written cancellation notice",
                  "source_id": "SRC-3"}),
        ("Rule", {"id": "RUL-AIR-1", "text": "Carrier must refund unused fare on cancellation",
                  "condition_text": "unused fare on cancellation", "source_id": "SRC-4"}),
        ("Obligation", {"id": "OBL-AIR", "description": "Airline refund of unused fare"}),
        ("Obligation", {"id": "OBL-INS", "description": "Insurer assessment of cancellation claim"}),
        ("Obligation", {"id": "OBL-HOT", "description": "Hotel treatment of non-refundable charge"}),
        ("Condition", {"id": "CND-TICKET", "text": "Ticket receipt on file", "check": "evidence"}),
        ("Condition", {"id": "CND-REFUND-DOC", "text": "Carrier refund amount documented", "check": "evidence"}),
        ("Condition", {"id": "CND-NOTICE-INS", "text": "Carrier cancellation notice for insurer",
                       "check": "evidence"}),
        ("Condition", {"id": "CND-NOTICE-HOT", "text": "Carrier cancellation notice for hotel",
                       "check": "evidence"}),
        ("Condition", {"id": "CND-HOTEL-DOC", "text": "Hotel terms and charge statement on file",
                       "check": "evidence"}),
        ("Condition", {"id": "CND-NET-CLM1", "text": "Claim as submitted excludes refunded fare",
                       "check": "claim_net"}),
        ("Condition", {"id": "CND-NET-CLM2", "text": "Amended claim excludes refunded fare",
                       "check": "claim_net"}),
        ("Condition", {"id": "CND-AIR-RULE", "text": "Airline refund entitlement verified against a source",
                       "check": "rule_only"}),
        ("Remedy", {"id": "REM-INS-FULL", "title": "Resubmit original claim in full"}),
        ("Remedy", {"id": "REM-INS-NET", "title": "Amend insurance claim to net amount"}),
        ("Remedy", {"id": "REM-AIR-TOPUP", "title": "Request airline top-up of refund"}),
        ("Remedy", {"id": "REM-HOT-REFUND", "title": "Request hotel refund for cancelled trip"}),
        ("Strategy", {"id": "STR-A", "title": "Resubmit full claim now"}),
        ("Strategy", {"id": "STR-B", "title": "Amend insurance claim to net amount"}),
        ("Strategy", {"id": "STR-C", "title": "Airline top-up request"}),
        ("Strategy", {"id": "STR-D", "title": "Hotel refund request"}),
    ]
    if ov.get("add_sources"):
        nodes.append(("Source", {"id": "SRC-7", "title": "Insurer FAQ (synthetic, conflicting)",
                                 "kind": "FAQ", "jurisdiction": JURISDICTION, "effective_date": "2026-03-01",
                                 "verified": True, "excerpt": CONFLICT_EXCERPT}))
    return nodes


def _edges(ov: dict) -> list[tuple[str, str, str, str, str]]:
    edges = [
        ("CitizenCase", CASE_ID, "INVOLVES", "Institution", "INS-AIR"),
        ("CitizenCase", CASE_ID, "INVOLVES", "Institution", "INS-TRV"),
        ("CitizenCase", CASE_ID, "INVOLVES", "Institution", "INS-HTL"),
        ("Institution", "INS-AIR", "IN_DOMAIN", "Domain", "DOM-AIR"),
        ("Institution", "INS-TRV", "IN_DOMAIN", "Domain", "DOM-INS"),
        ("Institution", "INS-HTL", "IN_DOMAIN", "Domain", "DOM-BKG"),
        ("Event", "EV-1", "EVIDENCED_BY", "Evidence", "EVD-1"),
        ("Event", "EV-2", "EVIDENCED_BY", "Evidence", "EVD-3"),
        ("Event", "EV-4", "EVIDENCED_BY", "Evidence", "EVD-4"),
        ("Event", "EV-5", "EVIDENCED_BY", "Evidence", "EVD-6"),
        ("Claim", "CLM-1", "INCLUDES", "Evidence", "EVD-1"),
        ("Claim", "CLM-1", "INCLUDES", "Evidence", "EVD-6"),
        ("Claim", "CLM-2", "INCLUDES", "Evidence", "EVD-1"),
        ("Claim", "CLM-2", "INCLUDES", "Evidence", "EVD-6"),
        ("Evidence", "EVD-3", "REFUNDS", "Evidence", "EVD-1"),
        ("Claim", "CLM-1", "FILED_WITH", "Institution", "INS-TRV"),
        ("Claim", "CLM-2", "FILED_WITH", "Institution", "INS-TRV"),
        ("Obligation", "OBL-AIR", "OWED_BY", "Institution", "INS-AIR"),
        ("Obligation", "OBL-AIR", "GOVERNED_BY", "Rule", "RUL-AIR-1"),
        ("Obligation", "OBL-INS", "OWED_BY", "Institution", "INS-TRV"),
        ("Obligation", "OBL-INS", "GOVERNED_BY", "Rule", "RUL-INS-1"),
        ("Obligation", "OBL-INS", "GOVERNED_BY", "Rule", "RUL-INS-2"),
        ("Obligation", "OBL-HOT", "OWED_BY", "Institution", "INS-HTL"),
        ("Obligation", "OBL-HOT", "GOVERNED_BY", "Rule", "RUL-HOT-1"),
        ("Rule", "RUL-INS-1", "CITES", "Source", "SRC-1"),
        ("Rule", "RUL-INS-2", "CITES", "Source", "SRC-1"),
        ("Rule", "RUL-HOT-1", "CITES", "Source", "SRC-3"),
        ("Rule", "RUL-AIR-1", "CITES", "Source", "SRC-4"),
        ("Condition", "CND-TICKET", "REQUIRES_EVIDENCE", "Evidence", "EVD-1"),
        ("Condition", "CND-REFUND-DOC", "REQUIRES_EVIDENCE", "Evidence", "EVD-3"),
        ("Condition", "CND-NOTICE-INS", "REQUIRES_EVIDENCE", "Evidence", "EVD-2"),
        ("Condition", "CND-NOTICE-INS", "GOVERNED_BY", "Rule", "RUL-INS-2"),
        ("Condition", "CND-NOTICE-HOT", "REQUIRES_EVIDENCE", "Evidence", "EVD-2"),
        ("Condition", "CND-NOTICE-HOT", "GOVERNED_BY", "Rule", "RUL-HOT-1"),
        ("Condition", "CND-HOTEL-DOC", "REQUIRES_EVIDENCE", "Evidence", "EVD-5"),
        ("Condition", "CND-HOTEL-DOC", "REQUIRES_EVIDENCE", "Evidence", "EVD-6"),
        ("Condition", "CND-NET-CLM1", "CONCERNS", "Claim", "CLM-1"),
        ("Condition", "CND-NET-CLM1", "GOVERNED_BY", "Rule", "RUL-INS-1"),
        ("Condition", "CND-NET-CLM2", "CONCERNS", "Claim", "CLM-2"),
        ("Condition", "CND-NET-CLM2", "GOVERNED_BY", "Rule", "RUL-INS-1"),
        ("Condition", "CND-NET-CLM2", "DEPENDS_ON", "Event", "EV-2"),
        ("Condition", "CND-AIR-RULE", "GOVERNED_BY", "Rule", "RUL-AIR-1"),
        ("Remedy", "REM-INS-FULL", "IN_DOMAIN", "Domain", "DOM-INS"),
        ("Remedy", "REM-INS-NET", "IN_DOMAIN", "Domain", "DOM-INS"),
        ("Remedy", "REM-AIR-TOPUP", "IN_DOMAIN", "Domain", "DOM-AIR"),
        ("Remedy", "REM-HOT-REFUND", "IN_DOMAIN", "Domain", "DOM-BKG"),
        ("Remedy", "REM-INS-FULL", "CLAIMS_RECOVERY_FOR", "Event", "EV-5"),
        ("Remedy", "REM-INS-NET", "CLAIMS_RECOVERY_FOR", "Event", "EV-5"),
        ("Remedy", "REM-HOT-REFUND", "CLAIMS_RECOVERY_FOR", "Event", "EV-5"),
        ("Remedy", "REM-AIR-TOPUP", "CLAIMS_RECOVERY_FOR", "Event", "EV-1"),
        ("Strategy", "STR-A", "PROPOSES", "Remedy", "REM-INS-FULL"),
        ("Strategy", "STR-B", "PROPOSES", "Remedy", "REM-INS-NET"),
        ("Strategy", "STR-C", "PROPOSES", "Remedy", "REM-AIR-TOPUP"),
        ("Strategy", "STR-D", "PROPOSES", "Remedy", "REM-HOT-REFUND"),
        ("Strategy", "STR-A", "REQUIRES", "Condition", "CND-NET-CLM1"),
        ("Strategy", "STR-A", "REQUIRES", "Condition", "CND-TICKET"),
        ("Strategy", "STR-A", "REQUIRES", "Condition", "CND-NOTICE-INS"),
        ("Strategy", "STR-B", "REQUIRES", "Condition", "CND-NET-CLM2"),
        ("Strategy", "STR-B", "REQUIRES", "Condition", "CND-REFUND-DOC"),
        ("Strategy", "STR-B", "REQUIRES", "Condition", "CND-NOTICE-INS"),
        ("Strategy", "STR-C", "REQUIRES", "Condition", "CND-AIR-RULE"),
        ("Strategy", "STR-C", "REQUIRES", "Condition", "CND-REFUND-DOC"),
        ("Strategy", "STR-C", "REQUIRES", "Condition", "CND-TICKET"),
        ("Strategy", "STR-D", "REQUIRES", "Condition", "CND-NOTICE-HOT"),
        ("Strategy", "STR-D", "REQUIRES", "Condition", "CND-HOTEL-DOC"),
    ]
    if ov.get("add_sources"):
        edges.append(("Source", "SRC-7", "CONTRADICTS", "Rule", "RUL-INS-2"))
    drop = {tuple(e) for e in ov.get("drop_edges", [])}
    return [e for e in edges if e not in drop]


def build_case(overrides: dict | None = None) -> dict:
    ov = copy.deepcopy(overrides or {})
    return {"nodes": _nodes(ov), "edges": _edges(ov)}
