"""Command-line behaviour: validation, dry runs, trace output, and usage errors. No model or server is used."""

import json
from pathlib import Path

import pytest
from orchestration.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "orchestration" / "examples" / "demo_workflow.json"
TOOLS = "orchestration.examples.demo_tools:REGISTRY"


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch):
    for name in ("SGLANG_BASE_URL", "SGLANG_MODEL", "SGLANG_API_KEY", "ORCH_REQUEST_TIMEOUT_S", "ORCH_MAX_CONCURRENCY"):
        monkeypatch.delenv(name, raising=False)


def test_validate_accepts_the_example(capsys):
    assert main(["validate", str(EXAMPLE), "--tools", TOOLS]) == 0
    assert "OK: 'brief-from-notes'" in capsys.readouterr().out


def test_validate_without_the_tool_registry_reports_the_missing_grant(capsys):
    assert main(["validate", str(EXAMPLE)]) == 2
    assert "unregistered tools: word_count" in capsys.readouterr().err


def test_validate_reports_malformed_json_with_a_location(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text('{"name": "x",', encoding="utf-8")
    assert main(["validate", str(broken)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_dry_run_writes_a_trace_and_a_json_summary(tmp_path, capsys):
    trace_path = tmp_path / "trace.json"
    code = main(["run", str(EXAMPLE), "--backend", "scripted", "--tools", TOOLS, "--out", str(trace_path), "--json"])
    assert code == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "SUCCEEDED"
    assert summary["tasks"]["brief"]["state"] == "SUCCEEDED"

    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    types = [event["type"] for event in trace["events"]]
    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_COMPLETED"


def test_sglang_run_needs_a_model_and_says_how_to_get_one(capsys):
    assert main(["run", str(EXAMPLE), "--tools", TOOLS]) == 2
    assert "no model selected" in capsys.readouterr().err


def test_an_invalid_base_url_is_a_usage_error(capsys):
    code = main(["run", str(EXAMPLE), "--tools", TOOLS, "--model", "m", "--base-url", "ftp://nope"])
    assert code == 2
    assert "base URL" in capsys.readouterr().err


def test_negative_retry_backoff_is_rejected(capsys):
    code = main(["run", str(EXAMPLE), "--backend", "scripted", "--tools", TOOLS, "--retry-base-s", "-1"])
    assert code == 2
    assert "must not be negative" in capsys.readouterr().err
