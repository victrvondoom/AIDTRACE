"""KAIROS INTEGRATION (added to the imported RESOLVE-AI-main worker; not part of the upstream project).

Evidence-first investigation that runs ResolveAI's OWN deterministic pipeline stages and reports exactly what ran:

    domain router (keyword scored) -> vector retrieval over the indexed domain corpus -> authority-aware ranking
    -> evidence scoring -> citation building -> institution knowledge-graph patterns

No text is generated here. Model synthesis (the full multi-agent case workflow) is attached only when a model
provider is configured and enabled; otherwise `synthesis.status` says it did not run, and nothing pretends it did.
The result is stored as an agent run on the case so it appears in the case history.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.research_agent.agent import rank_hits
from app.agents.role_agents.domain_router import classify_domains
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.models.domain import ACTIVE_DOMAINS, Domain
from app.prompts.domain_profiles import get_profile
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.case_context import build_case_summary
from app.services.citation_engine import build_citations

router = APIRouter()
MAX_DOMAINS = 3
HITS_PER_QUERY = 40  # a wide pool, so the lexical re-rank below has something to choose from
EVIDENCE_PER_DOMAIN = 6
LEXICAL_WEIGHT = 0.6
_TOKEN = re.compile(r"[a-z][a-z0-9]{2,}")
_STOP = frozenset("""the and for that with this from have has was were are but not you your they them their there which would could
should about into than then also been being over under such only any all can may will upon its our his her she him who whom what when
where while after before because since did does done had out off per via""".split())


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def lexical_rerank(query: str, hits: list[dict]) -> list[dict]:
    """BM25 of each retrieved chunk against the case text, blended with its vector similarity.

    The default offline embeddings are hashed bag-of-words vectors, which find topical neighbours but rank them loosely.
    BM25 over the candidate pool (document frequencies taken from the pool itself) favours chunks that contain the case's
    distinctive terms. The original vector score is kept as `vector_score`; the blend is reported as `score`."""
    docs = [_tokens(h.get("text", "")) for h in hits]
    query_terms = set(_tokens(query))
    if not hits or not query_terms:
        return hits
    n = len(docs)
    df = Counter(term for doc in docs for term in set(doc) if term in query_terms)
    avg = (sum(len(d) for d in docs) / n) or 1.0
    raw: list[float] = []
    for doc in docs:
        tf = Counter(doc)
        score = 0.0
        for term in query_terms:
            if not tf[term]:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * 2.2 / (tf[term] + 1.2 * (0.25 + 0.75 * len(doc) / avg))
        raw.append(score)
    top = max(raw) or 1.0
    out = []
    for hit, lexical in zip(hits, raw):
        vector = max(0.0, min(1.0, float(hit.get("score", 0.0))))
        blended = {**hit, "vector_score": round(vector, 4), "lexical_score": round(lexical / top, 4),
                   "score": LEXICAL_WEIGHT * (lexical / top) + (1 - LEXICAL_WEIGHT) * vector}
        out.append(blended)
    return out


class InvestigateRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=80)
    run_model_synthesis: bool = False


def _model_available() -> bool:
    settings = get_settings()
    if settings.disable_external_llm:
        return False
    provider = (settings.llm_provider or "gemini").strip().lower()
    return bool(settings.nvidia_api_key if provider == "nvidia" else settings.gemini_api_key)


@router.post("/investigate")
async def investigate(payload: InvestigateRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    case = await case_repository.get_case(payload.case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    documents = await case_repository.list_documents(case["id"])
    summary = build_case_summary(case, documents)
    institution = case.get("institution_name") or ""
    own = case["domain"] if isinstance(case["domain"], Domain) else Domain(case["domain"])

    trace: list[str] = [f"case:{case['id']}", "router:keyword_scored"]
    classified = classify_domains(summary, max_domains=MAX_DOMAINS)
    candidates = [own] + [Domain(c["domain"]) for c in classified
                          if Domain(c["domain"]) != own and Domain(c["domain"]) in ACTIVE_DOMAINS]
    candidates = candidates[:MAX_DOMAINS]
    routing = [{"domain": c["domain"], "confidence": c.get("confidence")} for c in classified]

    evidence: list[dict] = []
    stats: list[dict] = []
    patterns_out: list[dict] = []
    for domain in candidates:
        profile = get_profile(domain)
        # The case text alone first (it carries the specific vocabulary), then the research agent's broader profile query.
        queries = [f"{summary} {institution}",
                   f"{summary} {institution} " + " ".join(profile.research_questions),
                   f"{institution} {profile.counterparty} rules regulations terms"]
        seen: set[str] = set()
        hits: list[dict] = []
        for query in queries:
            for hit in await qdrant_service.search(domain, query, limit=HITS_PER_QUERY):
                if str(hit.get("id")) not in seen:
                    seen.add(str(hit.get("id")))
                    hits.append(hit)
        ranked = rank_hits(lexical_rerank(f"{summary} {institution}", hits))[:10]
        trace.append(f"retrieve:{domain.value}:{len(hits)}_hits")
        for citation in build_citations(domain, ranked, max_citations=EVIDENCE_PER_DOMAIN):
            source = next((h for h in ranked if (h.get("metadata", {}).get("title") or "") == citation["title"]), None)
            evidence.append({**citation, "chunk_id": str(source.get("id")) if source else None,
                             "retrieval_score": round(float(source.get("score", 0)), 4) if source else None,
                             "vector_score": source.get("vector_score") if source else None,
                             "lexical_score": source.get("lexical_score") if source else None})
        stats.append({"domain": domain.value, "hits_considered": len(hits), "collection": qdrant_service.collection_name(domain),
                      "indexed_points": qdrant_service.count(domain)})
        for pattern in await knowledge_graph.find_institution_patterns(domain, institution):
            patterns_out.append({"domain": domain.value, **pattern})
    trace.append("score:authority+legal_weight+freshness")
    trace.append("graph:institution_patterns")

    synthesis: dict = {"status": "NOT_RUN", "reason": "No model provider is configured for this worker, so no text was generated. "
                       "The evidence above is retrieved and scored by ResolveAI's deterministic stages only."}
    mode = "retrieval_only"
    if payload.run_model_synthesis and _model_available():
        from app.agents.orchestrator.case_analysis_workflow import case_analysis_workflow

        state = await case_analysis_workflow.run({"case_id": case["id"], "user_id": user.id, "domain": case["domain"],
                                                  "case_summary": summary, "institution_name": institution,
                                                  "evidence_bundle": "", "documents": documents})
        synthesis = {"status": "COMPLETED", "research_summary": state.get("research_summary", ""), "strategy": state.get("strategy", ""),
                     "review_notes": state.get("review_notes", []), "llm_call_count": state.get("llm_call_count", 0)}
        mode = "retrieval_plus_model"
        trace.append("synthesis:model")

    result = {"case_id": case["id"], "mode": mode, "llm_used": mode == "retrieval_plus_model", "routing": routing,
              "domains_searched": [d.value for d in candidates], "retrieval": stats, "evidence": evidence,
              "graph_patterns": patterns_out, "synthesis": synthesis,
              "citations": [e["title"] for e in evidence],  # read by the worker's case-graph view
              "agent_trace": trace,
              "limitations": ["Ranking blends the vector score with a BM25 lexical re-rank over the retrieved pool (both scores are shown).",
                              "Embeddings use the worker's configured provider; with no provider they are deterministic hashed "
                              "bag-of-words vectors, so relevance is lexical rather than semantic.",
                              "Evidence is retrieved reference material (regulations, guidance, FAQs). It is not a finding about this case "
                              "and not legal advice."]}
    await case_repository.add_agent_run(case["id"], "kairos_evidence_investigation", "completed",
                                        {"documents": len(documents), "domains": [d.value for d in candidates]}, result)
    return result
