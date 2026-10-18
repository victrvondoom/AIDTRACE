"""Command-line interface for the GreenChain supplier CSV validator.

Usage:
    python cli.py --input examples/valid_suppliers.csv --output output/

Exit codes:
    0  input processed, no rejected rows (warnings allowed)
    1  input processed, one or more rows rejected
    2  input could not be processed (missing file, bad encoding, no header,
       missing required columns)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from validator import ValidatorFileError, validate_file, write_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and normalize GreenChain supplier CSV files."
    )
    parser.add_argument("--input", required=True, help="Path to the input CSV file.")
    parser.add_argument(
        "--output",
        default="output",
        help="Directory for cleaned.csv, errors.json and summary.json (default: output).",
    )
    args = parser.parse_args(argv)

    try:
        result = validate_file(args.input)
    except ValidatorFileError as exc:
        print(f"error: {exc}")
        return 2

    paths = write_outputs(result, args.output)

    if result.file_errors:
        for file_error in result.file_errors:
            print(f"error: {file_error['message']}")
        print(f"error: no rows processed; see {paths['errors']}")
        return 2

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

    if summary["rejected_rows"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
