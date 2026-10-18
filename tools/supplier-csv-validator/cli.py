"""Command-line interface for the GreenChain supplier CSV validator.

Single file:
    python cli.py --input examples/valid_suppliers.csv --output output/

Batch (every *.csv in a directory, each into output/<name>/):
    python cli.py --input examples/ --output output/

Exit codes:
    0  input processed, no rejected rows (warnings allowed unless --strict)
    1  one or more rows rejected (or, with --strict, any warning)
    2  input could not be processed (missing file, bad encoding, no header,
       missing required columns, unusable output path, empty batch)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from validator import (
    SCHEMA_VERSION,
    FileResult,
    ValidatorFileError,
    validate_file,
    write_outputs,
)

VERSION = "1.1.1"


def _exit_code(result: FileResult, *, strict: bool) -> int:
    """Return 0 clean, 1 rejections (or warnings under --strict), 2 file error."""
    if result.file_errors:
        return 2
    if result.rejected:
        return 1
    if strict and result.warnings:
        return 1
    return 0


def _print_report(
    result: FileResult, paths: dict[str, str], *, quiet: bool
) -> None:
    """Print the per-file processing report unless quiet."""
    if quiet:
        return
    summary = result.summary()
    print(
        f"processed {summary['total_rows']} rows: "
        f"{summary['accepted_rows']} accepted, "
        f"{summary['rejected_rows']} rejected, "
        f"{summary['warning_count']} warning(s)"
    )
    print(f"cleaned:  {paths['cleaned_csv']}")
    print(f"errors:   {paths['errors']}")
    print(f"summary:  {paths['summary']}")


def run_single(
    input_path: str, output_dir: str, *, strict: bool, quiet: bool
) -> int:
    """Validate one CSV file into output_dir; return the exit code."""
    try:
        result = validate_file(input_path)
    except ValidatorFileError as exc:
        if not quiet:
            print(f"error: {exc}")
        return 2

    paths = write_outputs(result, output_dir)

    if result.file_errors:
        if not quiet:
            for file_error in result.file_errors:
                print(f"error: {file_error['message']}")
            print(f"error: no rows processed; see {paths['errors']}")
        return 2

    _print_report(result, paths, quiet=quiet)
    return _exit_code(result, strict=strict)


def _batch_output_name(csv_path: Path, index: int, used_names: set[str]) -> str:
    """Return a unique output-directory name for one batch file.

    "a.csv" and "a.CSV" share a stem, so colliding stems get a numeric
    suffix; uniqueness is tracked case-insensitively so output paths cannot
    collide on Windows either.
    """
    name = csv_path.stem or f"file{index}"
    if name.lower() in used_names:
        suffix = 2
        while f"{name.lower()}_{suffix}" in used_names:
            suffix += 1
        name = f"{name}_{suffix}"
    used_names.add(name.lower())
    return name


def _process_batch_file(
    csv_path: Path,
    file_output: Path,
    *,
    strict: bool,
    quiet: bool,
    totals: dict[str, int],
) -> tuple[int, dict[str, object]]:
    """Validate one batch file, write its outputs, update the shared totals.

    Return (exit code, combined-summary entry for this file).
    """
    try:
        result = validate_file(csv_path)
    except ValidatorFileError as exc:
        if not quiet:
            print(f"error: {csv_path}: {exc}")
        totals["file_errors"] += 1
        return 2, {
            "input_file": str(csv_path),
            "status": "unusable",
            "error": str(exc),
            "output_dir": str(file_output),
        }
    write_outputs(result, file_output)
    summary = result.summary()
    code = _exit_code(result, strict=strict)
    totals["total_rows"] += summary["total_rows"]
    totals["accepted_rows"] += summary["accepted_rows"]
    totals["rejected_rows"] += summary["rejected_rows"]
    totals["warning_count"] += summary["warning_count"]
    if result.file_errors:
        totals["file_errors"] += 1
    if not quiet:
        print(
            f"{csv_path.name}: {summary['total_rows']} rows, "
            f"{summary['accepted_rows']} accepted, "
            f"{summary['rejected_rows']} rejected, "
            f"{summary['warning_count']} warning(s)"
        )
    return code, {
        "input_file": str(csv_path),
        "input_sha256": summary["input_sha256"],
        "status": (
            "file_error"
            if result.file_errors
            else ("rejected_rows" if result.rejected else "ok")
        ),
        "exit_code": code,
        "total_rows": summary["total_rows"],
        "accepted_rows": summary["accepted_rows"],
        "rejected_rows": summary["rejected_rows"],
        "warning_count": summary["warning_count"],
        "file_error_codes": [
            file_error["code"] for file_error in result.file_errors
        ],
        "output_dir": str(file_output),
    }


def run_batch(
    input_dir: str, output_dir: str, *, strict: bool, quiet: bool
) -> int:
    """Validate every .csv file in input_dir into per-file output dirs.

    Return the worst exit code across the batch.
    """
    directory = Path(input_dir)
    try:
        csv_files = sorted(
            path for path in directory.iterdir() if path.suffix.lower() == ".csv"
        )
    except OSError as exc:
        if not quiet:
            print(f"error: cannot read input directory: {exc}")
        return 2
    if not csv_files:
        if not quiet:
            print(f"error: no .csv files found in {directory}")
        return 2

    out = Path(output_dir)
    per_file: list[dict[str, object]] = []
    totals = {
        "total_rows": 0,
        "accepted_rows": 0,
        "rejected_rows": 0,
        "warning_count": 0,
        "file_errors": 0,
    }
    worst = 0
    used_names: set[str] = set()
    for index, csv_path in enumerate(csv_files):
        name = _batch_output_name(csv_path, index, used_names)
        file_output = out / name
        code, entry = _process_batch_file(
            csv_path, file_output, strict=strict, quiet=quiet, totals=totals
        )
        worst = max(worst, code)
        per_file.append(entry)

    combined = {
        "schema_version": SCHEMA_VERSION,
        "mode": "batch",
        "input_directory": str(directory),
        "file_count": len(csv_files),
        "exit_code": worst,
        "totals": dict(sorted(totals.items())),
        "files": per_file,
    }
    out.mkdir(parents=True, exist_ok=True)
    combined_path = out / "combined_summary.json"
    combined_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not quiet:
        print(
            f"batch: {len(csv_files)} file(s), "
            f"{totals['accepted_rows']} accepted, "
            f"{totals['rejected_rows']} rejected, "
            f"{totals['warning_count']} warning(s), "
            f"{totals['file_errors']} file error(s)"
        )
        print(f"summary:  {combined_path}")
    return worst


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run single-file or batch validation."""
    parser = argparse.ArgumentParser(
        prog="supplier-csv-validator",
        description=(
            "Validate and normalize GreenChain supplier CSV files. "
            "If --input is a directory, every .csv file inside is processed "
            "into its own subdirectory of --output."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input .csv file, or a directory of .csv files for batch mode.",
    )
    parser.add_argument(
        "--output",
        default="output",
        help="Directory for cleaned.csv, errors.json and summary.json "
        "(default: output). In batch mode each file gets a subdirectory.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures too (exit code 1).",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress progress output."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} (schema {SCHEMA_VERSION})",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)
    if output_path.exists() and not output_path.is_dir():
        print(f"error: --output exists and is not a directory: {output_path}")
        return 2

    try:
        if input_path.is_dir():
            return run_batch(
                str(input_path),
                str(output_path),
                strict=args.strict,
                quiet=args.quiet,
            )
        return run_single(
            str(input_path),
            str(output_path),
            strict=args.strict,
            quiet=args.quiet,
        )
    except OSError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
