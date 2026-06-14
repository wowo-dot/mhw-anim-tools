from __future__ import annotations

from dataclasses import replace
import unittest

from core.formats.timl.reader import read_timl_bytes
from core.formats.timl.validation import validate_timl
from tests.test_timl_reader import _build_minimal_timl_bytes


class TimlValidationTests(unittest.TestCase):
    def test_validate_minimal_timl(self):
        timl = read_timl_bytes(_build_minimal_timl_bytes(), source_name="minimal.timl")
        report = validate_timl(timl)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)

    def test_validate_entry_offset_outside_file(self):
        timl = read_timl_bytes(_build_minimal_timl_bytes(), source_name="minimal.timl")
        broken = replace(timl, entry_offsets=(timl.file_size + 64,))
        report = validate_timl(broken)
        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.diagnostics[0].code, "timl.data_offset")
