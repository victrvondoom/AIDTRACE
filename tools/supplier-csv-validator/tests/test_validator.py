"""Unit tests for the GreenChain supplier CSV validator.

Deterministic, standard library only. Run from the tool directory:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cli
import validator
from validator import (
    ISO2_COUNTRIES,
    ValidatorFileError,
    format_number,
    parse_number,
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


class CountrySetIntegrityTests(unittest.TestCase):
    def test_iso2_set_has_249_codes(self):
        self.assertEqual(len(ISO2_COUNTRIES), 249)

    def test_iso2_codes_are_two_uppercase_letters(self):
        for code in ISO2_COUNTRIES:
            self.assertEqual(len(code), 2, code)
            self.assertTrue(code.isalpha(), code)
            self.assertTrue(code.isupper(), code)


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

    def test_duplicate_message_names_first_seen_row(self):
        result = validate_rows(
            [{}, {"component": "led module"}, {}]
        )
        message = result.rejected[0].errors[0].message
        self.assertIn("row 2", message)

    def test_duplicate_of_rejected_row_not_flagged(self):
        # Two identical rows that are both invalid for their own reasons:
        # neither is accepted, so neither registers the duplicate key.
        result = validate_rows(
            [{"destination": "USA"}, {"destination": "USA"}]
        )
        self.assertEqual(len(result.rejected), 2)
        for record in result.rejected:
            self.assertEqual(
                [error.code for error in record.errors], ["invalid_country_code"]
            )


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

    def test_quantity_overflow_rejected(self):
        result = validate_rows([{"quantity": "1e400"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_quantity_normalized_to_canonical(self):
        result = validate_rows([{"quantity": " 8000.0 "}])
        self.assertEqual(result.accepted_rows[0]["quantity"], "8000")


class NumericGrammarTests(unittest.TestCase):
    def test_underscore_separator_rejected(self):
        # Python float("1_000") == 1000.0; CSV data must not allow it.
        self.assertIsNone(parse_number("1_000"))
        result = validate_rows([{"quantity": "1_000"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_hex_rejected(self):
        self.assertIsNone(parse_number("0x1F"))
        result = validate_rows([{"quantity": "0x1F"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_leading_dot_fraction_accepted(self):
        result = validate_rows([{"quantity": ".5"}])
        self.assertEqual(result.accepted_rows[0]["quantity"], "0.5")

    def test_trailing_dot_accepted(self):
        result = validate_rows([{"quantity": "5."}])
        self.assertEqual(result.accepted_rows[0]["quantity"], "5")

    def test_leading_plus_accepted(self):
        result = validate_rows([{"quantity": "+5"}])
        self.assertEqual(result.accepted_rows[0]["quantity"], "5")

    def test_scientific_notation_accepted(self):
        result = validate_rows([{"quantity": "1e3"}])
        self.assertEqual(result.accepted_rows[0]["quantity"], "1000")

    def test_surrounding_whitespace_accepted(self):
        result = validate_rows([{"quantity": " 5 "}])
        self.assertEqual(result.accepted_rows[0]["quantity"], "5")

    def test_thousands_separator_rejected(self):
        result = validate_rows([{"quantity": "1,000"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_quantity")

    def test_empty_string_is_not_a_number(self):
        self.assertIsNone(parse_number(""))


class FormatNumberTests(unittest.TestCase):
    def test_integral_values_lose_decimal_point(self):
        self.assertEqual(format_number(8000.0), "8000")
        self.assertEqual(format_number(-0.0), "0")

    def test_no_scientific_notation(self):
        self.assertEqual(format_number(1e-07), "0.0000001")
        self.assertEqual(format_number(1e20), "100000000000000000000")

    def test_large_near_integer_not_rounded(self):
        # 999999999999.9 is not integral and must not silently become 1e12.
        self.assertEqual(format_number(999999999999.9), "999999999999.9")

    def test_output_roundtrips_to_same_float(self):
        for value in (8000.0, 28.5, 0.1, 1e-07, 123.456, 999999999999.9, 0.01, 100.0):
            self.assertEqual(float(format_number(value)), value, value)


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


class ControlCharacterTests(unittest.TestCase):
    def test_nul_in_cell_rejected(self):
        result = validate_rows([{"product": "bad\x00name"}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "product")
        self.assertEqual(error.code, "invalid_control_character")

    def test_vertical_tab_and_form_feed_rejected(self):
        for value in ("bad\x0bname", "bad\x0cname"):
            result = validate_rows([{"current_city": value}])
            self.assertEqual(
                result.rejected[0].errors[0].code, "invalid_control_character", value
            )

    def test_control_char_in_header_is_file_error(self):
        text = ",".join(HEADER) + ",bad\x00column\n" + build_csv([{}]).split("\n", 1)[1]
        result = validate_text(text, input_name="test.csv")
        self.assertEqual(len(result.file_errors), 1)
        self.assertEqual(result.file_errors[0]["code"], "invalid_header")

    def test_newline_and_tab_are_not_control_char_errors(self):
        # \n inside a quoted cell is legitimate; \t is reported as a formula
        # vector, never as an accepted value.
        result = validate_rows([{"product": "Multi\nLine"}])
        self.assertEqual(result.accepted_rows[0]["product"], "Multi Line")


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

    def test_zero_shipment_weight_allowed(self):
        result = validate_rows([{"shipment_weight_kg": "0"}])
        self.assertEqual(len(result.accepted_rows), 1)


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

    def test_whitespace_only_file_is_file_error(self):
        result = validate_text(" \n \n", input_name="test.csv")
        self.assertEqual(result.file_errors[0]["code"], "empty_file")

    def test_bom_only_file_is_file_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bom.csv"
            path.write_bytes(b"\xef\xbb\xbf")
            result = validate_file(path)
        self.assertEqual(result.file_errors[0]["code"], "empty_file")


class UnicodeTests(unittest.TestCase):
    def test_unicode_text_preserved(self):
        result = validate_rows([{"current_city": "Iași", "product": "Öko-Stofftasche"}])
        accepted = result.accepted_rows[0]
        self.assertEqual(accepted["current_city"], "Iași")
        self.assertEqual(accepted["product"], "Öko-Stofftasche")

    def test_non_utf8_file_reports_encoding_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latin1.csv"
            path.write_bytes("product,quantity\nTüllamp,öö\n".encode("latin-1"))
            result = validate_file(path)
        self.assertEqual(len(result.file_errors), 1)
        self.assertEqual(result.file_errors[0]["code"], "invalid_encoding")

    def test_utf8_bom_handled(self):
        text = build_csv([{}])
        result = validate_text("\ufeff" + text, input_name="test.csv")
        self.assertEqual(len(result.accepted_rows), 1)

    def test_utf8_bom_file_handled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bom.csv"
            path.write_bytes(b"\xef\xbb\xbf" + build_csv([{}]).encode("utf-8"))
            result = validate_file(path)
        self.assertEqual(result.file_errors, [])
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

    def test_uppercase_header_normalized(self):
        header = [c.upper() for c in HEADER]
        result = validate_rows([{}], header=header)
        self.assertEqual(result.file_errors, [])
        self.assertEqual(result.headers, HEADER)


class OtherValidationTests(unittest.TestCase):
    def test_invalid_target_count_text_rejected(self):
        result = validate_rows([{"target_count": "six"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_target_count")

    def test_invalid_target_count_fraction_rejected(self):
        result = validate_rows([{"target_count": "6.5"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_target_count")

    def test_target_count_near_integer_rejected(self):
        # Exact whole-number check: 5.0000001 must not pass as 5.
        result = validate_rows([{"target_count": "5.0000001"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_target_count")

    def test_target_count_integral_float_accepted(self):
        result = validate_rows([{"target_count": "6.0"}])
        self.assertEqual(result.accepted_rows[0]["target_count"], "6")

    def test_invalid_revenue_rejected(self):
        result = validate_rows([{"current_revenue_usd_m": "abc"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_revenue_usd_m")

    def test_revenue_below_minimum_rejected(self):
        result = validate_rows([{"current_revenue_usd_m": "0"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_revenue_usd_m")

    def test_revenue_at_minimum_accepted(self):
        result = validate_rows([{"current_revenue_usd_m": "0.01"}])
        self.assertEqual(len(result.accepted_rows), 1)

    def test_renewable_pct_out_of_range_rejected(self):
        result = validate_rows([{"current_renewable_pct": "150"}])
        self.assertEqual(result.rejected[0].errors[0].code, "invalid_renewable_pct")

    def test_renewable_pct_bounds_accepted(self):
        for value in ("0", "100"):
            result = validate_rows([{"current_renewable_pct": value}])
            self.assertEqual(len(result.accepted_rows), 1, value)

    def test_field_too_long_rejected(self):
        result = validate_rows([{"current_manufacturer": "M" * 201}])
        error = result.rejected[0].errors[0]
        self.assertEqual(error.field, "current_manufacturer")
        self.assertEqual(error.code, "field_too_long")

    def test_field_at_length_limit_accepted(self):
        result = validate_rows([{"current_manufacturer": "M" * 200}])
        self.assertEqual(len(result.accepted_rows), 1)

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

    def test_rejected_record_raw_has_every_mapped_column(self):
        result = validate_rows([{"destination": "USA"}])
        self.assertEqual(set(result.rejected[0].raw.keys()), set(HEADER))

    def test_validate_file_rejects_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValidatorFileError):
                validate_file(tmp)


class CsvParsingTests(unittest.TestCase):
    def test_quoted_comma_field_accepted(self):
        result = validate_rows([{"product": "Lamp, desk variant"}])
        self.assertEqual(result.accepted_rows[0]["product"], "Lamp, desk variant")

    def test_multiline_quoted_field_line_numbering(self):
        # Row 2 spans physical lines 2-3; the next row is therefore line 4.
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(HEADER)
        merged = dict(DEFAULT_ROW)
        merged["product"] = "Multi\nLine"
        writer.writerow([merged.get(column, "") for column in HEADER])
        writer.writerow(
            [dict(DEFAULT_ROW, destination="USA").get(column, "") for column in HEADER]
        )
        result = validate_text(buffer.getvalue(), input_name="test.csv")
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(result.accepted_rows[0]["product"], "Multi Line")
        self.assertEqual(len(result.rejected), 1)
        self.assertEqual(result.rejected[0].row, 4)

    def test_crlf_file_accepted(self):
        text = build_csv([{"component": "led module"}]).replace("\n", "\r\n")
        result = validate_text(text, input_name="test.csv")
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(result.accepted_rows[0]["component"], "led module")

    def test_short_row_padded(self):
        # Only the 7 required columns are present; the row is accepted and
        # the normalized map contains exactly the file's own columns.
        values = ["LED desk lamp", "8000", "US", "sea", "aluminum housing", "MetalForm Precision", "CN"]
        text = "product,quantity,destination,transport_mode,component,current_manufacturer,current_country\n"
        text += ",".join(values) + "\n"
        result = validate_text(text, input_name="test.csv")
        self.assertEqual(len(result.accepted_rows), 1)
        self.assertEqual(
            set(result.accepted_rows[0].keys()),
            {
                "product",
                "quantity",
                "destination",
                "transport_mode",
                "component",
                "current_manufacturer",
                "current_country",
            },
        )


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

    def test_no_unit_warning_when_column_absent(self):
        header = [c for c in HEADER if c != "unit"]
        result = validate_rows(
            [{"component": "a"}, {"component": "b"}], header=header
        )
        self.assertEqual(len(result.accepted_rows), 2)
        self.assertEqual(result.warnings, [])

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


class ProvenanceTests(unittest.TestCase):
    def test_summary_contains_sha256_of_text(self):
        text = build_csv([{}])
        result = validate_text(text, input_name="test.csv")
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.assertEqual(result.input_sha256, expected)
        self.assertEqual(result.summary()["input_sha256"], expected)

    def test_summary_sha256_matches_file_bytes(self):
        payload = build_csv([{}]).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.csv"
            path.write_bytes(payload)
            result = validate_file(path)
        self.assertEqual(
            result.input_sha256, hashlib.sha256(payload).hexdigest()
        )

    def test_outputs_contain_sha256_and_headers(self):
        result = validate_rows([{}])
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_outputs(result, tmp)
            errors_doc = json.loads(Path(paths["errors"]).read_text(encoding="utf-8"))
            summary_doc = json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))
        self.assertIn("input_sha256", errors_doc)
        self.assertEqual(errors_doc["input_sha256"], result.input_sha256)
        self.assertEqual(summary_doc["headers"], HEADER)


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

    def test_rejected_and_warnings_ordered_by_row(self):
        rows = [{"destination": "USA"}, {}, {"quantity": "0"}, {}]
        header = [c for c in HEADER if c != "unit"]
        result = validate_text(build_csv(rows, header=header), input_name="test.csv")
        rejected_rows = [record.row for record in result.rejected]
        self.assertEqual(rejected_rows, sorted(rejected_rows))
        warning_rows = [warn.row for warn in result.warnings]
        self.assertEqual(warning_rows, sorted(warning_rows))


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

    def test_cli_exit_two_on_bad_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "latin1.csv"
            source.write_bytes("product,quantity\nTüllamp,öö\n".encode("latin-1"))
            code = cli.main(["--input", str(source), "--output", tmp])
            self.assertEqual(code, 2)
            errors = json.loads((Path(tmp) / "errors.json").read_text(encoding="utf-8"))
            self.assertEqual(errors["file_errors"][0]["code"], "invalid_encoding")

    def test_cli_rejects_non_csv_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_input(tmp, build_csv([{}]), name="input.txt")
            code = cli.main(["--input", source, "--output", tmp])
            self.assertEqual(code, 2)

    def test_cli_output_path_is_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_input(tmp, build_csv([{}]))
            blocker = Path(tmp) / "blocker.txt"
            blocker.write_text("not a directory", encoding="utf-8")
            code = cli.main(["--input", source, "--output", str(blocker)])
            self.assertEqual(code, 2)

    def test_cli_strict_warning_causes_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_input(
                tmp, build_csv([{"current_website": "example.com"}])
            )
            out = Path(tmp) / "out"
            self.assertEqual(
                cli.main(["--input", source, "--output", str(out), "--strict"]), 1
            )
            self.assertEqual(
                cli.main(["--input", source, "--output", str(out)]), 0
            )

    def test_cli_version_exits_zero(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("supplier-csv-validator", buffer.getvalue())

    def test_cli_quiet_suppresses_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_input(tmp, build_csv([{}]))
            out = Path(tmp) / "out"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.main(["--input", source, "--output", str(out), "--quiet"])
            self.assertEqual(code, 0)
            self.assertEqual(buffer.getvalue(), "")

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


class CliBatchTests(unittest.TestCase):
    def _make_batch_dir(self, tmp: str) -> str:
        batch = Path(tmp) / "batch"
        batch.mkdir()
        (batch / "clean.csv").write_text(build_csv([{}]), encoding="utf-8")
        (batch / "broken.csv").write_text(
            build_csv([{}, {"destination": "USA"}]), encoding="utf-8"
        )
        return str(batch)

    def test_batch_creates_per_file_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = self._make_batch_dir(tmp)
            out = Path(tmp) / "out"
            code = cli.main(["--input", batch, "--output", str(out)])
            self.assertEqual(code, 1)  # broken.csv has a rejection
            self.assertTrue((out / "clean" / "cleaned.csv").exists())
            self.assertTrue((out / "broken" / "cleaned.csv").exists())
            self.assertTrue((out / "broken" / "errors.json").exists())
            self.assertTrue((out / "combined_summary.json").exists())

    def test_batch_combined_summary_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = self._make_batch_dir(tmp)
            out = Path(tmp) / "out"
            cli.main(["--input", batch, "--output", str(out)])
            combined = json.loads(
                (out / "combined_summary.json").read_text(encoding="utf-8")
            )
        self.assertEqual(combined["mode"], "batch")
        self.assertEqual(combined["file_count"], 2)
        self.assertEqual(combined["totals"]["total_rows"], 3)
        self.assertEqual(combined["totals"]["accepted_rows"], 2)
        self.assertEqual(combined["totals"]["rejected_rows"], 1)
        statuses = {entry["input_file"]: entry["status"] for entry in combined["files"]}
        self.assertEqual(statuses[str(Path(batch) / "clean.csv")], "ok")
        self.assertEqual(statuses[str(Path(batch) / "broken.csv")], "rejected_rows")

    def test_batch_all_clean_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "batch"
            batch.mkdir()
            (batch / "a.csv").write_text(build_csv([{}]), encoding="utf-8")
            (batch / "b.csv").write_text(
                build_csv([{"component": "led module"}]), encoding="utf-8"
            )
            out = Path(tmp) / "out"
            code = cli.main(["--input", str(batch), "--output", str(out)])
            self.assertEqual(code, 0)

    def test_batch_strict_warning_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "batch"
            batch.mkdir()
            (batch / "a.csv").write_text(
                build_csv([{"current_website": "example.com"}]), encoding="utf-8"
            )
            out = Path(tmp) / "out"
            code = cli.main(["--input", str(batch), "--output", str(out), "--strict"])
            self.assertEqual(code, 1)
            code = cli.main(["--input", str(batch), "--output", str(out)])
            self.assertEqual(code, 0)

    def test_batch_empty_directory_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "batch"
            batch.mkdir()
            out = Path(tmp) / "out"
            code = cli.main(["--input", str(batch), "--output", str(out)])
            self.assertEqual(code, 2)

    def test_batch_ignores_non_csv_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "batch"
            batch.mkdir()
            (batch / "a.csv").write_text(build_csv([{}]), encoding="utf-8")
            (batch / "notes.txt").write_text("ignore me", encoding="utf-8")
            out = Path(tmp) / "out"
            code = cli.main(["--input", str(batch), "--output", str(out)])
            self.assertEqual(code, 0)
            combined = json.loads(
                (out / "combined_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(combined["file_count"], 1)


class SmokeTests(unittest.TestCase):
    def test_two_thousand_rows_processed(self):
        rows = [{"component": f"component {i}", "current_manufacturer": f"M{i}"} for i in range(2000)]
        text = build_csv(rows)
        started = time.monotonic()
        result = validate_text(text, input_name="big.csv")
        elapsed = time.monotonic() - started
        self.assertEqual(result.file_errors, [])
        self.assertEqual(len(result.accepted_rows), 2000)
        self.assertLess(elapsed, 30.0)


if __name__ == "__main__":
    unittest.main()
