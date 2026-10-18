"""Complaint intake: free text to structured facts, with explicit gaps.

Deterministic on purpose. Nothing here invents an institution name, an amount or a date. Anything it
cannot read is reported under `missing` or `ambiguities`, and the case is not treated as complete.

Scope and limits (also stated in docs/KNOWN_LIMITATIONS.md):
  * English only. Text that is mostly non-Latin is returned as LANGUAGE_UNSUPPORTED, not guessed at.
  * Domain routing uses keyword profiles. Domain profiles marked flow_implemented=False are metadata only.
  * Typo tolerance is fuzzy matching of words of five letters or more against the keyword list (difflib).
"""
import difflib
import re
import unicodedata

# Domain profiles. flow_implemented says whether a complete investigation flow exists in the engine.
DOMAIN_PROFILES = {
    "DOM-AIR": {"name": "Airline and aviation", "flow_implemented": True,
                "keywords": ["flight", "airline", "airfare", "boarding", "carrier", "airport"]},
    "DOM-INS": {"name": "Travel insurance", "flow_implemented": True,
                "keywords": ["insurer", "insurance", "policy", "claim", "premium", "coverage"]},
    "DOM-BKG": {"name": "Booking and payments", "flow_implemented": True,
                "keywords": ["hotel", "booking", "reservation", "charged", "refund", "payment", "invoice"]},
    "DOM-BANK": {"name": "Banking", "flow_implemented": False,
                 "keywords": ["bank", "account", "overdraft", "atm", "debit", "transfer"]},
    "DOM-TEL": {"name": "Telecom", "flow_implemented": False,
                "keywords": ["sim", "mobile", "telecom", "roaming", "network", "phone"]},
    "DOM-HOU": {"name": "Housing and real estate", "flow_implemented": False,
                "keywords": ["landlord", "tenant", "deposit", "flat", "builder", "possession", "lease"]},
    "DOM-HEA": {"name": "Healthcare services", "flow_implemented": False,
                "keywords": ["hospital", "doctor", "clinic", "treatment", "medical", "patient"]},
    "DOM-GOV": {"name": "Government and public services", "flow_implemented": False,
                "keywords": ["government", "department", "permit", "municipal", "pension"]},
    "DOM-ECO": {"name": "E-commerce and purchases", "flow_implemented": False,
                "keywords": ["order", "delivery", "seller", "marketplace", "parcel", "shop"]},
}

CURRENCY = r"(?:\$|€|£|₹|USD|EUR|GBP|INR|dollars?|euros?|rupees?|rs\.?)"
NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
AMOUNT_RE = re.compile(rf"({CURRENCY})\s?({NUMBER})|({NUMBER})\s?({CURRENCY})", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
DAY_MONTH_RE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})\b", re.IGNORECASE)

EVENT_PATTERNS = [
    ("CARRIER_CANCELLATION", re.compile(r"\b(cancel+ed|cancell?ation)\b", re.IGNORECASE)),
    ("PARTIAL_REFUND", re.compile(
        r"\brefund(?:ed)?\s+(?:only\s+)?(?:part|partial(?:ly)?|some)\b|\b(?:partial(?:ly)?|part of)\s+(?:the\s+|my\s+|a\s+)?refund",
        re.IGNORECASE)),
    ("REFUND_RECEIVED", re.compile(r"\brefund(?:ed)?\b", re.IGNORECASE)),
    ("CLAIM_REJECTED", re.compile(r"\b(rejected|denied|declined)\s+(?:the\s+|my\s+|our\s+)?claim\b", re.IGNORECASE)),
    ("CHARGE_OPEN", re.compile(r"\b(still\s+)?(being\s+)?charged\b", re.IGNORECASE)),
]
NON_REFUNDABLE_RE = re.compile(r"\bnon[- ]?refundable\b", re.IGNORECASE)
INSTRUCTION_RE = re.compile(r"\b(ignore (all |previous |the )?(instructions|rules)|approve (all|everything)|"
                            r"submit (this|it|the complaint)|system prompt)\b", re.IGNORECASE)
AMBIGUOUS_RE = re.compile(r"\b(half|a third|a quarter|most of|some of|roughly|around|about)\b", re.IGNORECASE)
INSTITUTION_RE = re.compile(r"\b(?:my|the|our)\s+((?:[a-z]+\s){0,2}?)(airline|insurer|insurance company|hotel|bank|"
                            r"landlord|telecom provider|carrier|booking site|seller|hospital)\b", re.IGNORECASE)
KIND_BY_WORD = {"airline": "airline", "carrier": "airline", "insurer": "insurer", "insurance company": "insurer",
                "hotel": "booking", "booking site": "booking", "bank": "bank", "landlord": "landlord",
                "telecom provider": "telecom", "seller": "seller", "hospital": "healthcare"}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("’", "'")
    return " ".join(text.split())


def _non_latin_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    return 1 - latin / len(letters)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def _domains(text: str) -> list[dict]:
    words = _words(text)
    lowered = text.lower()
    found = []
    for dom_id, profile in DOMAIN_PROFILES.items():
        hits = []
        for keyword in profile["keywords"]:
            if " " in keyword:
                if keyword in lowered:
                    hits.append({"term": keyword, "match": "exact"})
                continue
            if keyword in words:
                hits.append({"term": keyword, "match": "exact"})
                continue
            if len(keyword) >= 5:
                close = difflib.get_close_matches(keyword, words, n=1, cutoff=0.8)
                if close:
                    hits.append({"term": keyword, "match": f"fuzzy:{close[0]}"})
        if hits:
            found.append({"id": dom_id, "name": profile["name"], "evidence_terms": hits,
                          "flow_implemented": profile["flow_implemented"]})
    # "health insurance" is healthcare, not travel insurance. Keep both only if both are named.
    if "health insurance" in lowered:
        found = [d for d in found if d["id"] != "DOM-INS"] + [
            {"id": "DOM-HEA", "name": DOMAIN_PROFILES["DOM-HEA"]["name"], "evidence_terms": [
                {"term": "health insurance", "match": "exact"}], "flow_implemented": False}]
    if ("travel insurance" in lowered or "travel insurer" in lowered) and not any(d["id"] == "DOM-INS" for d in found):
        found.append({"id": "DOM-INS", "name": DOMAIN_PROFILES["DOM-INS"]["name"], "evidence_terms": [
            {"term": "travel insurance", "match": "exact"}], "flow_implemented": True})
    return sorted(found, key=lambda d: d["id"])


def _amounts(text: str) -> list[dict]:
    out = []
    for m in AMOUNT_RE.finditer(text):
        if m.group(1):
            raw, currency = m.group(2), m.group(1)
        else:
            raw, currency = m.group(3), m.group(4)
        out.append({"value": float(raw.replace(",", "")), "currency": currency.strip().lower(),
                    "span": m.group(0)})
    return out


def _dates(text: str) -> list[dict]:
    out = [{"value": m.group(0), "format": "iso"} for m in ISO_DATE_RE.finditer(text)]
    out += [{"value": m.group(0), "format": "day-month"} for m in DAY_MONTH_RE.finditer(text)]
    return out


def _institutions(text: str) -> list[dict]:
    found = []
    for m in INSTITUTION_RE.finditer(text):
        kind = KIND_BY_WORD.get(m.group(2).lower(), m.group(2).lower())
        # The name is only set when the user gave one. Nothing is invented.
        found.append({"mention": m.group(0).strip(), "kind": kind, "name": None, "name_given": False})
    return found


def _events(text: str) -> list[dict]:
    events = []
    for event_type, pattern in EVENT_PATTERNS:
        m = pattern.search(text)
        if m:
            events.append({"type": event_type, "span": m.group(0)})
    m = NON_REFUNDABLE_RE.search(text)
    if m:
        events.append({"type": "NON_REFUNDABLE_TERMS", "span": m.group(0)})
    return events


def _missing(events: list[dict], amounts: list[dict], institutions: list[dict], dates: list[dict]) -> list[str]:
    gaps = []
    types = {e["type"] for e in events}
    if "PARTIAL_REFUND" in types and not amounts:
        gaps.append("amount refunded so far")
    if "CLAIM_REJECTED" in types and not amounts:
        gaps.append("amount claimed")
    if "CARRIER_CANCELLATION" in types and not dates:
        gaps.append("date of cancellation")
    for inst in institutions:
        gaps.append(f"name of the {inst['mention'].split()[-1]} (not given)")
    return gaps


def parse(text: str | None) -> dict:
    normalized = _normalize(text or "")
    empty = {"domains": [], "events": [], "amounts": [], "dates": [], "institutions": [],
             "flags": {}, "missing": [], "ambiguities": [], "ignored_instructions": []}
    if not normalized:
        return {"status": "EMPTY", "message": "No complaint text was given.", **empty}
    if _non_latin_share(normalized) > 0.3:
        return {"status": "LANGUAGE_UNSUPPORTED",
                "message": "This text is not in English. Translate it or describe the problem in English.", **empty}

    domains = _domains(normalized)
    events = _events(normalized)
    amounts = _amounts(normalized)
    dates = _dates(normalized)
    institutions = _institutions(normalized)
    ambiguities = [{"span": m.group(0), "note": "vague amount or share: not converted to a number"}
                   for m in AMBIGUOUS_RE.finditer(normalized)]
    missing = _missing(events, amounts, institutions, dates)
    return {
        "status": "NEEDS_INFO" if missing or not domains else "OK",
        "message": None,
        "domains": domains,
        "events": events,
        "amounts": amounts,
        "dates": dates,
        "institutions": institutions,
        "flags": {"non_refundable": any(e["type"] == "NON_REFUNDABLE_TERMS" for e in events),
                  "claim_rejected": any(e["type"] == "CLAIM_REJECTED" for e in events)},
        "missing": missing,
        "ambiguities": ambiguities,
        # Instruction-like text in a complaint is reported and treated as data. It changes nothing.
        "ignored_instructions": [m.group(0) for m in INSTRUCTION_RE.finditer(normalized)],
    }
