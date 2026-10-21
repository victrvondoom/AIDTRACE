"""Honest registry of shared infrastructure and domain capabilities.

Registry entries describe code that exists and its current activation boundary. An entry does
not get an executor merely because its name or UI is present; domain execution is unavailable
until a real adapter supplies evidence and has integration-test evidence attached.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from api.services.coordination.contracts import CapabilityAvailability, RiskLevel


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    display_name: str
    domain: str
    version: str
    description: str
    pack: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    read_tools: tuple[str, ...] = ()
    write_tools: tuple[str, ...] = ()
    required_services: tuple[str, ...] = ()
    required_credentials: tuple[str, ...] = ()
    required_role: str = "engineer"
    risk_level: RiskLevel | str = RiskLevel.LOW
    supports_simulation: bool = False
    supports_replay: bool = False
    supports_evidence_trace: bool = True
    supports_checkpointing: bool = True
    availability: CapabilityAvailability | str = CapabilityAvailability.PLANNED
    test_evidence: tuple[str, ...] = ()
    source_provenance: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        item = asdict(self)
        item["read_tools"] = list(self.read_tools)
        item["write_tools"] = list(self.write_tools)
        item["required_services"] = list(self.required_services)
        item["required_credentials"] = list(self.required_credentials)
        item["test_evidence"] = list(self.test_evidence)
        item["source_provenance"] = list(self.source_provenance)
        return item


class CapabilityRegistry:
    """Namespaced capabilities with deterministic status lookup."""

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDefinition] = {}
        self._register_defaults()

    def register(self, capability: CapabilityDefinition) -> None:
        if capability.capability_id in self._capabilities:
            raise ValueError(f"duplicate capability id: {capability.capability_id}")
        self._capabilities[capability.capability_id] = capability

    def get(self, capability_id: str) -> CapabilityDefinition | None:
        return self._capabilities.get(capability_id)

    def list_all(self) -> list[CapabilityDefinition]:
        return list(self._capabilities.values())

    def list_by_pack(self, pack: str) -> list[CapabilityDefinition]:
        return [item for item in self._capabilities.values() if item.pack == pack]

    def list_by_domain(self, domain: str) -> list[CapabilityDefinition]:
        aliases = {
            "cyber": "cybersecurity", "security": "cybersecurity", "aml": "finance",
            "fraud": "finance", "supply": "supply_chain", "greenchain": "supply_chain",
            "research": "research_data", "data_engineering": "research_data",
            "industrial": "kairos_industrial", "kairos": "kairos_industrial",
            "business": "business_support", "support": "business_support",
            "cloud": "cloud_devsecops", "devsecops": "cloud_devsecops",
            "disaster": "disaster_environment", "environment": "disaster_environment",
            "sre": "incident_sre",
        }
        normalized = aliases.get(domain.casefold(), domain.casefold())
        return [item for item in self._capabilities.values() if item.domain == normalized]

    def readiness(self, domain: str) -> dict[str, Any]:
        items = self.list_by_domain(domain)
        if not items:
            return {"domain": domain, "availability": "PLANNED", "capabilities": [],
                    "reason": "No capability is registered for this domain."}
        active = [item for item in items if item.availability == CapabilityAvailability.OPERATIONAL]
        if active:
            overall = CapabilityAvailability.OPERATIONAL.value
        elif any(item.availability == CapabilityAvailability.PARTIAL for item in items):
            overall = CapabilityAvailability.PARTIAL.value
        elif any(item.availability == CapabilityAvailability.CONFIGURATION_REQUIRED for item in items):
            overall = CapabilityAvailability.CONFIGURATION_REQUIRED.value
        elif any(item.availability == CapabilityAvailability.BLOCKED for item in items):
            overall = CapabilityAvailability.BLOCKED.value
        else:
            overall = CapabilityAvailability.PLANNED.value
        return {
            "domain": domain,
            "availability": overall,
            "capabilities": [{"capability_id": item.capability_id,
                              "display_name": item.display_name,
                              "availability": str(item.availability),
                              "required_services": list(item.required_services),
                              "required_credentials": list(item.required_credentials),
                              "test_evidence": list(item.test_evidence)} for item in items],
            "reason": "Registry readiness only; no domain finding was executed by this check.",
        }

    def _register_defaults(self) -> None:
        self.register(CapabilityDefinition(
            capability_id="core.graph_evidence_lookup", display_name="Site-scoped graph evidence lookup",
            domain="platform_core", version="1.0.0",
            description="Read exact supplied identifiers from the authenticated site's FalkorDB graph.",
            pack="Platform Core", input_schema={"evidence_ids": "array[string]"},
            output_schema={"found_ids": "array[string]", "missing_ids": "array[string]"},
            read_tools=("FalkorDriftStore.read_node",), required_services=("FalkorDB",),
            availability=CapabilityAvailability.CONFIGURATION_REQUIRED,
            test_evidence=("backend/tests/test_coordination.py::test_evidence_worker_only_cites_present_graph_nodes",),
            source_provenance=("backend/api/services/drift/store.py",),
        ))
        self.register(CapabilityDefinition(
            capability_id="core.capability_readiness", display_name="Domain capability readiness",
            domain="platform_core", version="1.0.0",
            pack="Platform Core",
            description="Reports registered domain adapter status and prerequisites; it does not perform domain analysis.",
            input_schema={"domain": "string"}, output_schema={"availability": "enum"},
            read_tools=("CapabilityRegistry.readiness",), availability=CapabilityAvailability.OPERATIONAL,
            test_evidence=("backend/tests/test_coordination.py::test_capability_readiness_is_explicit",),
            source_provenance=("backend/api/services/coordination/capability_registry.py",),
        ))
        self.register(CapabilityDefinition(
            capability_id="core.deterministic_summary", display_name="Evidence and readiness summary",
            domain="platform_core", version="1.0.0",
            pack="Platform Core",
            description="Combines stored Worker A and Worker B outputs without adding claims or actions.",
            input_schema={"task_results": "array[object]"}, output_schema={"outcome": "enum"},
            availability=CapabilityAvailability.OPERATIONAL,
            test_evidence=("backend/tests/test_coordination.py::test_generic_plan_fails_closed_without_domain_adapter",),
            source_provenance=("backend/api/services/coordination/coordinator.py",),
        ))

        entries = [
            ("supply.supplier_impact", "Supplier and procurement impact", "supply_chain", "Pack A: Supply and GreenChain", "PARTIAL", ("FalkorDB", "GreenChain API"), ("backend/domains/greenchain",)),
            ("cyber.reachability", "Reachability-to-repair analysis", "cybersecurity", "Pack B: Cybersecurity", "PLANNED", ("FalkorDB", "SBOM or lockfile intake", "isolated test runner"), ("docs/integration/UNIFIED_PLATFORM_BASELINE.md",)),
            ("finance.aml_trace", "Evidence-linked transaction tracing", "finance", "Pack C: Finance and AML", "PARTIAL", ("FalkorDB", "authorized transaction source"), ("backend/domains/fraud",)),
            ("sre.incident_diagnosis", "Incident and service dependency diagnosis", "incident_sre", "Pack D: Incident Response and SRE", "PLANNED", ("FalkorDB", "authorized telemetry source"), ("docs/integration/UNIFIED_PLATFORM_BASELINE.md",)),
            ("cloud.manifest_policy", "Cloud and Kubernetes policy checks", "cloud_devsecops", "Pack E: Cloud and DevSecOps", "PLANNED", ("policy engine", "authorized manifests"), ("docs/integration/UNIFIED_PLATFORM_BASELINE.md",)),
            ("research.data_contracts", "Research and data contract verification", "research_data", "Pack F: Research and Data Engineering", "PLANNED", ("versioned source contract", "quarantine store"), ("docs/integration/UNIFIED_PLATFORM_BASELINE.md",)),
            ("disaster.hazard_assessment", "Authoritative hazard and response evidence", "disaster_environment", "Pack G: Disaster and Environment", "PLANNED", ("authoritative observations", "geospatial source"), ("docs/integration/UNIFIED_PLATFORM_BASELINE.md",)),
            ("industrial.asset_diagnostics", "Kairos industrial asset evidence", "kairos_industrial", "Pack H: Kairos Industrial", "PARTIAL", ("Neo4j", "Qdrant", "Elasticsearch"), ("backend/api", "frontend/src/components/features")),
            ("business.support_swarm_memory", "Business and support knowledge workflows", "business_support", "Pack I: Business and Support", "PLANNED", ("authorized knowledge source",), ("docs/integration/UNIFIED_PLATFORM_BASELINE.md",)),
            ("business.engineering_memory", "Voice-captured engineering memory vault", "business_support", "Pack I: Business and Support", "PARTIAL", ("FalkorDB", "Groq transcription credential for voice"), ("backend/api/services/memory/engineering_vault.py", "backend/api/services/memory/engineering_mcp.py")),
        ]
        for capability_id, name, domain, pack, availability, services, provenance in entries:
            status = CapabilityAvailability(availability)
            self.register(CapabilityDefinition(
                capability_id=capability_id,
                display_name=name,
                domain=domain,
                version="1.0.0",
                description=(f"{name} is registered with status {availability}; coordination does not execute this domain adapter."),
                pack=pack,
                input_schema={"goal": "string", "evidence_ids": "array[string]"},
                output_schema={"availability": "enum", "findings": "array[evidence-backed]"},
                read_tools=(),
                write_tools=(),
                required_services=services,
                required_credentials=(),
                required_role="engineer",
                risk_level=RiskLevel.HIGH if domain in {"cybersecurity", "finance", "disaster_environment"} else RiskLevel.MEDIUM,
                supports_simulation=False,
                supports_replay=False,
                supports_evidence_trace=True,
                supports_checkpointing=True,
                availability=status,
                test_evidence=(),
                source_provenance=provenance,
            ))


CAPABILITY_REGISTRY = CapabilityRegistry()
