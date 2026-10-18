"""GreenChain supplier CSV validation and normalization.

Column names and value rules follow the existing GreenChain import format:

- ``backend/domains/greenchain/sample-upload.csv`` (supplier row shape)
- ``backend/domains/greenchain/dataset_intakes.py`` (scenario CSV contract:
  required headers, transport modes, quantity rule)
- ``backend/domains/greenchain/main.py`` ``ScenarioComponentRequest``
  (ISO-2 country codes, disclosure statuses, revenue/renewable ranges)

Standard library only. No API keys, database, network, or AI model required.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = "supplier_csv_v1"

# Mirrors VALID_TRANSPORT_MODES in dataset_intakes.py and TRANSPORT_MODES in transport.py.
VALID_TRANSPORT_MODES = {"sea", "air", "rail", "road"}

# Mirrors ScenarioComponentRequest.current_disclosure_status.
VALID_DISCLOSURE_STATUSES = {"verified", "partial", "none"}

# Columns of sample-upload.csv plus the optional scenario columns from
# dataset_intakes.py (countries, require_certifications) and the shipment
# weight field used by the GreenChain transport model (weight_kg).
REQUIRED_COLUMNS = (
    "product",
    "quantity",
    "destination",
    "transport_mode",
    "component",
    "current_manufacturer",
    "current_country",
)
OPTIONAL_COLUMNS = (
    "unit",
    "target_count",
    "current_city",
    "current_website",
    "current_certifications",
    "current_disclosure_status",
    "current_revenue_usd_m",
    "current_renewable_pct",
    "countries",
    "require_certifications",
    "shipment_weight_kg",
)
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Fields parsed as numbers. Values: (parse kind, minimum, maximum, error code).
# "positive_*" kinds treat the minimum as exclusive (quantity > 0),
# "float" kinds treat it as inclusive (revenue >= 0.01, like GreenChain ge=0.01).
NUMERIC_FIELDS = {
    "quantity": ("positive_float", 0.0, None, "invalid_quantity"),
    "target_count": ("positive_int", 0.0, None, "invalid_target_count"),
    "current_revenue_usd_m": ("float", 0.01, None, "invalid_revenue_usd_m"),
    "current_renewable_pct": ("float", 0.0, 100.0, "invalid_renewable_pct"),
    "shipment_weight_kg": ("float", 0.0, None, "invalid_shipment_weight"),
}

COUNTRY_FIELDS = ("destination", "current_country")
PIPE_LIST_FIELDS = ("current_certifications", "countries", "require_certifications")

# Duplicate identity: same product component from the same supplier country.
DUPLICATE_KEY = ("product", "component", "current_manufacturer", "current_country")

MAX_FIELD_LENGTHS = {
    "product": 200,
    "unit": 50,
    "component": 200,
    "current_manufacturer": 200,
    "current_city": 100,
    "current_website": 500,
    "current_certifications": 200,
    "current_disclosure_status": 20,
    "countries": 200,
    "require_certifications": 200,
}
DEFAULT_MAX_FIELD_LENGTH = 500

# Spreadsheet formula injection prefixes (OWASP CSV injection vectors).
# FORMULA_PREFIXES are checked on the first character of a cell;
# DANGEROUS_PREFIXES additionally lists in-cell tab/CR, which are injection
# vectors and never survive into cleaned.csv.
FORMULA_PREFIXES = ("=", "+", "-", "@")
DANGEROUS_PREFIXES = FORMULA_PREFIXES + ("\t", "\r")

# Strict decimal grammar for CSV numeric fields. Deliberately stricter than
# float(): rejects Python-isms such as "1_000" (underscore separators),
# "nan", "inf", "0x1F", and localized forms such as "1,000" or "1.000,5".
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

# C0 control characters that are neither whitespace handled by the CSV layer
# (\t, \n, \r) nor acceptable in a text cell (NUL, VT, FF, SOH, ...).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# ISO 3166-1 alpha-2 country codes.
ISO2_COUNTRIES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
    BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
    CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
    DE DJ DK DM DO DZ
    EC EE EG EH ER ES ET
    FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
    HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT
    JE JM JO JP
    KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY
    MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
    NA NC NE NF NG NI NL NO NP NR NU NZ
    OM
    PA PE PF PG PH PK PL PM PN PR PS PT PW PY
    QA
    RE RO RS RU RW
    SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
    TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ
    UA UG UM US UY UZ
    VA VC VE VG VI VN VU
    WF WS
    YE YT
    ZA ZM ZW
    """.split()
)

_WHITESPACE_RE = re.compile(r"\s+")


class ValidatorFileError(Exception):
    """Raised when an input CSV cannot be processed at all."""


@dataclass
class RowError:
    row: int
    field: str
    code: str
    message: str


@dataclass
class RowWarning:
    row: int
    field: str
    code: str
    message: str


@dataclass
class RejectedRecord:
    row: int
    errors: list[RowError] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class FileResult:
    input_file: str
    input_sha256: str = ""
    file_errors: list[dict[str, str]] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    accepted_rows: list[dict[str, str]] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)
    warnings: list[RowWarning] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return len(self.accepted_rows) + len(self.rejected)

    def summary(self) -> dict[str, object]:
        rejected_by_code: dict[str, int] = {}
        for record in self.rejected:
            for err in record.errors:
                rejected_by_code[err.code] = rejected_by_code.get(err.code, 0) + 1
        warnings_by_code: dict[str, int] = {}
        for warn in self.warnings:
            warnings_by_code[warn.code] = warnings_by_code.get(warn.code, 0) + 1
        return {
            "input_file": self.input_file,
            "input_sha256": self.input_sha256,
            "schema_version": SCHEMA_VERSION,
            "headers": list(self.headers),
            "total_rows": self.total_rows,
            "accepted_rows": len(self.accepted_rows),
            "rejected_rows": len(self.rejected),
            "warning_count": len(self.warnings),
            "rejected_by_code": dict(sorted(rejected_by_code.items())),
            "warnings_by_code": dict(sorted(warnings_by_code.items())),
        }


def normalize_text(value: str) -> str:
    """Trim and collapse internal whitespace (incl. newlines/tabs) to spaces."""
    return _WHITESPACE_RE.sub(" ", value.strip())


def normalize_country(value: str) -> str:
    """Uppercase an ISO-2 country code. Does not invent or repair bad codes."""
    return value.strip().upper()


def format_number(number: float) -> str:
    """Canonical numeric text.

    Integral values lose the trailing '.0'; non-integral values use the
    shortest exact decimal form and never scientific notation. The output
    always parses back to the identical float.
    """
    if number.is_integer():
        return str(int(number))
    text = repr(number)
    if "e" not in text and "E" not in text:
        return text
    # Scientific notation: find the shortest plain-decimal expansion that
    # still parses back to the identical float.
    for precision in range(1, 31):
        expanded = format(number, f".{precision}f").rstrip("0").rstrip(".")
        if expanded and float(expanded) == number:
            return expanded
    return text


def parse_number(value: str) -> float | None:
    """Parse a finite plain-decimal number. Returns None for anything else.

    Accepts optional sign, integer or fractional decimal digits, and an
    optional decimal exponent (``1e3``). Rejects underscores, hex, NaN,
    infinity, localized separators, and anything non-numeric.
    """
    text = value.strip()
    if not _NUMBER_RE.match(text):
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _is_dangerous(value: str) -> bool:
    """Spreadsheet formula prefix, or a raw tab/CR inside the cell."""
    trimmed = value.strip()
    if not trimmed:
        return False
    if "\t" in value or "\r" in value:
        return True
    return trimmed[0] in FORMULA_PREFIXES


def _has_control_characters(value: str) -> bool:
    """NUL, VT, FF and other C0 controls that are not \t, \n or \r."""
    return _CONTROL_RE.search(value) is not None


def _check_formula(row: int, name: str, value: str, code: str) -> RowError | None:
    if _is_dangerous(value):
        return RowError(
            row=row,
            field=name,
            code=code,
            message=f"{name} starts with a dangerous spreadsheet formula prefix.",
        )
    return None


def _validate_country(row: int, name: str, value: str) -> RowError | None:
    code = normalize_country(value)
    if code not in ISO2_COUNTRIES:
        return RowError(
            row=row,
            field=name,
            code="invalid_country_code",
            message=f"{name} must be an ISO 3166-1 alpha-2 country code, got {value!r}.",
        )
    return None


def _validate_pipe_countries(row: int, name: str, value: str) -> list[RowError]:
    errors: list[RowError] = []
    for item in _split_pipe_list(value):
        if item.upper() not in ISO2_COUNTRIES:
            errors.append(
                RowError(
                    row=row,
                    field=name,
                    code="invalid_country_code",
                    message=f"{name} contains invalid country code {item!r}.",
                )
            )
    return errors


def _split_pipe_list(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _join_pipe_list(items: list[str]) -> str:
    return "|".join(items)


def _validate_numeric(
    row: int, name: str, value: str
) -> tuple[float | None, list[RowError]]:
    """Returns (parsed number or None, errors)."""
    kind, minimum, maximum, code = NUMERIC_FIELDS[name]
    number = parse_number(value)
    if number is None:
        formula_error = _check_formula(row, name, value, "dangerous_formula_prefix")
        if formula_error is not None:
            return None, [formula_error]
        return None, [
            RowError(
                row=row,
                field=name,
                code=code,
                message=f"{name} must be a number, got {value!r}.",
            )
        ]
    below_minimum = number < minimum or (
        kind.startswith("positive") and number == minimum
    )
    if below_minimum or (maximum is not None and number > maximum):
        if name == "shipment_weight_kg":
            return None, [
                RowError(
                    row=row,
                    field=name,
                    code="negative_shipment_weight",
                    message="shipment_weight_kg must not be negative.",
                )
            ]
        upper_bound = maximum if maximum is not None else "unbounded"
        return None, [
            RowError(
                row=row,
                field=name,
                code=code,
                message=f"{name} is outside the supported range ({minimum}..{upper_bound}).",
            )
        ]
    if kind == "positive_int" and number != int(number):
        return None, [
            RowError(
                row=row,
                field=name,
                code=code,
                message=f"{name} must be a whole number, got {value!r}.",
            )
        ]
    return number, []


def _validate_row(row_number: int, row: list[str], headers: list[str]) -> tuple[dict[str, str], list[RowError], list[RowWarning]]:
    """Validate one data row. Returns (normalized values, errors, warnings)."""
    errors: list[RowError] = []
    warnings: list[RowWarning] = []
    if len(row) > len(headers):
        errors.append(
            RowError(
                row=row_number,
                field="",
                code="row_has_extra_columns",
                message="Row has more columns than the header.",
            )
        )
    padded = row + [""] * (len(headers) - len(row))
    raw = {header: value for header, value in zip(headers, padded)}
    normalized: dict[str, str] = {}
    errored_fields: set[str] = set()

    def fail(error: RowError) -> None:
        errors.append(error)
        if error.field:
            errored_fields.add(error.field)

    for name, value in raw.items():
        if name in NUMERIC_FIELDS:
            if not value.strip():
                if name in REQUIRED_COLUMNS:
                    fail(
                        RowError(
                            row=row_number,
                            field=name,
                            code="missing_value",
                            message=f"{name} is required and must not be empty.",
                        )
                    )
                else:
                    normalized[name] = ""
                continue
            number, numeric_errors = _validate_numeric(row_number, name, value)
            for error in numeric_errors:
                fail(error)
            if number is not None:
                normalized[name] = format_number(number)
            continue

        if _is_dangerous(value):
            formula_error = _check_formula(row_number, name, value, "dangerous_formula_prefix")
            if formula_error is not None:
                fail(formula_error)
            continue

        if _has_control_characters(value):
            fail(
                RowError(
                    row=row_number,
                    field=name,
                    code="invalid_control_character",
                    message=f"{name} contains a control character (NUL, VT, FF or similar).",
                )
            )
            continue

        if name in COUNTRY_FIELDS:
            normalized[name] = normalize_country(value)
            country_error = _validate_country(row_number, name, value)
            if country_error is not None:
                fail(country_error)
            continue

        if name in PIPE_LIST_FIELDS:
            items = _split_pipe_list(normalize_text(value))
            if name == "countries":
                items = [item.upper() for item in items]
                for error in _validate_pipe_countries(row_number, name, value):
                    fail(error)
            normalized[name] = _join_pipe_list(items)
            continue

        if name == "transport_mode":
            mode = normalize_text(value).lower()
            normalized[name] = mode
            if mode not in VALID_TRANSPORT_MODES:
                valid = ", ".join(sorted(VALID_TRANSPORT_MODES))
                fail(
                    RowError(
                        row=row_number,
                        field=name,
                        code="unsupported_transport_mode",
                        message=f"transport_mode must be one of: {valid}; got {value!r}.",
                    )
                )
            continue

        if name == "current_disclosure_status":
            status = normalize_text(value).lower()
            normalized[name] = status
            if status not in VALID_DISCLOSURE_STATUSES:
                valid = ", ".join(sorted(VALID_DISCLOSURE_STATUSES))
                fail(
                    RowError(
                        row=row_number,
                        field=name,
                        code="unsupported_disclosure_status",
                        message=f"current_disclosure_status must be one of: {valid}; got {value!r}.",
                    )
                )
            continue

        # Plain text column (required, optional, or unknown pass-through).
        text = normalize_text(value)
        normalized[name] = text
        limit = MAX_FIELD_LENGTHS.get(name, DEFAULT_MAX_FIELD_LENGTH)
        if len(text) > limit:
            fail(
                RowError(
                    row=row_number,
                    field=name,
                    code="field_too_long",
                    message=f"{name} exceeds the maximum length of {limit} characters.",
                )
            )

    for name in REQUIRED_COLUMNS:
        if name in errored_fields:
            continue
        if not normalized.get(name, "").strip():
            fail(
                RowError(
                    row=row_number,
                    field=name,
                    code="missing_value",
                    message=f"{name} is required and must not be empty.",
                )
            )

    # Warnings (record stays acceptable). Only fields whose column exists in
    # this file can warn: a file without a `unit` column is not "missing" it.
    if "unit" in raw and not raw["unit"].strip():
        warnings.append(
            RowWarning(
                row=row_number,
                field="unit",
                code="missing_unit",
                message="unit is empty; the record is accepted but lacks a unit of measure.",
            )
        )
    if "current_website" in raw:
        website = raw["current_website"].strip()
        if website and not (
            website.lower().startswith("http://")
            or website.lower().startswith("https://")
        ):
            warnings.append(
                RowWarning(
                    row=row_number,
                    field="current_website",
                    code="suspicious_website",
                    message="current_website does not start with http:// or https://.",
                )
            )

    return normalized, errors, warnings


def _parse_headers(raw_headers: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Normalize header names like dataset_intakes.py: strip + lower."""
    headers: list[str] = []
    file_errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_header in raw_headers:
        normalized = raw_header.strip().lower()
        if not normalized:
            file_errors.append(
                {"code": "empty_header", "message": "Header names cannot be empty."}
            )
            return [], file_errors
        if _has_control_characters(normalized):
            file_errors.append(
                {
                    "code": "invalid_header",
                    "message": f"Header name contains a control character: {raw_header!r}.",
                }
            )
            return [], file_errors
        if normalized in seen:
            file_errors.append(
                {"code": "duplicate_header", "message": f"Duplicate header: {normalized}"}
            )
            return [], file_errors
        seen.add(normalized)
        headers.append(normalized)
    missing = [name for name in REQUIRED_COLUMNS if name not in seen]
    if missing:
        file_errors.append(
            {
                "code": "missing_required_columns",
                "message": "Missing required header(s): " + ", ".join(missing),
            }
        )
    return headers, file_errors


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_text(
    text: str, input_name: str = "input.csv", sha256: str | None = None
) -> FileResult:
    """Validate CSV text against the GreenChain supplier contract.

    ``sha256`` optionally supplies the provenance hash of the source bytes
    (``validate_file`` passes the raw file bytes); by default the hash of the
    BOM-stripped text is used.
    """
    result = FileResult(
        input_file=input_name,
        input_sha256=sha256 if sha256 is not None else "",
    )
    if text.startswith("\ufeff"):  # UTF-8 BOM, mirrors utf-8-sig file decoding
        text = text[1:]
    if not result.input_sha256:
        result.input_sha256 = _sha256_hex(text)

    reader = csv.reader(io.StringIO(text))
    header_row = next(reader, None)
    if header_row is None or not any(cell.strip() for cell in header_row):
        result.file_errors.append(
            {
                "code": "empty_file",
                "message": "CSV must include a header row and one data row.",
            }
        )
        return result

    headers, header_errors = _parse_headers(header_row)
    result.file_errors.extend(header_errors)
    if header_errors:
        return result
    result.headers = headers

    seen_keys: dict[tuple[str, str, str, str], int] = {}
    for row in reader:
        row_number = reader.line_num
        if not any(cell.strip() for cell in row):
            continue  # entirely blank lines are skipped, like dataset_intakes.py
        normalized, errors, warnings = _validate_row(row_number, row, headers)
        if errors:
            raw = {header: value for header, value in zip(headers, row + [""] * (len(headers) - len(row)))}
            result.rejected.append(RejectedRecord(row=row_number, errors=errors, raw=raw))
            continue
        key = tuple(normalized.get(name, "") for name in DUPLICATE_KEY)
        if key in seen_keys:
            result.rejected.append(
                RejectedRecord(
                    row=row_number,
                    errors=[
                        RowError(
                            row=row_number,
                            field=",".join(DUPLICATE_KEY),
                            code="duplicate_supplier_record",
                            message=(
                                "Duplicate supplier record (product, component, "
                                "current_manufacturer, current_country already seen at "
                                f"row {seen_keys[key]})."
                            ),
                        )
                    ],
                    raw={header: value for header, value in zip(headers, row + [""] * (len(headers) - len(row)))},
                )
            )
            continue
        seen_keys[key] = row_number
        result.warnings.extend(warnings)
        result.accepted_rows.append(normalized)
    return result


def validate_file(path: str | Path) -> FileResult:
    """Read a CSV file (UTF-8 / UTF-8 with BOM) and validate it."""
    input_path = Path(path)
    if not input_path.exists():
        raise ValidatorFileError(f"Input file not found: {input_path}")
    if input_path.is_dir():
        raise ValidatorFileError(
            f"Input is a directory: {input_path}. Pass a .csv file (or use batch mode)."
        )
    if input_path.suffix.lower() != ".csv":
        raise ValidatorFileError("Only .csv files are supported.")
    data = input_path.read_bytes()
    if not data:
        result = FileResult(input_file=str(input_path), input_sha256=_sha256_hex(""))
        result.file_errors.append(
            {
                "code": "empty_file",
                "message": "CSV must include a header row and one data row.",
            }
        )
        return result
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        # Still emit outputs for provenance even when decoding fails.
        result = FileResult(input_file=str(input_path), input_sha256=sha256)
        result.file_errors.append(
            {"code": "invalid_encoding", "message": "CSV must be UTF-8 encoded."}
        )
        return result
    return validate_text(text, input_name=str(input_path), sha256=sha256)


def write_outputs(result: FileResult, output_dir: str | Path) -> dict[str, str]:
    """Write cleaned.csv, errors.json and summary.json into output_dir."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    cleaned_path = out / "cleaned.csv"
    with cleaned_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if result.headers:
            writer.writerow(result.headers)
        for record in result.accepted_rows:
            writer.writerow([record.get(header, "") for header in result.headers])

    errors_doc = {
        "input_file": result.input_file,
        "input_sha256": result.input_sha256,
        "schema_version": SCHEMA_VERSION,
        "file_errors": result.file_errors,
        "rejected": [
            {
                "row": record.row,
                "errors": [
                    {"field": err.field, "code": err.code, "message": err.message}
                    for err in record.errors
                ],
                "record": dict(sorted(record.raw.items())),
            }
            for record in result.rejected
        ],
        "warnings": [
            {"row": warn.row, "field": warn.field, "code": warn.code, "message": warn.message}
            for warn in result.warnings
        ],
    }
    errors_path = out / "errors.json"
    errors_path.write_text(
        json.dumps(errors_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary_path = out / "summary.json"
    summary_path.write_text(
        json.dumps(result.summary(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "cleaned_csv": str(cleaned_path),
        "errors": str(errors_path),
        "summary": str(summary_path),
    }
