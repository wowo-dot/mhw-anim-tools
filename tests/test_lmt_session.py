import json
import struct
import unittest

from blender_adapter.lmt_session import build_file_summary
from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.semantics import get_buffer_semantics
from core.formats.lmt.semantics import get_usage_semantics
from core.formats.lmt.semantics import raw_key_count


HEADER_STRUCT = struct.Struct("<4shh8s")
ACTION_STRUCT = struct.Struct("<QIIi3i4f4fB2sB5iQ")
TRACK_STRUCT = struct.Struct("<BBBBifiq4fq")


def build_minimal_lmt() -> bytes:
    header = HEADER_STRUCT.pack(b"LMT\x00", 95, 1, b"\x00" * 8)
    entry_offsets = struct.pack("<Q", 32)
    header_padding = b"\x00" * 8
    action = ACTION_STRUCT.pack(
        128,
        1,
        40,
        -1,
        0,
        0,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0,
        b"\x00\x00",
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    track = TRACK_STRUCT.pack(
        0,
        0,
        0,
        205,
        3,
        1.0,
        0,
        0,
        0.0,
        0.0,
        0.0,
        1.0,
        0,
    )
    return header + entry_offsets + header_padding + action + track


class LmtSemanticsTests(unittest.TestCase):
    def test_usage_semantics_for_root_translation(self):
        usage = get_usage_semantics(4)
        self.assertEqual(usage.scope, "root")
        self.assertEqual(usage.transform, "translation")
        self.assertEqual(usage.blender_path_hint, "location")

    def test_buffer_semantics_for_quaternion_lerp(self):
        buffer_info = get_buffer_semantics(14)
        self.assertEqual(buffer_info.code, "q11_lerp")
        self.assertTrue(buffer_info.uses_lerp_basis)
        self.assertEqual(raw_key_count(14, 12), 2)

    def test_unknown_buffer_type_falls_back_cleanly(self):
        buffer_info = get_buffer_semantics(99)
        self.assertEqual(buffer_info.code, "buffer_99")
        self.assertEqual(raw_key_count(99, 32), 0)


class LmtSessionSummaryTests(unittest.TestCase):
    def test_build_file_summary_contains_track_payload(self):
        lmt = read_lmt_bytes(build_minimal_lmt(), source_name="synthetic.lmt")
        summary = build_file_summary(lmt)
        self.assertEqual(len(summary), 1)
        action_summary = summary[0]
        self.assertEqual(action_summary["entry_id"], 0)
        self.assertIn("track_payload", action_summary)
        track_payload = json.loads(action_summary["track_payload"])
        self.assertEqual(len(track_payload), 1)
        self.assertEqual(track_payload[0]["bone_id"], 3)
        self.assertEqual(track_payload[0]["usage_label"], "Bone Local Rotation")
        self.assertEqual(track_payload[0]["buffer_code"], "buffer_0")


if __name__ == "__main__":
    unittest.main()
