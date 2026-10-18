"""Citation checks for rules. Word overlap is not enough, so each check tests a different property.

A rule is citable only when all of these hold:
  UNVERIFIED_SOURCE   the source is marked verified by a person, not just present in the graph
  EXCERPT_MISMATCH    the exact condition text appears in the source excerpt (normalized, not fuzzy)
  JURISDICTION_MISMATCH  the source applies in the case's jurisdiction
  NOT_IN_FORCE        the source has an effective date on or before the event date
  SOURCE_CONFLICT     a different source CONTRADICTS this rule

Returning a list of problems (instead of a boolean) lets the verifier say exactly what is missing.
"""
import re

_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"'}


def normalize(text: str) -> str:
    """Lowercase, unify quote characters, drop punctuation other than apostrophes, collapse spaces."""
    for src, dst in _QUOTES.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^\w' ]+", " ", text.lower())
    return " ".join(text.split())


def check_rule(rule: dict, sources: dict, conflicting_sources: set, event_date: str, jurisdiction: str) -> list[str]:
    source = sources.get(rule["source_id"])
    if source is None:
        return ["SOURCE_MISSING"]
    problems = []
    if not source["verified"]:
        problems.append("UNVERIFIED_SOURCE")
    if normalize(rule["condition_text"]) not in normalize(source["excerpt"]):
        problems.append("EXCERPT_MISMATCH")
    if source["jurisdiction"] != jurisdiction:
        problems.append("JURISDICTION_MISMATCH")
    if not source["effective_date"] or source["effective_date"] > event_date:
        problems.append("NOT_IN_FORCE")
    if conflicting_sources:
        problems.append("SOURCE_CONFLICT")
    return problems
