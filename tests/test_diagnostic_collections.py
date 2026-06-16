from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.diagnostics.collections import has_text_diagnostic


class DiagnosticCollectionsTests(unittest.TestCase):
    def test_has_text_diagnostic_matches_exact_duplicate(self):
        items = [
            SimpleNamespace(
                level="WARNING",
                source="timl.block",
                message="Preview bindings are missing.",
            )
        ]

        self.assertTrue(
            has_text_diagnostic(
                items,
                level="WARNING",
                source="timl.block",
                message="Preview bindings are missing.",
            )
        )

    def test_has_text_diagnostic_keeps_distinct_messages(self):
        items = [
            SimpleNamespace(
                level="WARNING",
                source="timl.block",
                message="Preview bindings are missing.",
            )
        ]

        self.assertFalse(
            has_text_diagnostic(
                items,
                level="WARNING",
                source="timl.block",
                message="Preview curves were rebuilt.",
            )
        )

    def test_has_text_diagnostic_ignores_items_missing_fields(self):
        items = [SimpleNamespace(code="timl.block")]

        self.assertFalse(
            has_text_diagnostic(
                items,
                level="WARNING",
                source="timl.block",
                message="Preview bindings are missing.",
            )
        )


if __name__ == "__main__":
    unittest.main()
