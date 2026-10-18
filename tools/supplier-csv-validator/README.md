# GreenChain Supplier CSV Validator

A dependency-free Python tool that validates and normalizes GreenChain supplier
and sourcing-scenario CSV files. It reports every rejected record with its
source row and field, exports the clean records, and never invents supplier
information or silently turns invalid values into valid-looking data.

It runs on the Python standard library alone — no API keys, no FalkorDB, no
network access, no AI model.

## Column format

The column names and value rules follow the existing GreenChain import format
(read-only sources: `backend/domains/greenchain/sample-upload.csv`,
`backend/domains/greenchain/dataset_intakes.py`, and the
`ScenarioComponentRequest` model in `backend/domains/greenchain/main.py`).

Required columns:

| Column | Rule |
|---|---|
| `product` | non-empty text |
| `quantity` | positive number |
| `destination` | ISO 3166-1 alpha-2 country code |
| `transport_mode` | one of `sea`, `air`, `rail`, `road` |
| `component` | non-empty text |
| `current_manufacturer` | non-empty text |
| `current_country` | ISO 3166-1 alpha-2 country code |

Optional columns: `unit`, `target_count` (positive whole number),
`current_city`, `current_website`, `current_certifications` (pipe-separated),
`current_disclosure_status` (`verified` | `partial` | `none`),
`current_revenue_usd_m` (>= 0.01), `current_renewable_pct` (0..100),
`countries` (pipe-separated ISO-2 codes), `require_certifications`
(pipe-separated), `shipment_weight_kg` (>= 0; negative weights are rejected).

Unknown extra columns are passed through to `cleaned.csv` unchanged apart
from whitespace normalization, formula-prefix, and length checks.

## Validation checks

1. Missing required columns (file-level error)
2. Empty required values
3. Invalid country codes (ISO 3166-1 alpha-2, embedded list)
4. Invalid quantities (must be a positive, finite number)
5. Negative shipment weights
6. Unsupported transport modes (`sea`, `air`, `rail`, `road`)
7. Duplicate supplier records (same `product`, `component`,
   `current_manufacturer`, `current_country`; first occurrence wins)
8. Invalid numeric values (`target_count`, `current_revenue_usd_m`,
   `current_renewable_pct`, `shipment_weight_kg`)
9. Excessively long text fields (per-column limits)
10. Dangerous spreadsheet formula prefixes (`=`, `+`, `-`, `@`, tab, CR —
    rejected, never sanitized)

Warnings (record stays accepted): `current_website` without an `http://` or
`https://` prefix, and an empty `unit`. Warnings are only emitted for accepted
rows.

## Normalization

- Header names: trimmed and lowercased (like `dataset_intakes.py`).
- Text: surrounding whitespace removed, internal whitespace runs collapsed to
  single spaces.
- Country codes: trimmed and uppercased (`us` -> `US`); invalid codes are
  rejected, not repaired.
- Transport mode and disclosure status: trimmed and lowercased.
- Numbers: canonical text (`8000.0` -> `8000`, `28.50` -> `28.5`).
- Pipe lists: items trimmed, empty items dropped (` a | | b ` -> `a|b`).

## Run

```bash
python cli.py --input examples/valid_suppliers.csv --output output/
```

Outputs in `--output` (default `output/`):

- `cleaned.csv` — accepted records, normalized, UTF-8.
- `errors.json` — rejected records (source row, field, code, message, raw
  record) plus file-level errors and warnings.
- `summary.json` — `total_rows`, `accepted_rows`, `rejected_rows`,
  `warning_count`, and per-code breakdowns.

Exit codes: `0` = no rejected rows, `1` = one or more rejected rows,
`2` = input unusable (missing file, non-`.csv` extension, wrong encoding,
no header, missing/duplicate header columns).

## Tests

```bash
python -m unittest discover -s tests -v
```

72 deterministic unit tests covering valid input, missing columns, missing
values, invalid countries, duplicates, invalid quantities, unsupported
transport modes, CSV injection, empty files, Unicode, normalization, and
output accuracy.
