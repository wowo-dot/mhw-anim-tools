from __future__ import annotations

import struct
import unittest

from core.formats.lmt.export_context import RawTimlPayload
from core.formats.lmt.decoder import decode_action_tracks
from core.formats.lmt.export_context import extract_raw_timl_payload_layouts
from core.formats.lmt.merge_writer import write_merged_lmt_bytes
from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.reconstructed import LmtReconstructedAction
from core.formats.lmt.reconstructed import LmtReconstructedKeyframe
from core.formats.lmt.reconstructed import LmtReconstructedTrack
from core.formats.timl.embedded_writer import build_embedded_timl_data_payload
from core.formats.timl.reader import read_timl_data_bytes


HEADER_STRUCT = struct.Struct("<4shh8s")
ENTRY_OFFSET_STRUCT = struct.Struct("<Q")
ACTION_STRUCT = struct.Struct("<QIIi3i4f4fB2sB5iQ")
TIML_DATA_STRUCT = struct.Struct("<QQiiffiI")
TIML_TYPE_STRUCT = struct.Struct("<QQIi")
TIML_TRANSFORM_STRUCT = struct.Struct("<QQIi")


def _build_source_container_with_shared_timl() -> tuple[bytes, bytes]:
    timl_offset = 224
    timl_payload = bytearray(144)
    TIML_DATA_STRUCT.pack_into(
        timl_payload,
        0,
        timl_offset + 48,
        1,
        0,
        0,
        10.0,
        0.0,
        0,
        0,
    )
    TIML_TYPE_STRUCT.pack_into(timl_payload, 48, timl_offset + 80, 1, 1234, 0)
    TIML_TRANSFORM_STRUCT.pack_into(timl_payload, 80, timl_offset + 112, 1, 5678, 2)
    struct.pack_into("<ffffhh", timl_payload, 112, 1.0, 0.0, 0.0, 0.0, 0, 2)
    entry_count = 2
    header = HEADER_STRUCT.pack(b"LMT\x00", 95, entry_count, b"ABCDEFGH")
    entry_table = ENTRY_OFFSET_STRUCT.pack(32) + ENTRY_OFFSET_STRUCT.pack(128)
    action0 = ACTION_STRUCT.pack(
        0,
        0,
        10,
        7,
        1,
        2,
        3,
        11.0,
        12.0,
        13.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        9,
        b"\xAA\xBB",
        4,
        5,
        6,
        7,
        8,
        9,
        timl_offset,
    )
    action1 = ACTION_STRUCT.pack(
        0,
        0,
        20,
        -1,
        0,
        0,
        0,
        21.0,
        22.0,
        23.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        17,
        b"\x00\x00",
        2,
        1,
        1,
        1,
        1,
        1,
        timl_offset,
    )
    return (
        header
        + entry_table
        + action0
        + action1
        + bytes(timl_payload),
        bytes(timl_payload),
    )


class LmtMergeWriterTests(unittest.TestCase):
    def test_merge_writer_preserves_siblings_and_shared_raw_timl(self):
        source_bytes, timl_payload = _build_source_container_with_shared_timl()
        source_lmt = read_lmt_bytes(source_bytes, source_name="merge-source.lmt")
        reconstructed = LmtReconstructedAction(
            action_name="EditedAction",
            frame_start=0,
            frame_end=6,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(0.5, 1.0, 1.5),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=1, value=(1.25, 2.5, -3.75)),
                        LmtReconstructedKeyframe(frame=6, value=(4.0, 5.0, 6.0)),
                    ),
                ),
            ),
        )

        merged_bytes = write_merged_lmt_bytes(
            source_lmt,
            source_bytes,
            reconstructed,
            action_id=0,
        )
        merged_lmt = read_lmt_bytes(merged_bytes, source_name="merge-output.lmt")
        decoded = decode_action_tracks(merged_lmt.actions[0], strict=True)

        self.assertEqual(merged_lmt.header.version, 95)
        self.assertEqual(merged_lmt.header.unknown, b"ABCDEFGH")
        self.assertEqual(merged_lmt.header.entry_count, 2)
        self.assertEqual(tuple(action.id for action in merged_lmt.actions), (0, 1))

        self.assertEqual(merged_lmt.actions[0].header.loop_frame, 7)
        self.assertEqual(merged_lmt.actions[0].header.flags, 9)
        self.assertEqual(merged_lmt.actions[0].header.null2, b"\xAA\xBB")
        self.assertEqual(merged_lmt.actions[0].header.null3, (5, 6, 7, 8, 9))
        self.assertEqual(len(merged_lmt.actions[0].tracks), 1)
        self.assertEqual([sample.frame for sample in decoded.tracks[0].keyframes], [1, 6])
        self.assertEqual(len(merged_lmt.actions[1].tracks), 0)
        self.assertEqual(merged_lmt.actions[1].header.flags, 17)

        self.assertNotEqual(merged_lmt.actions[0].header.timl_offset, 0)
        self.assertEqual(merged_lmt.actions[0].header.timl_offset, merged_lmt.actions[1].header.timl_offset)
        timl_offset = merged_lmt.actions[0].header.timl_offset
        layouts = extract_raw_timl_payload_layouts(merged_lmt, merged_bytes)
        self.assertEqual(len(layouts), 1)
        self.assertEqual(len(layouts[timl_offset].payload), len(timl_payload))
        (type_offset,) = struct.unpack_from("<Q", merged_bytes, timl_offset)
        (transform_offset,) = struct.unpack_from("<Q", merged_bytes, timl_offset + 48)
        (keyframe_offset,) = struct.unpack_from("<Q", merged_bytes, timl_offset + 80)
        self.assertEqual(type_offset, timl_offset + 48)
        self.assertEqual(transform_offset, timl_offset + 80)
        self.assertEqual(keyframe_offset, timl_offset + 112)
        self.assertEqual(
            merged_bytes[timl_offset + 112 : timl_offset + len(timl_payload)],
            timl_payload[112:],
        )

    def test_merge_writer_can_replace_shared_timl_payload(self):
        source_bytes, timl_payload = _build_source_container_with_shared_timl()
        source_lmt = read_lmt_bytes(source_bytes, source_name="merge-source.lmt")
        source_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=224,
            source_name="merge-source.lmt#timl",
            entry_id=0,
        )
        sampled_transform = type(
            "SampledTimlTransform",
            (),
            {
                "type_index": 0,
                "transform_index": 0,
                "timeline_parameter_hash": 1234,
                "datatype_hash": 5678,
                "data_type": 2,
                "data_type_name": "float",
                "component_labels": ("value",),
                "keyframes": (
                    type("SampledTimlKeyframe", (), {"frame": 0.0, "value": (9.0,), "interpolation": "LINEAR"})(),
                ),
            },
        )()
        replacement_payload, replacement_rebase_offsets = build_embedded_timl_data_payload(
            source_entry,
            (sampled_transform,),
            base_offset=224,
        )
        reconstructed = LmtReconstructedAction(
            action_name="EditedAction",
            frame_start=0,
            frame_end=6,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(0.5, 1.0, 1.5),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=1, value=(1.25, 2.5, -3.75)),
                    ),
                ),
            ),
        )

        merged_bytes = write_merged_lmt_bytes(
            source_lmt,
            source_bytes,
            reconstructed,
            action_id=0,
            replacement_timl_payloads={
                224: RawTimlPayload(payload=replacement_payload, rebase_offsets=replacement_rebase_offsets),
            },
        )
        merged_lmt = read_lmt_bytes(merged_bytes, source_name="merge-output.lmt")

        self.assertEqual(merged_lmt.actions[0].header.timl_offset, merged_lmt.actions[1].header.timl_offset)
        merged_timl_offset = merged_lmt.actions[0].header.timl_offset
        merged_entry = read_timl_data_bytes(
            merged_bytes,
            data_offset=merged_timl_offset,
            source_name="merge-output.lmt#timl",
            entry_id=0,
        )
        self.assertEqual(merged_entry.types[0].transforms[0].keyframes[0].value, 9.0)
        layouts = extract_raw_timl_payload_layouts(merged_lmt, merged_bytes)
        self.assertEqual(len(layouts), 1)
        self.assertNotEqual(layouts[merged_timl_offset].payload, timl_payload)
        (type_offset,) = struct.unpack_from("<Q", merged_bytes, merged_timl_offset)
        self.assertEqual(type_offset, merged_timl_offset + 48)


if __name__ == "__main__":
    unittest.main()
