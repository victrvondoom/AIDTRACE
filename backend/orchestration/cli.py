"""Command line: ``python -m orchestration doctor | validate | run``.

Exit codes: 0 success, 1 run incomplete or failed, 2 usage or configuration error,
3 SGLang server not healthy, 130 interrupted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .backends import ChatBackend, ScriptedBackend, SGLangBackend
from .config import Settings
from .doctor import Health, probe
from .errors import ConfigError, OrchestrationError
from .scheduler import RetryPolicy, RunResult, TaskState, run_workflow
from .tools import ToolRegistry, load_registry
from .trace import Trace
from .workflow import Workflow, load_workflow

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_USAGE = 2
EXIT_UNHEALTHY = 3
EXIT_INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m orchestration",
        description="Run LLM agent workflows on an SGLang server, or on a scripted dry-run backend.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    doctor = commands.add_parser("doctor", help="check that the SGLang server answers and serves the model")
    _connection_options(doctor)
    doctor.add_argument("--ping", action="store_true", help="also run one 4-token completion")
    doctor.add_argument("--json", action="store_true", help="print the report as JSON")

    validate = commands.add_parser("validate", help="check a workflow file without calling any model")
    validate.add_argument("workflow", type=Path)
    validate.add_argument("--tools", metavar="MODULE:ATTR", help="ToolRegistry used to check tool grants")

    run = commands.add_parser("run", help="execute a workflow")
    run.add_argument("workflow", type=Path)
    run.add_argument(
        "--backend",
        choices=("sglang", "scripted"),
        default="sglang",
        help="'scripted' echoes its input and is not a model",
    )
    _connection_options(run)
    run.add_argument("--tools", metavar="MODULE:ATTR", help="ToolRegistry the agents may call")
    run.add_argument("--out", type=Path, help="write the full JSON trace to this file")
    run.add_argument("--json", action="store_true", help="print the run summary as JSON")
    run.add_argument("--retry-base-s", type=float, default=0.5, help="base backoff between retries, in seconds")
    return parser


def _connection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", help="SGLang URL (default: SGLANG_BASE_URL or http://127.0.0.1:30000)")
    parser.add_argument("--model", help="model name the server serves (default: SGLANG_MODEL)")


def cmd_validate(args: argparse.Namespace) -> int:
    registry = load_registry(args.tools) if args.tools else ToolRegistry()
    workflow = load_workflow(args.workflow, tools=registry)
    print(
        f"OK: {workflow.name!r}: {len(workflow.tasks)} tasks, {len(workflow.agents)} agents, "
        f"policy {workflow.failure_policy}"
    )
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    base_url = args.base_url or settings.sglang_base_url
    model = args.model or settings.sglang_model
    report = asyncio.run(
        probe(
            base_url,
            api_key=settings.sglang_api_key,
            model=model,
            ping=args.ping,
            timeout_s=settings.request_timeout_s,
        )
    )
    generation_failed = report.generation is not None and report.generation.startswith("FAILED")
    if args.json:
        payload = {
            "base_url": report.base_url,
            "status": report.status.value,
            "detail": report.detail,
            "models": list(report.models),
            "requested_model": report.requested_model,
            "generation": report.generation,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"{report.status.value}: {report.detail}")
        if report.generation is not None:
            print(f"generation: {report.generation}")
    healthy = report.status is Health.OK and not generation_failed
    return EXIT_OK if healthy else EXIT_UNHEALTHY


def cmd_run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if args.retry_base_s < 0:
        raise ConfigError("--retry-base-s must not be negative")
    registry = load_registry(args.tools) if args.tools else ToolRegistry()
    workflow = load_workflow(args.workflow, tools=registry)
    backend = _make_backend(args, settings)
    if args.backend == "scripted":
        print("note: scripted backend; outputs echo the input and are not model answers", file=sys.stderr)

    trace = Trace(secrets=[settings.sglang_api_key] if settings.sglang_api_key else [])
    result = asyncio.run(_execute(workflow, backend, registry, trace, RetryPolicy(base_s=args.retry_base_s)))

    if args.out:
        args.out.write_text(trace.to_json(), encoding="utf-8")
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_summary(result)
    return EXIT_OK if result.status == "SUCCEEDED" else EXIT_INCOMPLETE


def _make_backend(args: argparse.Namespace, settings: Settings) -> ChatBackend:
    if args.backend == "scripted":
        return ScriptedBackend()
    model = args.model or settings.sglang_model
    if not model:
        raise ConfigError(
            "no model selected: pass --model or set SGLANG_MODEL "
            "(`python -m orchestration doctor` shows what the server serves)"
        )
    return SGLangBackend(
        base_url=args.base_url or settings.sglang_base_url,
        model=model,
        api_key=settings.sglang_api_key,
        timeout_s=settings.request_timeout_s,
        max_concurrency=settings.max_concurrency,
    )


async def _execute(
    workflow: Workflow,
    backend: ChatBackend,
    registry: ToolRegistry,
    trace: Trace,
    retry: RetryPolicy,
) -> RunResult:
    try:
        return await run_workflow(workflow, backend=backend, tools=registry, trace=trace, retry=retry)
    finally:
        close: Callable[[], object] | None = getattr(backend, "aclose", None)
        if close is not None:
            await close()


def _print_summary(result: RunResult) -> None:
    print(f"workflow {result.workflow!r}: {result.status}")
    width = max(len(task_id) for task_id in result.states)
    for task_id, state in result.states.items():
        note = result.errors.get(task_id, "")
        print(f"  {task_id:<{width}}  {state.value:<10}  {note}".rstrip())
        if state is TaskState.SUCCEEDED:
            preview = result.outputs[task_id][:200].replace("\n", " / ")
            print(f"  {'':<{width}}  {'':<10}  -> {preview}")
    print(f"{len(result.trace.events)} trace events")


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # model text may hold characters the console cannot show
    args = build_parser().parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "doctor": cmd_doctor,
        "validate": cmd_validate,
        "run": cmd_run,
    }
    try:
        return handlers[args.command](args)
    except OrchestrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
