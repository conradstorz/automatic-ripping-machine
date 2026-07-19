"""Tests for the History page filter-parsing helpers.

These pure functions normalise the /history query params (status + date
range) before the route builds its SQLAlchemy query. They are DB- and
Flask-free so they can be unit-tested directly, the same way the Settings
redesign extracted build_field_model into ripper_fields for testing.
"""
import sys
import unittest
from datetime import datetime

sys.path.insert(0, '/opt/arm')
from arm.ui.history.filters import (   # noqa: E402
    ALLOWED_STATUSES,
    normalize_status,
    parse_date,
    build_page_args,
)


class TestNormalizeStatus(unittest.TestCase):

    def test_recognised_values_pass_through(self):
        for value in ("all", "success", "fail", "active"):
            self.assertEqual(normalize_status(value), value)

    def test_allowed_statuses_constant(self):
        self.assertEqual(ALLOWED_STATUSES, ("all", "success", "fail", "active"))

    def test_unknown_value_falls_back_to_all(self):
        self.assertEqual(normalize_status("garbage"), "all")

    def test_none_falls_back_to_all(self):
        self.assertEqual(normalize_status(None), "all")

    def test_empty_string_falls_back_to_all(self):
        self.assertEqual(normalize_status(""), "all")


class TestParseDate(unittest.TestCase):

    def test_valid_date(self):
        self.assertEqual(parse_date("2026-01-15"), datetime(2026, 1, 15))

    def test_empty_string_is_none(self):
        self.assertIsNone(parse_date(""))

    def test_none_is_none(self):
        self.assertIsNone(parse_date(None))

    def test_malformed_is_none(self):
        self.assertIsNone(parse_date("not-a-date"))

    def test_wrong_format_is_none(self):
        self.assertIsNone(parse_date("01/15/2026"))


class TestBuildPageArgs(unittest.TestCase):

    def test_empty_when_all_defaults(self):
        self.assertEqual(build_page_args("all", "", ""), {})

    def test_status_included_when_not_all(self):
        self.assertEqual(build_page_args("fail", "", ""), {"status": "fail"})

    def test_dates_included_when_present(self):
        self.assertEqual(
            build_page_args("all", "2026-01-01", "2026-01-31"),
            {"from": "2026-01-01", "to": "2026-01-31"},
        )

    def test_all_three_combined(self):
        self.assertEqual(
            build_page_args("success", "2026-01-01", "2026-01-31"),
            {"status": "success", "from": "2026-01-01", "to": "2026-01-31"},
        )


if __name__ == '__main__':
    unittest.main()
