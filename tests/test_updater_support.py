from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from core.updater_support import find_addon_root
from core.updater_support import is_version_newer
from core.updater_support import parse_version_text
from core.updater_support import should_check_for_updates


class UpdaterSupportTests(unittest.TestCase):
    def test_parse_version_text_accepts_plain_and_v_prefixed_tags(self):
        self.assertEqual(parse_version_text("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version_text("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version_text("V2.4"), (2, 4, 0))

    def test_parse_version_text_rejects_non_numeric_tags(self):
        self.assertIsNone(parse_version_text("main"))
        self.assertIsNone(parse_version_text(""))

    def test_is_version_newer_compares_normalized_tuples(self):
        self.assertTrue(is_version_newer((1, 2, 0), (1, 1, 9)))
        self.assertFalse(is_version_newer((1, 0, 0), (1, 0, 0)))
        self.assertFalse(is_version_newer(None, (1, 0, 0)))

    def test_should_check_for_updates_respects_interval(self):
        now = datetime.fromisoformat("2026-06-16T12:00:00+03:00")
        self.assertFalse(
            should_check_for_updates(
                "2026-06-16T11:30:00+03:00",
                auto_check_enabled=True,
                hours=1,
                now=now,
            )
        )
        self.assertTrue(
            should_check_for_updates(
                "2026-06-15T11:30:00+03:00",
                auto_check_enabled=True,
                hours=1,
                now=now,
            )
        )
        self.assertFalse(
            should_check_for_updates(
                "2026-06-15T11:30:00+03:00",
                auto_check_enabled=False,
                hours=1,
                now=now,
            )
        )

    def test_find_addon_root_locates_directory_with_bl_info(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "payload" / "mhw_anim_tools"
            root.mkdir(parents=True)
            (root / "__init__.py").write_text("bl_info = {'name': 'Test'}\n", encoding="utf-8")
            found = find_addon_root(Path(tmpdir))
        self.assertEqual(found, root)
