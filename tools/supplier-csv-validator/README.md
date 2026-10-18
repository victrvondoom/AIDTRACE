# GreenChain Supplier CSV Validator

A dependency-free Python tool that validates and normalizes GreenChain supplier
and sourcing-scenario CSV files. It reports every rejected record with its
source row and field, exports the clean records, and never invents supplier
information or silently turns invalid values into valid-looking data.

It runs on the Python standard library alone — no API keys, no FalkorDB, no
network access, no AI model.

Version: 1.1.1 (schema `supplier_csv_v1`).

## Quick start

```bash
python cli.py --input examples/valid_suppliers.csv --output output/
python cli.py --input examples/invalid_suppliers.csv --output output/
python cli.py --input examples/ --output output/          # batch mode
```

## Column format

The column names and value rules follow the existing GreenChain import format
(read-only sources: `backend/domains/greenchain/sample-upload.csv`,
`backend/domains/greenchain/dataset_intakes.py`, and the
`ScenarioComponentRequest` model in `backend/domains/greenchain/main.py`).

Required columns:

| Column | Rule |
|---|---|
| `product` | non-empty text, max 200 chars |
| `quantity` | positive plain-decimal number (`1e3`, `.5`, `5.` ok; `1,000`, `1_000`, `nan`, `inf` rejected) |
| `destination` | ISO 3166-1 alpha-2 country code |
| `transport_mode` | one of `sea`, `air`, `rail`, `road` |
| `component` | non-empty text, max 200 chars |
| `current_manufacturer` | non-empty text, max 200 chars |
| `current_country` | ISO 3166-1 alpha-2 country code |

Optional columns:

| Column | Rule |
|---|---|
| `unit` | text, max 50 chars; empty value warns (`missing_unit`) |
| `target_count` | positive whole number (`6.0` accepted as `6`) |
| `current_city` | text, max 100 chars |
| `current_website` | text, max 500 chars; non-`http(s)://` values warn (`suspicious_website`) |
| `current_certifications` | pipe-separated list |
| `current_disclosure_status` | `verified`, `partial` or `none` |
| `current_revenue_usd_m` | number >= 0.01 |
| `current_renewable_pct` | number in 0..100 |
| `countries` | pipe-separated ISO 3166-1 alpha-2 codes |
| `require_certifications` | pipe-separated list |
| `shipment_weight_kg` | number >= 0 (negative values are rejected) |

Unknown extra columns are passed through to `cleaned.csv` unchanged apart from
whitespace normalization, formula-prefix, control-character and length checks.

## Error codes

Every rejected record appears in `errors.json` with its physical source row
number (header = row 1), the failing field, a machine-readable code, and a
human-readable message. The raw record is included for review.

| Code | Meaning |
|---|---|
| `missing_value` | a required column is empty in this row |
| `invalid_country_code` | `destination`, `current_country` or a `countries` item is not an ISO 3166-1 alpha-2 code |
| `invalid_quantity` | `quantity` is not a positive plain-decimal number |
| `negative_shipment_weight` | `shipment_weight_kg` is negative |
| `invalid_shipment_weight` | `shipment_weight_kg` is not a number |
| `unsupported_transport_mode` | `transport_mode` is not `sea`/`air`/`rail`/`road` |
| `duplicate_supplier_record` | same `product` + `component` + `current_manufacturer` + `current_country` as an earlier accepted row (message names the first-seen row) |
| `invalid_target_count` | `target_count` is not a positive whole number |
| `invalid_revenue_usd_m` | `current_revenue_usd_m` is not a number >= 0.01 |
| `invalid_renewable_pct` | `current_renewable_pct` is not a number in 0..100 |
| `field_too_long` | a text field exceeds its per-column limit (500 chars for unknown columns) |
| `dangerous_formula_prefix` | cell starts with `=`, `+`, `-`, `@`, or contains a raw tab/CR (numeric cells included — `"5\t"` is rejected even though the digits parse) — rejected, never sanitized |
| `invalid_control_character` | cell contains NUL, DEL, VT, FF or another control character (outside `\t`, `\n`, `\r`) |
| `unsupported_disclosure_status` | `current_disclosure_status` is not `verified`/`partial`/`none` |
| `row_has_extra_columns` | row has more columns than the header |

File-level errors (the file cannot be processed at all; no rows are read).
Every header problem is reported at once, not just the first:

| Code | Meaning |
|---|---|
| `empty_file` | no header row (zero bytes, BOM-only, whitespace/blank-line-only) |
| `empty_header` | a header cell is blank |
| `duplicate_header` | the same header name appears twice |
| `invalid_header` | a header name contains a control character |
| `missing_required_columns` | one or more required columns are absent (message lists them) |
| `invalid_encoding` | file is not UTF-8 / UTF-8 with BOM |

Warnings (the record stays accepted; only emitted for accepted rows):

| Code | Meaning |
|---|---|
| `suspicious_website` | `current_website` does not start with `http://` or `https://` |
| `missing_unit` | the `unit` column exists in the file but is empty for this row |

## Normalization

- Header names: trimmed and lowercased (like `dataset_intakes.py`).
- Text: surrounding whitespace removed, internal whitespace runs collapsed
  to single spaces (an embedded newline in a quoted cell becomes a space).
- Country codes: trimmed and uppercased (`us` -> `US`); invalid codes are
  rejected, never repaired.
- Transport mode and disclosure status: trimmed and lowercased.
- Numbers: canonical text (`8000.0` -> `8000`, `28.50` -> `28.5`, `1e3` ->
  `1000`), never scientific notation, always parsing back to the identical
  value.
- Pipe lists: items trimmed, empty items dropped (` a | | b ` -> `a|b`).

The tool does not invent values: empty optional columns stay empty, and no
invalid value is ever coerced into a valid-looking one.

## Outputs

`cleaned.csv` — accepted records, normalized, UTF-8, same column order as the
input file.

`errors.json` — file-level errors, rejected records (row, field, code,
message, raw record) and warnings.

`summary.json`:

```json
{
  "input_file": "examples/invalid_suppliers.csv",
  "input_sha256": "…provenance hash of the input bytes…",
  "schema_version": "supplier_csv_v1",
  "headers": ["product", "quantity", "…"],
  "total_rows": 16,
  "accepted_rows": 1,
  "rejected_rows": 15,
  "warning_count": 1,
  "rejected_by_code": {"invalid_quantity": 2, "…": "…"},
  "warnings_by_code": {"suspicious_website": 1}
}
```

`input_sha256` is the SHA-256 of the raw input bytes (for in-memory
validation, of the BOM-stripped text) so every report is traceable to the
exact source file.

In batch mode, each input file additionally gets its own subdirectory under
`--output` (named after the file; colliding stems such as `a.csv` and
`a.CSV` get a numeric suffix so outputs cannot overwrite each other), and a
top-level `combined_summary.json` aggregates per-file status, totals, exit
codes and hashes (including the batch's overall `exit_code`).

## CLI reference

```
python cli.py --input <file.csv | directory> [--output DIR] [--strict] [--quiet] [--version]
```

- `--input` (required): a `.csv` file, or a directory — in directory mode every
  `*.csv` inside is processed into `<output>/<file name>/`.
- `--output` (default `output`): output directory. Must not be an existing file.
- `--strict`: warnings also cause exit code 1.
- `--quiet`: no progress output on stdout.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | no rejected rows (warnings allowed unless `--strict`) |
| 1 | one or more rows rejected (or, with `--strict`, any warning) |
| 2 | input unusable: missing file, non-`.csv` file, bad encoding, no header, missing/duplicate header columns, output path is a file, batch directory has no `.csv` files. Batch mode returns the worst per-file code. |

## Tests

```bash
python -m unittest discover -s tests -v
```

139 deterministic unit tests covering valid input, all missing-column cases,
missing values, invalid countries, duplicates, invalid quantities and the
strict numeric grammar, unsupported transport modes, CSV injection (text and
numeric cells), control characters including DEL, empty files, Unicode and
encodings, normalization, provenance, output accuracy, CLI flags, batch mode
(including output-name dedupe and unreadable files), and a 2000-row smoke
test.

The code is lint-clean under the tool's own `ruff.toml` ruleset
(`ruff check .` from this directory).

## Limitations

- One contract only (`supplier_csv_v1`); no header auto-mapping.
- The duplicate rule is "first accepted row wins": a duplicate of a row that
  was itself rejected is not additionally flagged as duplicate.
- Row numbers are physical end-of-record line numbers from `csv.reader`, so a
  row with a quoted embedded newline reports the line where the record ends.
- Entirely blank lines are skipped (like `dataset_intakes.py`) and do not
  count as rows — including blank lines that precede the header row.
- A signed numeric cell like `-50` in `shipment_weight_kg` keeps its
  negative-value error code; only tabs/CRs inside numeric cells are treated
  as injection vectors.
