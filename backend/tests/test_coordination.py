"""Coordination unit tests use an explicit test graph, never an implicit production fallback."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import time

import pytest

from api.services.coordination import (
    ActionProposal,
    AgentEvent,
    AgentRole,
    CapabilityAvailability,
    CoordinationGraphStore,
    CoordinatorAgent,
    DependencyScheduler,
    DeterministicGovernance,
    EventType,
    EvidenceWorker,
    Run,
    Task,
    TaskStatus,
    ValidationWorker,
    VerifiedUnlearningEngine,
    evaluate_source_independence,
)
from api.services.coordination.capability_registry import CAPABILITY_REGISTRY
from api.services.coordination.evidence_extensions import GovernedDeletionUnavailable
from api.services.coordination.graph_store import InMemoryGraphStore


@pytest.fixture
def graph_backend() -> InMemoryGraphStore:
    return InMemoryGraphStore()


@pytest.fixture
def graph_store(graph_backend: InMemoryGraphStore) -> CoordinationGraphStore:
    return CoordinationGraphStore(site_id="test_site", memory_backend=graph_backend)


def _run(store: CoordinationGraphStore, run_id: str = "test_run") -> Run:
    run = Run(run_id=run_id, site_id=store.site_id, campaign_goal="unit test", domain="general")
    return store.create_run(run)


def test_dependency_dag_readiness(graph_store: CoordinationGraphStore) -> None:
    _run(graph_store)
    tasks = [
        Task(task_id="t1", run_id="test_run", domain="general", capability_id="core.a", goal="T1"),
        Task(task_id="t2", run_id="test_run", domain="general", capability_id="core.b", goal="T2"),
        Task(task_id="t3", run_id="test_run", domain="general", capability_id="core.c", goal="T3", depends_on=["t1", "t2"]),
    ]
    for task in tasks:
        graph_store.create_task(task)
    graph_store.link_task_dependencies("test_run")
    scheduler = DependencyScheduler(graph_store)

    ready = scheduler.evaluate_readiness("test_run")
    assert {task.task_id for task in ready} == {"t1", "t2"}
    assert graph_store.get_task("t3").status == TaskStatus.WAITING_FOR_DEPENDENCY

    assert scheduler.claim_task("t1", "worker_a")
    assert scheduler.start_running("t1", "worker_a", expected_attempt=1)
    assert scheduler.complete_task("t1", "worker_a", {"done": True}, expected_attempt=1)
    assert {task.task_id for task in scheduler.evaluate_readiness("test_run")} == {"t2"}

    assert scheduler.claim_task("t2", "worker_b")
    assert scheduler.start_running("t2", "worker_b", expected_attempt=1)
    assert scheduler.complete_task("t2", "worker_b", {"done": True}, expected_attempt=1)
    assert {task.task_id for task in scheduler.evaluate_readiness("test_run")} == {"t3"}
    assert graph_store.get_task("t3").status == TaskStatus.READY


def test_task_claim_is_atomic_under_concurrent_workers(graph_store: CoordinationGraphStore) -> None:
    _run(graph_store)
    graph_store.create_task(Task(task_id="claim_me", run_id="test_run", domain="general",
                                 capability_id="core.read", goal="claim", status=TaskStatus.READY))
    scheduler = DependencyScheduler(graph_store)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda index: scheduler.claim_task("claim_me", f"worker_{index}"), range(12)))
    assert sum(results) == 1
    task = graph_store.get_task("claim_me")
    assert task.status == TaskStatus.CLAIMED
    assert task.lease_expires_at
    assert task.attempt == 1


def test_evidence_worker_only_cites_present_graph_nodes(
    graph_backend: InMemoryGraphStore, graph_store: CoordinationGraphStore
) -> None:
    _run(graph_store)
    graph_backend.upsert_node("SourceVersion", "source_present", {"status": "ACTIVE"})
    task = Task(task_id="evidence_task", run_id="test_run", domain="general",
                capability_id="core.graph_evidence_lookup", goal="check evidence",
                evidence_ids=["source_present", "missing_source"])
    ok, result, findings, error = EvidenceWorker(graph_store).execute_task(task)
    assert ok and error is None
    assert findings == []
    assert result["verified_citations"] == ["source_present"]
    assert result["missing_ids"] == ["missing_source"]
    assert result["claim_scope"] == "graph node existence only; no domain conclusion was made"


def test_generic_plan_fails_closed_without_domain_adapter(graph_store: CoordinationGraphStore) -> None:
    coordinator = CoordinatorAgent(graph_store)
    run = coordinator.plan_investigation(
        goal="Investigate this unknown vulnerability",
        domain="cybersecurity",
        site_id=graph_store.site_id,
        context_ids=["not_in_graph"],
    )
    result = coordinator.execute_investigation(run.run_id)
    assert result["status"] == "BLOCKED"
    assert result["domain_analysis_performed"] is False
    assert result["findings_count"] == 0
    assert {task["capability_id"] for task in result["tasks"]} == {
        "core.graph_evidence_lookup", "core.capability_readiness", "core.deterministic_summary"
    }
    summary = next(task for task in result["tasks"] if task["capability_id"] == "core.deterministic_summary")
    assert summary["result_data"]["outcome"] == "CAPABILITY_NOT_OPERATIONAL"
    assert graph_store.get_run(run.run_id).status == "BLOCKED"
    assert len(graph_store.list_events_for_run(run.run_id)) == result["event_count"]
    assert graph_store.get_latest_checkpoint(run.run_id).hash


def test_event_idempotency_is_persistent_and_rejects_key_reuse(graph_store: CoordinationGraphStore) -> None:
    _run(graph_store)
    event = AgentEvent(event_id="original_event_id", run_id="test_run", task_id=None,
                       event_type=EventType.RUN_CREATED, agent_id="coordinator", role="coordinator",
                       payload={"goal": "same"}, timestamp="2026-10-01T00:00:00+00:00",
                       idempotency_key="test_run:created")
    graph_store.record_event(event)
    graph_store.record_event(event)
    assert len(graph_store.list_events_for_run("test_run")) == 1
    conflict = AgentEvent(event_id="different", run_id="test_run", task_id=None,
                          event_type=EventType.RUN_CREATED, agent_id="coordinator", role="coordinator",
                          payload={"goal": "different"}, timestamp=event.timestamp,
                          idempotency_key=event.idempotency_key)
    with pytest.raises(ValueError, match="idempotency key"):
        graph_store.record_event(conflict)


def test_failed_dependency_fails_downstream_task(graph_store: CoordinationGraphStore) -> None:
    _run(graph_store)
    graph_store.create_task(Task(task_id="root", run_id="test_run", domain="general",
                                 capability_id="core.read", goal="root", status=TaskStatus.FAILED))
    graph_store.create_task(Task(task_id="child", run_id="test_run", domain="general",
                                 capability_id="core.read", goal="child", depends_on=["root"]))
    graph_store.link_task_dependencies("test_run")
    assert DependencyScheduler(graph_store).evaluate_readiness("test_run") == []
    assert graph_store.get_task("child").status == TaskStatus.FAILED
    assert graph_store.get_task("child").error == "PREREQUISITE_FAILED"


def test_retry_uses_bounded_persisted_backoff(graph_store: CoordinationGraphStore) -> None:
    _run(graph_store)
    graph_store.create_task(Task(task_id="retry", run_id="test_run", domain="general",
                                 capability_id="core.read", goal="retry", status=TaskStatus.READY,
                                 max_attempts=3))
    scheduler = DependencyScheduler(graph_store, retry_base_seconds=1, retry_max_seconds=4)
    assert scheduler.claim_task("retry", "worker")
    assert scheduler.start_running("retry", "worker", expected_attempt=1)
    assert scheduler.fail_task("retry", "worker", "temporary", expected_attempt=1)
    task = graph_store.get_task("retry")
    assert task.status == TaskStatus.READY
    assert task.next_attempt_at
    assert task.error == "temporary"
    assert DependencyScheduler(graph_store).evaluate_readiness("test_run") == []


def test_stale_attempt_cannot_complete_or_fail_a_retry(graph_store: CoordinationGraphStore) -> None:
    _run(graph_store)
    graph_store.create_task(Task(task_id="stale_result", run_id="test_run", domain="general",
                                 capability_id="core.read", goal="attempt fence", status=TaskStatus.READY,
                                 max_attempts=2))
    scheduler = DependencyScheduler(graph_store, retry_base_seconds=1)
    assert scheduler.claim_task("stale_result", "same_worker")
    assert scheduler.start_running("stale_result", "same_worker", expected_attempt=1)
    assert scheduler.fail_task("stale_result", "same_worker", "retry me", expected_attempt=1)
    assert graph_store.transition_task(
        "stale_result", expected_status=TaskStatus.READY, expected_attempt=1,
        new_status=TaskStatus.READY, next_attempt_at="2000-01-01T00:00:00+00:00",
    )
    assert [task.task_id for task in scheduler.evaluate_readiness("test_run")] == ["stale_result"]
    assert scheduler.claim_task("stale_result", "same_worker")
    assert scheduler.start_running("stale_result", "same_worker", expected_attempt=2)

    assert not scheduler.complete_task("stale_result", "same_worker", {"stale": True},
                                        expected_attempt=1)
    assert not scheduler.fail_task("stale_result", "same_worker", "stale failure",
                                   expected_attempt=1)
    current = graph_store.get_task("stale_result")
    assert current.status == TaskStatus.RUNNING
    assert current.attempt == 2
    assert current.result_data == {}
    assert scheduler.complete_task("stale_result", "same_worker", {"current": True},
                                   expected_attempt=2)
    assert graph_store.get_task("stale_result").result_data == {"current": True}


def test_worker_timeout_fails_closed(graph_store: CoordinationGraphStore) -> None:
    _run(graph_store)
    graph_store.create_task(Task(task_id="slow", run_id="test_run", domain="general",
                                 capability_id="core.read", goal="slow", status=TaskStatus.READY,
                                 max_attempts=1, timeout_seconds=1))

    def slow_worker(_task):
        time.sleep(1.1)
        return True, {"late": True}, [], None

    result = DependencyScheduler(graph_store).run_parallel_cycle(
        "test_run", {AgentRole.EVIDENCE_WORKER.value: slow_worker}, max_workers=1
    )
    assert result["timed_out"] == ["slow"]
    assert graph_store.get_task("slow").status == TaskStatus.FAILED
    assert graph_store.get_task("slow").result_data == {}


def test_recovery_resets_only_inflight_tasks(graph_store: CoordinationGraphStore) -> None:
    _run(graph_store)
    graph_store.create_task(Task(task_id="inflight", run_id="test_run", domain="general",
                                 capability_id="core.read", goal="inflight", status=TaskStatus.RUNNING,
                                 claimed_by="worker", lease_expires_at="2099-01-01T00:00:00+00:00"))
    graph_store.create_task(Task(task_id="done", run_id="test_run", domain="general",
                                 capability_id="core.read", goal="done", status=TaskStatus.SUCCEEDED,
                                 result_data={"done": True}))
    recovered = DependencyScheduler(graph_store).recover_run("test_run")
    assert recovered is not None
    assert graph_store.get_task("inflight").status == TaskStatus.READY
    assert graph_store.get_task("done").status == TaskStatus.SUCCEEDED


def test_capability_readiness_is_explicit() -> None:
    result = CAPABILITY_REGISTRY.readiness("cybersecurity")
    assert result["availability"] == CapabilityAvailability.PLANNED.value
    assert result["capabilities"][0]["capability_id"] == "cyber.reachability"
    assert result["reason"].startswith("Registry readiness only")
    assert "executor" not in CAPABILITY_REGISTRY.get("cyber.reachability").to_dict()


def test_source_independence_uses_transitive_provenance() -> None:
    result = evaluate_source_independence([
        {"source_id": "primary", "origin_family_id": "family_a"},
        {"source_id": "reprint", "derived_from_source_id": "primary"},
        {"source_id": "same_hash", "content_sha256": "abc"},
        {"source_id": "same_hash_copy", "content_sha256": "ABC"},
        {"source_id": "unknown"},
    ])
    assert result["independent_families"] == 3
    assert result["duplicate_citations_discounted"] == 2
    assert result["verification_effect"] == "none; source authority and validity require separate checks"


def test_governance_never_approves_or_executes() -> None:
    governance = DeterministicGovernance(None)
    proposal = ActionProposal(proposal_id="prop", task_id="task", run_id="run",
                             action_type="WRITE", target_entity_id="entity", reversible=True)
    result = governance.evaluate_proposal(proposal, evidence_fresh=True)
    assert result["decision"] == "ELIGIBLE_FOR_REVIEW"
    assert result["executed"] is False
    assert proposal.status == "ELIGIBLE_FOR_REVIEW"


def test_broad_unlearning_fails_closed_without_receipt(graph_store: CoordinationGraphStore) -> None:
    with pytest.raises(GovernedDeletionUnavailable, match="No data was changed"):
        VerifiedUnlearningEngine(graph_store).verified_delete(
            entity_id="old_record", entity_type="Runbook", authority="operator", reason="obsolete"
        )
