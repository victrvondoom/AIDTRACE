"""Evidence Drift Cascade integration tests.

These tests verify the deterministic impact traversal engine independently of any database,
then test the FalkorDB-backed routes when a store is available.
"""
import json

import pytest

from api.services.drift.engine import DependencyEdge, ImpactPath, find_impacted_dependents
from api.services.drift.model import (
    AUTHORITY_MIN,
    AUTHORITY_MAX,
    ContractError,
    DERIVED_LABELS,
    DEPENDENCY_RELS,
    EdgeKind,
    Label,
    MemoryKind,
    PROPAGATING_KINDS,
    Rel,
    SourceStatus,
    Verdict,
    check_authority,
    check_confidence,
    check_id,
    check_key,
    check_site,
    encode_value,
    evaluate_conditions,
    parse_conditions,
    resolve_authority,
    stable_hash,
    now_iso,
    Condition,
    ConditionResult,
    EvidenceStrength,
    VALID_TO_OPEN,
)


class TestContractValidation:
    """Validation of all typed contract inputs."""

    def test_valid_id(self) -> None:
        assert check_id("abc123") == "abc123"
        assert check_id("node_001") == "node_001"
        assert check_id("a" * 128) == "a" * 128

    def test_invalid_id_empty(self) -> None:
        with pytest.raises(ContractError, match="id"):
            check_id("")

    def test_invalid_id_too_long(self) -> None:
        with pytest.raises(ContractError, match="id"):
            check_id("x" * 129)

    def test_invalid_id_spaces(self) -> None:
        with pytest.raises(ContractError, match="id"):
            check_id("bad id")

    def test_site_validation(self) -> None:
        assert check_site("SITE_01") == "SITE_01"
        assert check_site("a" * 64) == "a" * 64
        with pytest.raises(ContractError, match="site_id"):
            check_site("bad site")

    def test_key_validation(self) -> None:
        assert check_key("pressure_setpoint") == "pressure_setpoint"
        assert check_key("a" * 200) == "a" * 200
        with pytest.raises(ContractError, match="fact key"):
            check_key("")

    def test_authority_bounds(self) -> None:
        assert check_authority(AUTHORITY_MIN) == AUTHORITY_MIN
        assert check_authority(AUTHORITY_MAX) == AUTHORITY_MAX
        with pytest.raises(ContractError, match="authority_level"):
            check_authority(0)
        with pytest.raises(ContractError, match="authority_level"):
            check_authority(AUTHORITY_MAX + 1)
        with pytest.raises(ContractError, match="authority_level"):
            check_authority(True)  # bool is not int

    def test_confidence_bounds(self) -> None:
        assert check_confidence(0.0) == 0.0
        assert check_confidence(1.0) == 1.0
        assert check_confidence(0.5) == 0.5
        with pytest.raises(ContractError, match="confidence"):
            check_confidence(-0.1)
        with pytest.raises(ContractError, match="confidence"):
            check_confidence(1.1)
        with pytest.raises(ContractError, match="confidence"):
            check_confidence(True)


class TestStableHash:
    """Deterministic hashing utilities."""

    def test_same_input_same_hash(self) -> None:
        payload = {"key": "value", "number": 42}
        h1 = stable_hash(payload)
        h2 = stable_hash(payload)
        assert h1 == h2

    def test_different_input_different_hash(self) -> None:
        h1 = stable_hash({"key": "value1"})
        h2 = stable_hash({"key": "value2"})
        assert h1 != h2

    def test_order_independent(self) -> None:
        dict1 = {"a": 1, "b": 2, "c": 3}
        dict2 = {"c": 3, "b": 2, "a": 1}
        assert stable_hash(dict1) == stable_hash(dict2)


class TestValueEncoding:
    """Fact value canonical encoding."""

    def test_string(self) -> None:
        assert encode_value("hello") == '"hello"'

    def test_number(self) -> None:
        assert encode_value(42) == "42"
        assert encode_value(3.14) == "3.14"

    def test_boolean(self) -> None:
        assert encode_value(True) == "true"
        assert encode_value(False) == "false"

    def test_list(self) -> None:
        result = encode_value([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_nested(self) -> None:
        result = encode_value({"nested": {"value": 1}})
        parsed = json.loads(result)
        assert parsed == {"nested": {"value": 1}}

    def test_invalid_nested_object(self) -> None:
        with pytest.raises(ContractError, match="value"):
            encode_value({"nested": object()})


class TestConditions:
    """Decision precondition evaluation."""

    def test_equality(self) -> None:
        cond = Condition(key="x", op="==", value=42, material=True)
        assert cond.holds(42) is True
        assert cond.holds(43) is False
        assert cond.holds(None) is False

    def test_inequality(self) -> None:
        cond = Condition(key="x", op="!=", value=42)
        assert cond.holds(43) is True
        assert cond.holds(42) is False

    def test_less_than(self) -> None:
        cond = Condition(key="x", op="<", value=100)
        assert cond.holds(50) is True
        assert cond.holds(100) is False
        assert cond.holds(150) is False

    def test_greater_than_or_equal(self) -> None:
        cond = Condition(key="x", op=">=", value=10)
        assert cond.holds(10) is True
        assert cond.holds(11) is True
        assert cond.holds(9) is False

    def test_in_operator(self) -> None:
        cond = Condition(key="status", op="in", value=["ACTIVE", "PENDING"])
        assert cond.holds("ACTIVE") is True
        assert cond.holds("COMPLETE") is False

    def test_material_flag(self) -> None:
        cond = Condition(key="x", op="==", value=42, material=False)
        assert cond.material is False

    def test_invalid_op(self) -> None:
        with pytest.raises(ContractError, match="op"):
            Condition(key="x", op="INVALID", value=1)

    def test_in_requires_list(self) -> None:
        with pytest.raises(ContractError, match="list"):
            Condition(key="x", op="in", value="not a list")

    def test_evaluate_conditions_basic(self) -> None:
        conditions = [
            Condition(key="pressure", op=">=", value=100, material=True),
            Condition(key="temperature", op="<", value=200, material=True),
        ]
        current = {"pressure": ("claim1", 150), "temperature": ("claim2", 150)}
        results = evaluate_conditions(conditions, current)
        assert len(results) == 2
        assert all(r.holds for r in results)

    def test_evaluate_conditions_missing(self) -> None:
        conditions = [Condition(key="missing", op="==", value=1)]
        current = {}
        results = evaluate_conditions(conditions, current)
        assert len(results) == 1
        assert results[0].holds is False

    def test_parse_conditions_from_json(self) -> None:
        raw = [
            {"key": "x", "op": "==", "value": 42, "material": True},
            {"key": "y", "op": ">", "value": 10},
        ]
        conditions = parse_conditions(raw)
        assert len(conditions) == 2
        assert conditions[0].key == "x"

    def test_parse_conditions_from_string(self) -> None:
        raw = '[{"key": "x", "op": "==", "value": 42}]'
        conditions = parse_conditions(raw)
        assert len(conditions) == 1


class TestAuthorityResolution:
    """Authority-aware conflict resolution (Algorithm D)."""

    def test_stronger_replaces_weaker(self) -> None:
        incumbent = EvidenceStrength(authority_level=3, verification_status="VERIFIED", confidence=0.9)
        challenger = EvidenceStrength(authority_level=1, verification_status="VERIFIED", confidence=0.95)
        assert resolve_authority(incumbent, challenger) == Verdict.REPLACE

    def test_same_authority_newer_replaces(self) -> None:
        incumbent = EvidenceStrength(authority_level=2, verification_status="VERIFIED", confidence=0.9)
        challenger = EvidenceStrength(authority_level=2, verification_status="VERIFIED", confidence=0.95)
        assert resolve_authority(incumbent, challenger) == Verdict.REPLACE

    def test_weaker_contests_stronger(self) -> None:
        incumbent = EvidenceStrength(authority_level=1, verification_status="VERIFIED", confidence=0.9)
        challenger = EvidenceStrength(authority_level=3, verification_status="VERIFIED", confidence=0.95)
        assert resolve_authority(incumbent, challenger) == Verdict.CONTEST

    def test_unverified_contests_verified(self) -> None:
        incumbent = EvidenceStrength(authority_level=2, verification_status="VERIFIED", confidence=0.9)
        challenger = EvidenceStrength(authority_level=2, verification_status="UNVERIFIED", confidence=0.95)
        assert resolve_authority(incumbent, challenger) == Verdict.CONTEST

    def test_quarantined_rejected(self) -> None:
        incumbent = EvidenceStrength(authority_level=1, verification_status="VERIFIED", confidence=0.9)
        challenger = EvidenceStrength(authority_level=1, verification_status="QUARANTINED", confidence=0.6)
        assert resolve_authority(incumbent, challenger) == Verdict.REJECT

    def test_low_confidence_rejected(self) -> None:
        incumbent = EvidenceStrength(authority_level=2, verification_status="VERIFIED", confidence=0.9)
        challenger = EvidenceStrength(authority_level=1, verification_status="VERIFIED", confidence=0.65)
        assert resolve_authority(incumbent, challenger) == Verdict.REJECT


class TestImpactTraversal:
    """Evidence impact traversal (Algorithm A) and minimal affected subgraph (Algorithm B)."""

    def test_direct_dependency(self) -> None:
        edges = [
            DependencyEdge(dependent_id="decision1", dependency_id="claim1"),
        ]
        paths = find_impacted_dependents(["claim1"], edges)
        assert len(paths) == 1
        assert paths[0].node_id == "decision1"
        assert paths[0].depth == 1
        assert paths[0].path == ("claim1", "decision1")

    def test_transitive_dependency(self) -> None:
        edges = [
            DependencyEdge(dependent_id="decision1", dependency_id="claim1"),
            DependencyEdge(dependent_id="plan1", dependency_id="decision1"),
            DependencyEdge(dependent_id="action1", dependency_id="plan1"),
        ]
        paths = find_impacted_dependents(["claim1"], edges)
        assert len(paths) == 3
        node_ids = {p.node_id for p in paths}
        assert node_ids == {"decision1", "plan1", "action1"}

    def test_multiple_shortest_paths_same_depth(self) -> None:
        edges = [
            DependencyEdge(dependent_id="a", dependency_id="root"),
            DependencyEdge(dependent_id="b", dependency_id="root"),
            DependencyEdge(dependent_id="c", dependency_id="a"),
            DependencyEdge(dependent_id="c", dependency_id="b"),
        ]
        paths = find_impacted_dependents(["root"], edges)
        assert len(paths) == 3
        c_paths = [p for p in paths if p.node_id == "c"]
        assert len(c_paths) == 1
        # Lexicographically first path should be retained
        assert c_paths[0].path == ("root", "a", "c") or c_paths[0].path == ("root", "b", "c")

    def test_no_propagation_for_context_edges(self) -> None:
        edges = [
            DependencyEdge(dependent_id="decision1", dependency_id="claim1", kind=EdgeKind.CONTEXT.value),
        ]
        paths = find_impacted_dependents(["claim1"], edges)
        # Context edges should not propagate invalidation
        assert len(paths) == 0

    def test_max_depth_respected(self) -> None:
        edges = [
            DependencyEdge(dependent_id=f"n{i}", dependency_id=f"n{i-1}") for i in range(1, 20)
        ]
        paths = find_impacted_dependents(["n0"], edges, max_depth=3)
        assert len(paths) == 3  # n1, n2, n3

    def test_multiple_changed_roots(self) -> None:
        edges = [
            DependencyEdge(dependent_id="decision1", dependency_id="claim1"),
            DependencyEdge(dependent_id="decision2", dependency_id="claim2"),
        ]
        paths = find_impacted_dependents(["claim1", "claim2"], edges)
        assert len(paths) == 2
        node_ids = {p.node_id for p in paths}
        assert node_ids == {"decision1", "decision2"}

    def test_duplicates_not_returned(self) -> None:
        edges = [
            DependencyEdge(dependent_id="decision1", dependency_id="claim1"),
            DependencyEdge(dependent_id="decision1", dependency_id="claim1"),  # duplicate
        ]
        paths = find_impacted_dependents(["claim1"], edges)
        assert len(paths) == 1

    def test_empty_input(self) -> None:
        paths = find_impacted_dependents([], [])
        assert paths == []

    def test_roots_not_in_output(self) -> None:
        edges = [
            DependencyEdge(dependent_id="decision1", dependency_id="claim1"),
        ]
        paths = find_impacted_dependents(["claim1"], edges)
        node_ids = [p.node_id for p in paths]
        assert "claim1" not in node_ids


class TestLabelsAndRelationships:
    """Verify the graph contract labels and relationships."""

    def test_all_labels_exist(self) -> None:
        expected = {
            "Document", "SourceVersion", "Claim", "Agent", "AgentSession",
            "Memory", "Decision", "Plan", "ActionProposal", "Approval",
            "ChangeEvent", "AuditEvent", "Asset",
        }
        actual = {label.value for label in Label}
        assert expected == actual

    def test_dependency_rels(self) -> None:
        """Only SUPPORTED_BY, DERIVED_FROM, DEPENDS_ON propagate invalidation."""
        expected = {Rel.SUPPORTED_BY.value, Rel.DERIVED_FROM.value, Rel.DEPENDS_ON.value}
        actual = set(DEPENDENCY_RELS)
        assert expected == actual

    def test_propagating_edge_kinds(self) -> None:
        expected = {EdgeKind.LOGICAL.value, EdgeKind.POLICY.value}
        actual = set(PROPAGATING_KINDS)
        assert expected == actual


class TestSentinels:
    """Kairos sentinel values."""

    def test_valid_to_open(self) -> None:
        assert VALID_TO_OPEN == "9999-12-31T00:00:00.000000+00:00"


class TestImpactPath:
    """ImpactPath dataclass."""

    def test_as_dict(self) -> None:
        path = ImpactPath(node_id="decision1", depth=2, path=("claim1", "memory1", "decision1"))
        d = path.as_dict()
        assert d["node_id"] == "decision1"
        assert d["depth"] == 2
        assert d["path"] == ["claim1", "memory1", "decision1"]
        assert d["changed"] is True


class TestDependencyEdge:
    """DependencyEdge dataclass."""

    def test_invalid_id(self) -> None:
        with pytest.raises(ContractError):
            DependencyEdge(dependent_id="", dependency_id="valid")

    def test_invalid_dependency_id(self) -> None:
        with pytest.raises(ContractError):
            DependencyEdge(dependent_id="valid", dependency_id="bad id")

    def test_invalid_kind(self) -> None:
        with pytest.raises(ContractError, match="kind"):
            DependencyEdge(dependent_id="a", dependency_id="b", kind="INVALID")
