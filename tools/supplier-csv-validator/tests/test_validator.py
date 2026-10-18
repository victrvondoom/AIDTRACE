"""Unit tests for the GreenChain supplier CSV validator.

Deterministic, standard library only. Run from the tool directory:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cli
import validator
from validator import (
    ISO2_COUNTRIES,
    ValidatorFileError,
    validate_file,
    validate_text,
    write_outputs,
)

HEADER = [
    "product",
    "quantity",
    "unit",
    "destination",
    "transport_mode",
    "target_count",
    "component",
    "current_manufacturer",
    "current_country",
    "current_city",
    "current_website",
    "current_certifications",
    "current_disclosure_status",
    "current_revenue_usd_m",
    "current_renewable_pct",
    "countries",
    "shipment_weight_kg",
]

DEFAULT_ROW = {
    "product": "LED desk lamp",
    "quantity": "8000",
    "unit": "units",
    "destination": "US",
    "transport_mode": "sea",
    "target_count": "6",
    "component": "aluminum housing",
    "current_manufacturer": "MetalForm Precision",
    "current_country": "CN",
    "current_city": "Shenzhen",
    "current_website": "https://example.com",
    "current_certifications": "iso14001|sbt_committed",
    "current_disclosure_status": "verified",
    "current_revenue_usd_m": "38",
    "current_renewable_pct": "22",
    "countries": "CN|TW",
    "shipment_weight_kg": "450.5",
}


def build_csv(rows: list[dict[str, str]], header: list[str] | None = None) -> str:
    """Serialize rows (DEFAULT_ROW merged with overrides) into CSV text."""
    header = header if header is not None else HEADER
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        merged = dict(DEFAULT_ROW)
        merged.update(row)
        writer.writerow([merged.get(column, "") for column in header])
    return buffer.getvalue()


def validate_rows(rows: list[dict[str, str]], header: list[str] | None = None):
    return validate_text(build_csv(rows, header), input_name="test.csv")


class ValidInputTests(unittest.TestCase):
    def test_valid_rows_all_accepted(self):
        result = validate_rows([{}, {"component": "led module"}])
        self.assertEqual(result.file_errors, [])
        self.assertEqual(len(result.accepted_rows), 2)
        self.assertEqual(result.rejected, [])
        self.assertEqual(result.warnings, [])

    def test_unknown_column_is_preserved(self):
        result = validate_rows(
            [{"notes": "checked by QA"}], header=HEADER + ["notes"]
        )
        self.assertEqual(result.file_errors, [])
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(result.accepted_rows[0]["notes"], "checked by QA")


class MissingColumnTests(unittest.TestCase):
    def test_missing_required_column_is_file_error(self):
        header = [c for c in HEADER if c != "current_country"]
        result = validate_rows([{}], header=header)
        self.assertEqual(len(result.file_errors), 1)
        self.assertEqual(result.file_errors[0]["code"], "missing_required_columns")
        self.assertIn("current_country", result.file_errors[0]["message"])

    def test_file_error_prevents_row_processing(self):
        header = [c for c in HEADER if c != "quantity"]
        result = validate_rows([{}, {}, {}], header=header)
        self.assertEqual(result.accepted_rows, [])
        self.assertEqual(result.rejected, [])
        self.assertEqual(result.total_rows, 0)

    def test_duplicate_header_is_file_error(self):
        result = validate_rows([{}], header=HEADER + ["product"])
        self.assertEqual(len(result.file_errors), 1)
        self.assertEqual(result.file_errors[0]["code"], "duplicate_header")

    def test_empty_header_name_is_file_error(self):
        result = validate_rows([{}], header=HEADER + [" "])
        self.assertEqual(len(result.file_errors), 1)
        self.assertEqual(result.file_errors[0]["code"], "empty_header")


class MissingValueTests(unittest.TestCase):
    def test_empty_required_value_rejected(self):
        result = validate_rows([{"component": ""}])
        self.assertEqual(len(result.rejected), 1)
        codes = {error.code for error in result.rejected[0].errors}
        self.assertIn("missing_value", codes)

    def test_missing_value_error_has_row_and_field(self):
        result = validate_rows([{"current_manufacturer": ""}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.row, 2)
        self.assertEqual(error.field, "current_manufacturer")
        self.assertEqual(error.code, "missing_value")

    def test_empty_required_quantity_is_missing_value(self):
        result = validate_rows([{"quantity": ""}])
        self.assertEqual(len(result.rejected), 1)
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "quantity")
        self.assertEqual(error.code, "missing_value")


class CountryTests(unittest.TestCase):
    def test_invalid_destination_rejected(self):
        result = validate_rows([{"destination": "USA"}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "destination")
        self.assertEqual(error.code, "invalid_country_code")

    def test_invalid_current_country_rejected(self):
        result = validate_rows([{"current_country": "china"}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "current_country")
        self.assertEqual(error.code, "invalid_country_code")

    def test_invalid_country_in_pipe_list_rejected(self):
        result = validate_rows([{"countries": "CN|XX"}])
        codes = [error.code for error in result.rejected[0].errors]
        self.assertEqual(codes, ["invalid_country_code"])
        self.assertEqual(result.rejected[0].errors[0].field, "countries")

    def test_country_code_case_normalized(self):
        result = validate_rows([{"destination": "us", "current_country": " cn "}])
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(result.accepted_rows[0]["destination"], "US")
        self.assertEqual(result.accepted_rows[0]["current_country"], "CN")

    def test_pipe_country_items_uppercased(self):
        result = validate_rows([{"countries": "cn|tw"}])
        self.assertEqual(result.accepted_rows[0]["countries"], "CN|TW")

    def test_iso2_set_valid_members(self):
        for code in ("CN", "US", "DE", "TW", "RO", "KR"):
            self.assertIn(code, ISO2_COUNTRIES)

    def test_iso2_set_rejects_non_members(self):
        for code in ("XX", "ZZ", "USA", "CHINA", "C1", ""):
            self.assertNotIn(code, ISO2_COUNTRIES)


class DuplicateTests(unittest.TestCase):
    def test_duplicate_supplier_record_rejected(self):
        result = validate_rows([{}, {}])
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(len(result.rejected), 1)
        error = result.rejected[0].errors[0]
        self.assertEqual(error.row, 3)
        self.assertEqual(error.code, "duplicate_supplier_record")

    def test_duplicate_first_occurrence_accepted(self):
        result = validate_rows([{}, {}])
        self.assertEqual(result.accepted_rows[0]["current_manufacturer"], "MetalForm Precision")

    def test_different_component_is_not_duplicate(self):
        result = validate_rows([{}, {"component": "led module"}])
        self.assertEqual(len(result.accepted_rows), 2)
        self.assertEqual(result.rejected, [])


class QuantityTests(unittest.TestCase):
    def test_quantity_zero_rejected(self):
        result = validate_rows([{"quantity": "0"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_quantity_negative_rejected(self):
        result = validate_rows([{"quantity": "-100"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_quantity_text_rejected(self):
        result = validate_rows([{"quantity": "eight thousand"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_quantity_nan_rejected(self):
        result = validate_rows([{"quantity": "nan"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_quantity_inf_rejected(self):
        result = validate_rows([{"quantity": "inf"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_quantity_normalized_to_canonical(self):
        result = validate_rows([{"quantity": " 8000.0 "}])
        self.assertEqual(result.accepted_rows[0]["quantity"], "8000")


class TransportModeTests(unittest.TestCase):
    def test_unsupported_transport_mode_rejected(self):
        result = validate_rows([{"transport_mode": "horse"}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "transport_mode")
        self.assertEqual(error.code, "unsupported_transport_mode")

    def test_all_greenchain_modes_accepted(self):
        for mode in ("sea", "air", "rail", "road"):
            result = validate_rows([{"transport_mode": mode}])
            self.assertEqual(len(result.accepted_rows), 1, mode)

    def test_transport_mode_case_normalized(self):
        result = validate_rows([{"transport_mode": " SEA "}])
        self.assertEqual(result.accepted_rows[0]["transport_mode"], "sea")


class CsvInjectionTests(unittest.TestCase):
    def test_formula_prefix_equals_rejected(self):
        result = validate_rows([{"product": "=cmd|' /C calc.exe"}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "product")
        self.assertEqual(error.code, "dangerous_formula_prefix")

    def test_formula_prefix_plus_at_minus_rejected(self):
        for value in ("+SUM(A1:A2)", "@SUM(A1:A2)", "-2+3|cmd"):
            result = validate_rows([{"product": value}])
            self.assertEqual(result.rejected[0].errors[0].code, "dangerous_formula_prefix", value)

    def test_formula_in_numeric_field_rejected(self):
        result = validate_rows([{"quantity": "=1+1"}])
        self.assertEqual(result.rejected[0].errors[0].code, "dangerous_formula_prefix")

    def test_tab_inside_cell_rejected(self):
        result = validate_rows([{"current_manufacturer": "Metal\tForm"}])
        self.assertEqual(result.rejected[0].errors[0].code, "dangerous_formula_prefix")

    def test_formula_row_not_normalized_into_cleaned(self):
        result = validate_rows([{"product": "=cmd"}])
        self.assertEqual(result.accepted_rows, [])


class ShipmentWeightTests(unittest.TestCase):
    def test_negative_shipment_weight_rejected(self):
        result = validate_rows([{"shipment_weight_kg": "-50"}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "shipment_weight_kg")
        self.assertEqual(error.code, "negative_shipment_weight")

    def test_nonnumeric_shipment_weight_rejected(self):
        result = validate_rows([{"shipment_weight_kg": "heavy"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_shipment_weight")

    def test_shipment_weight_normalized(self):
        result = validate_rows([{"shipment_weight_kg": "75.50"}])
        self.assertEqual(result.accepted_rows[0]["shipment_weight_kg"], "75.5")

    def test_empty_shipment_weight_allowed(self):
        result = validate_rows([{"shipment_weight_kg": ""}])
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(result.accepted_rows[0]["shipment_weight_kg"], "")


class EmptyFileTests(unittest.TestCase):
    def test_zero_byte_file_is_file_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.csv"
            path.write_bytes(b"")
            result = validate_file(path)
        self.assertEqual(len(result.file_errors), 1)
        self.assertEqual(result.file_errors[0]["code"], "empty_file")

    def test_empty_text_is_file_error(self):
        result = validate_text("", input_name="test.csv")
        self.assertEqual(result.file_errors[0]["code"], "empty_file")

    def test_header_only_file_processes_zero_rows(self):
        text = ",".join(HEADER) + "\n"
        result = validate_text(text, input_name="test.csv")
        self.assertEqual(result.file_errors, [])
        self.assertEqual(result.total_rows, 0)
        self.assertEqual(result.accepted_rows, [])
        self.assertEqual(result.headers, HEADER)


class UnicodeTests(unittest.TestCase):
    def test_unicode_text_preserved(self):
        result = validate_rows([{"current_city": "Iași", "product": "Öko-Stofftasche"}])
        accepted = result.accepted_rows[0]
        self.assertEqual(accepted["current_city"], "Iași")
        self.assertEqual(accepted["product"], "Öko-Stofftasche")

    def test_non_utf8_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latin1.csv"
            path.write_bytes("product,quantity\nTüllamp,öö\n".encode("latin-1"))
            with self.assertRaises(ValidatorFileError):
                validate_file(path)

    def test_utf8_bom_handled(self):
        text = build_csv([{}])
        result = validate_text("\ufeff" + text, input_name="test.csv")
        self.assertEqual(len(result.accepted_rows), 1)


class NormalizationTests(unittest.TestCase):
    def test_whitespace_collapsed(self):
        result = validate_rows(
            [{"current_manufacturer": "  Metal   Form  ", "product": " LED  lamp\nPro "}]
        )
        accepted = result.accepted_rows[0]
        self.assertEqual(accepted["current_manufacturer"], "Metal Form")
        self.assertEqual(accepted["product"], "LED lamp Pro")

    def test_pipe_list_cleaned(self):
        result = validate_rows([{"current_certifications": " iso14001 | | sbt_committed "}])
        self.assertEqual(
            result.accepted_rows[0]["current_certifications"], "iso14001|sbt_committed"
        )

    def test_empty_optional_stays_empty(self):
        result = validate_rows(
            [{"current_city": "", "countries": "", "current_website": ""}]
        )
        accepted = result.accepted_rows[0]
        self.assertEqual(accepted["current_city"], "")
        self.assertEqual(accepted["countries"], "")
        self.assertEqual(accepted["current_website"], "")

    def test_disclosure_status_case_normalized(self):
        result = validate_rows([{"current_disclosure_status": "VERIFIED"}])
        self.assertEqual(
            result.accepted_rows[0]["current_disclosure_status"], "verified"
        )

    def test_revenue_normalized(self):
        result = validate_rows([{"current_revenue_usd_m": "38.50"}])
        self.assertEqual(result.accepted_rows[0]["current_revenue_usd_m"], "38.5")


class OtherValidationTests(unittest.TestCase):
    def test_invalid_target_count_text_rejected(self):
        result = validate_rows([{"target_count": "six"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_target_count")

    def test_invalid_target_count_fraction_rejected(self):
        result = validate_rows([{"target_count": "6.5"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_target_count")

    def test_invalid_revenue_rejected(self):
        result = validate_rows([{"current_revenue_usd_m": "abc"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_revenue_usd_m")

    def test_revenue_below_minimum_rejected(self):
        result = validate_rows([{"current_revenue_usd_m": "0"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_revenue_usd_m")

    def test_renewable_pct_out_of_range_rejected(self):
        result = validate_rows([{"current_renewable_pct": "150"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_renewable_pct")

    def test_field_too_long_rejected(self):
        result = validate_rows([{"current_manufacturer": "M" * 201}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "current_manufacturer")
        self.assertEqual(error.code, "field_too_long")

    def test_unsupported_disclosure_status_rejected(self):
        result = validate_rows([{"current_disclosure_status": "maybe"}])
        self.assertEqual(
            result.rejected[0].errors[0].code, "unsupported_disclosure_status"
        )

    def test_row_with_extra_columns_rejected(self):
        text = ",".join(HEADER) + "\n" + ",".join(["x"] * (len(HEADER) + 1)) + "\n"
        result = validate_text(text, input_name="test.csv")
        self.assertEqual(result.rejected[0].errors[0].code, "row_has_extra_columns")

    def test_blank_lines_skipped(self):
        text = build_csv([{}]) + "\n" + build_csv([{"component": "led module"}]).split("\n", 1)[1]
        result = validate_text(text, input_name="test.csv")
        self.assertEqual(len(result.accepted_rows), 2)
        self.assertEqual(result.total_rows, 2)

    def test_rejected_record_contains_raw_values(self):
        result = validate_rows([{"destination": "USA"}])
        self.assertEqual(result.rejected[0].raw["destination"], "USA")
        self.assertEqual(result.rejected[0].row, 2)


class WarningTests(unittest.TestCase):
    def test_suspicious_website_warning(self):
        result = validate_rows([{"current_website": "example.com/sustainability"}])
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].code, "suspicious_website")
        self.assertEqual(result.warnings[0].field, "current_website")

    def test_missing_unit_warning(self):
        result = validate_rows([{"unit": ""}])
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(result.warnings[0].code, "missing_unit")

    def test_no_warning_on_rejected_row(self):
        result = validate_rows(
            [{"transport_mode": "horse", "current_website": "example.com"}]
        )
        self.assertEqual(len(result.rejected), 1)
        self.assertEqual(result.warnings, [])

    def test_no_warning_on_duplicate_row(self):
        result = validate_rows(
            [{}, {"current_website": "example.com"}]
        )
        self.assertEqual(len(result.rejected), 1)
        self.assertEqual(result.rejected[0].errors[0].code, "duplicate_supplier_record")
        self.assertEqual(result.warnings, [])


class OutputTests(unittest.TestCase):
    def test_write_outputs_creates_three_files(self):
        result = validate_rows([{}, {"destination": "USA"}])
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_outputs(result, tmp)
            for key in ("cleaned_csv", "errors", "summary"):
                self.assertTrue(Path(paths[key]).exists(), key)

    def test_summary_counts_accurate(self):
        result = validate_rows(
            [
                {},
                {"destination": "USA"},
                {"quantity": "0"},
                {"current_website": "example.com", "component": "power adapter"},
            ]
        )
        summary = result.summary()
        self.assertEqual(summary["total_rows"], 4)
        self.assertEqual(summary["accepted_rows"], 2)
        self.assertEqual(summary["rejected_rows"], 2)
        self.assertEqual(summary["warning_count"], 1)
        self.assertEqual(summary["rejected_by_code"]["invalid_country_code"], 1)
        self.assertEqual(summary["rejected_by_code"]["invalid_quantity"], 1)
        self.assertEqual(summary["warnings_by_code"]["suspicious_website"], 1)

    def test_errors_json_structure(self):
        result = validate_rows([{"destination": "USA"}])
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_outputs(result, tmp)
            doc = json.loads(Path(paths["errors"]).read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], "supplier_csv_v1")
        rejected = doc["rejected"][0]
        self.assertEqual(rejected["row"], 2)
        self.assertEqual(rejected["errors"][0]["field"], "destination")
        self.assertEqual(rejected["errors"][0]["code"], "invalid_country_code")
        self.assertEqual(rejected["record"]["destination"], "USA")
        self.assertIn("message", rejected["errors"][0])

    def test_cleaned_csv_roundtrip(self):
        result = validate_rows([{}, {"component": "led module"}])
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_outputs(result, tmp)
            with open(paths["cleaned_csv"], encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
        self.assertEqual(rows[0], HEADER)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][0], "LED desk lamp")
        self.assertEqual(rows[2][6], "led module")


class CliTests(unittest.TestCase):
    def _write_input(self, tmp: str, text: str, name: str = "input.csv") -> str:
        path = Path(tmp) / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_cli_exit_zero_on_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_input(tmp, build_csv([{}]))
            out = Path(tmp) / "out"
            code = cli.main(["--input", source, "--output", str(out)])
            self.assertEqual(code, 0)
            self.assertTrue((out / "cleaned.csv").exists())

    def test_cli_exit_one_on_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_input(tmp, build_csv([{"destination": "USA"}]))
            out = Path(tmp) / "out"
            code = cli.main(["--input", source, "--output", str(out)])
            self.assertEqual(code, 1)

    def test_cli_exit_two_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = cli.main(
                ["--input", str(Path(tmp) / "nope.csv"), "--output", tmp]
            )
            self.assertEqual(code, 2)

    def test_cli_exit_two_on_missing_required_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            header = [c for c in HEADER if c != "quantity"]
            source = self._write_input(
                tmp, build_csv([{}], header=header), name="bad.csv"
            )
            code = cli.main(["--input", source, "--output", tmp])
            self.assertEqual(code, 2)
            errors = json.loads((Path(tmp) / "errors.json").read_text(encoding="utf-8"))
            self.assertEqual(errors["file_errors"][0]["code"], "missing_required_columns")

    def test_cli_rejects_non_csv_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_input(tmp, build_csv([{}]), name="input.txt")
            code = cli.main(["--input", source, "--output", tmp])
            self.assertEqual(code, 2)

    def test_cli_on_example_files(self):
        base = Path(__file__).parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            code = cli.main(
                [
                    "--input", str(base / "examples" / "valid_suppliers.csv"),
                    "--output", tmp,
                ]
            )
            self.assertEqual(code, 0)
            code = cli.main(
                [
                    "--input", str(base / "examples" / "invalid_suppliers.csv"),
                    "--output", tmp,
                ]
            )
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
