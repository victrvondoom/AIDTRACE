"""One interface over four different agent runtimes, without forcing them into one framework.

Kairos hosts ResolveAI (a LangGraph multi-agent worker), the Track 01 fraud investigator (a native tool-calling loop), GreenChain
(a deterministic XGBoost scoring pipeline with optional LLM agents) and the Kairos memory/evidence cascade. Each keeps its own
runtime. An adapter wraps one of them and answers the same questions: what is it, is it connected right now, which shared interfaces
does it really provide (natively, only through Kairos, or not at all), which tools does it expose, and what has it run recently.

The support matrix is declared per adapter and tested against reality; it never claims an interface an adapter cannot back.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

INTERFACES = ("task_execution", "tool_invocation", "evidence_retrieval", "graph_queries", "memory", "handoffs", "approval", "result_persistence", "execution_trace")
NATIVE, VIA_KAIROS, NONE = "native", "via_kairos", "none"


@dataclass(frozen=True)
class Tool:
    name: str
    interface: str
    description: str
    read_only: bool = True
    invokable: bool = False  # True when POST /agents/tools/invoke can run it safely


@dataclass
class Context:
    user: dict[str, Any]
    site_id: str
    settings: Any
    store: Any  # FalkorDriftStore


@dataclass
class Adapter:
    id: str
    name: str
    framework: str
    origin: str
    interfaces: dict[str, str]
    tools: tuple[Tool, ...]
    limits: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        missing = set(INTERFACES) - set(self.interfaces)
        unknown = set(self.interfaces) - set(INTERFACES)
        if missing or unknown or any(v not in (NATIVE, VIA_KAIROS, NONE) for v in self.interfaces.values()):
            raise ValueError(f"adapter {self.id} declares an invalid interface matrix: missing={sorted(missing)} unknown={sorted(unknown)}")
        bad_tools = [t.name for t in self.tools if t.interface not in INTERFACES or (self.interfaces[t.interface] == NONE)]
        if bad_tools:
            raise ValueError(f"adapter {self.id} exposes tools for interfaces it says it does not provide: {bad_tools}")

    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "framework": self.framework, "origin": self.origin, "interfaces": self.interfaces,
                "tools": [asdict(t) for t in self.tools], "limits": list(self.limits)}


RESOLVEAI = Adapter(
    id="resolveai", name="ResolveAI", framework="LangGraph multi-agent workflow plus a deterministic evidence pipeline", origin="RESOLVE-AI-main (private worker)",
    interfaces={"task_execution": NATIVE, "tool_invocation": NATIVE, "evidence_retrieval": NATIVE, "graph_queries": NATIVE, "memory": VIA_KAIROS, "handoffs": NATIVE,
                "approval": NONE, "result_persistence": NATIVE, "execution_trace": NATIVE},
    tools=(Tool("search_corpus", "evidence_retrieval", "Vector search over the indexed domain corpora", invokable=True),
           Tool("investigate_case", "task_execution", "Route, retrieve, score and cite evidence for a case", read_only=False),
           Tool("run_case_workflow", "task_execution", "Full research, evidence, strategy, negotiation and review agents (needs a model)", read_only=False),
           Tool("case_graph", "graph_queries", "Case, institution, document and appeal graph")),
    limits=("Agents write nothing without a model provider; it has no approval step of its own (drafts only).",),
)
FRAUD = Adapter(
    id="fraud", name="Fraud investigator", framework="Native tool-calling investigator (ported from Track 01)", origin="track1-agent",
    interfaces={"task_execution": NATIVE, "tool_invocation": NATIVE, "evidence_retrieval": NATIVE, "graph_queries": NATIVE, "memory": NONE, "handoffs": NONE,
                "approval": NATIVE, "result_persistence": NATIVE, "execution_trace": NATIVE},
    tools=(Tool("flagged_transactions", "graph_queries", "Transactions the network flags"), Tool("ring_members", "graph_queries", "Accounts in a circular money flow"),
           Tool("propose_freeze", "approval", "Propose freezing accounts (a human approves or rejects)", read_only=False)),
    limits=("Runs on a synthetic transfer network. It does not yet read or write shared agent memory.",),
)
GREENCHAIN = Adapter(
    id="greenchain", name="GreenChain scorer", framework="Deterministic XGBoost scoring pipeline (optional LLM scenario agents)", origin="GREENCHAIN-main",
    interfaces={"task_execution": NATIVE, "tool_invocation": NATIVE, "evidence_retrieval": NATIVE, "graph_queries": VIA_KAIROS, "memory": VIA_KAIROS, "handoffs": VIA_KAIROS,
                "approval": VIA_KAIROS, "result_persistence": VIA_KAIROS, "execution_trace": NONE},
    tools=(Tool("score_suppliers", "task_execution", "Score and rank candidates with the XGBoost models and reference data", invokable=True),
           Tool("what_if_remove_supplier", "task_execution", "Re-rank without one supplier"),
           Tool("record_decision", "memory", "Store the recommendation as evidence-backed memory", read_only=False)),
    limits=("No per-run execution trace of its own; its decisions are traced through agent memory.", "Live discovery needs provider keys."),
)
MEMORY = Adapter(
    id="memory", name="Kairos memory and evidence cascade", framework="FalkorDB graph memory with deterministic traversal", origin="Kairos",
    interfaces={"task_execution": NONE, "tool_invocation": NATIVE, "evidence_retrieval": NATIVE, "graph_queries": NATIVE, "memory": NATIVE, "handoffs": NATIVE,
                "approval": NATIVE, "result_persistence": NATIVE, "execution_trace": NATIVE},
    tools=(Tool("recall", "memory", "Memories an agent may rely on now (stale ones are blocked)", read_only=False, invokable=True),
           Tool("context", "memory", "Verified memory context with source and claim provenance for LLM agents", read_only=False, invokable=True),
           Tool("supersede_source", "evidence_retrieval", "Mark dependants stale when a source is superseded", read_only=False),
           Tool("approve_action", "approval", "Approve the current revision of a decision (refused if stale)", read_only=False)),
    limits=("It stores and gates what other agents conclude; it does not reason on its own.",),
)
ADAPTERS: dict[str, Adapter] = {a.id: a for a in (RESOLVEAI, FRAUD, GREENCHAIN, MEMORY)}


def support_matrix() -> dict[str, Any]:
    return {"interfaces": list(INTERFACES), "runtimes": [{"id": a.id, "name": a.name, "support": a.interfaces} for a in ADAPTERS.values()]}
