from __future__ import annotations

import unittest

from core.formats.lmt.reader import read_lmt_bytes

from test_lmt_reader import build_minimal_lmt


class RegressionHarnessTests(unittest.TestCase):
    def test_summary_counts_are_stable_for_synthetic_fixture(self):
        lmt = read_lmt_bytes(build_minimal_lmt(), source_name="synthetic.lmt")
        summary = {
            "entries": lmt.header.entry_count,
            "actions": lmt.action_count,
            "tracks": lmt.track_count,
            "has_timl": [action.has_timl for action in lmt.actions],
        }
        self.assertEqual(
            summary,
            {
                "entries": 1,
                "actions": 1,
                "tracks": 1,
                "has_timl": [False],
            },
        )


if __name__ == "__main__":
    unittest.main()
