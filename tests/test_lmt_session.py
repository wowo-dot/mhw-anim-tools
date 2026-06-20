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
TIML_DATA_STRUCT = struct.Struct("<QQiiffiI")
TIML_TYPE_STRUCT = struct.Struct("<QQIi")
TIML_TRANSFORM_STRUCT = struct.Struct("<QQIi")


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


def build_lmt_with_embedded_timl() -> bytes:
    timl_offset = 176
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
        timl_offset,
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
    payload = bytearray(144)
    TIML_DATA_STRUCT.pack_into(payload, 0, timl_offset + 48, 1, 0, 0, 10.0, 2.0, 3, 0x87654321)
    TIML_TYPE_STRUCT.pack_into(payload, 48, timl_offset + 80, 1, 0x000004D2, 0)
    TIML_TRANSFORM_STRUCT.pack_into(payload, 80, timl_offset + 112, 1, 0x0000162E, 2)
    struct.pack_into("<ffffhh", payload, 112, 3.5, 0.0, 0.0, 12.0, 1, 2)
    return header + entry_offsets + header_padding + action + track + bytes(payload)


def build_lmt_with_hole() -> bytes:
    header = HEADER_STRUCT.pack(b"LMT\x00", 95, 3, b"\x00" * 8)
    action0_offset = 48
    action = ACTION_STRUCT.pack(
        0,
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
    track0 = TRACK_STRUCT.pack(
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
    action1_offset = action0_offset + len(action) + len(track0)
    entry_offsets = struct.pack("<QQQ", action0_offset, 0, action1_offset)
    padding = b"\x00" * (action0_offset - (len(header) + len(entry_offsets)))
    track1 = TRACK_STRUCT.pack(
        0,
        1,
        0,
        205,
        4,
        1.0,
        0,
        0,
        0.0,
        0.0,
        0.0,
        1.0,
        0,
    )
    return header + entry_offsets + padding + action + track0 + action + track1


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

    def test_build_file_summary_contains_attached_timl_summary(self):
        source_bytes = build_lmt_with_embedded_timl()
        lmt = read_lmt_bytes(source_bytes, source_name="synthetic_timl.lmt")
        summary = build_file_summary(lmt, source_bytes=source_bytes)
        action_summary = summary[0]
        self.assertTrue(action_summary["has_timl"])
        self.assertEqual(action_summary["timl_source_offset"], 176)
        self.assertEqual(action_summary["timl_type_count"], 1)
        self.assertEqual(action_summary["timl_transform_count"], 1)
        self.assertEqual(action_summary["timl_keyframe_count"], 1)
        self.assertEqual(action_summary["timl_animation_length"], 10.0)
        self.assertEqual(action_summary["timl_loop_start_point"], 2.0)
        self.assertEqual(action_summary["timl_loop_control"], 3)
        self.assertEqual(action_summary["timl_data_type_breakdown"], "1 float")
        timl_transforms = json.loads(action_summary["timl_transform_payload"])
        self.assertEqual(len(timl_transforms), 1)
        self.assertEqual(timl_transforms[0]["data_type_name"], "float")
        self.assertEqual(timl_transforms[0]["timeline_parameter_label"], "0x000004D2")
        self.assertEqual(timl_transforms[0]["datatype_label"], "0x0000162E")
        self.assertEqual(action_summary["timl_parse_error"], "")

    def test_build_file_summary_surfaces_source_holes_as_empty_slots(self):
        source_bytes = build_lmt_with_hole()
        lmt = read_lmt_bytes(source_bytes, source_name="synthetic_hole.lmt")

        summary = build_file_summary(lmt)

        self.assertEqual(len(summary), 3)
        self.assertEqual(summary[0]["entry_state"], "source")
        self.assertEqual(summary[1]["entry_id"], 1)
        self.assertEqual(summary[1]["entry_state"], "source_hole")
        self.assertFalse(summary[1]["has_source_action"])
        self.assertEqual(summary[1]["track_count"], 0)
        self.assertEqual(summary[2]["entry_id"], 2)
        self.assertEqual(summary[2]["entry_state"], "source")


if __name__ == "__main__":
    unittest.main()
