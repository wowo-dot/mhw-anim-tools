from __future__ import annotations

import unittest
import struct

from core.formats.lmt.export_context import assess_standalone_export_context
from core.formats.lmt.export_context import build_source_action_export_context
from core.formats.lmt.export_context import extract_raw_timl_payloads
from core.formats.lmt.model import LmtAction
from core.formats.lmt.model import LmtActionHeader
from core.formats.lmt.model import LmtFile
from core.formats.lmt.model import LmtHeader
from core.formats.lmt.model import LmtTrack
from core.formats.lmt.model import LmtTrackHeader


TIML_DATA_STRUCT = struct.Struct("<QQiiffiI")
TIML_TYPE_STRUCT = struct.Struct("<QQIi")
TIML_TRANSFORM_STRUCT = struct.Struct("<QQIi")


def _track(
    *,
    bone_id: int = 3,
    usage: int = 1,
    buffer_type: int = 3,
) -> LmtTrack:
    return LmtTrack(
        header=LmtTrackHeader(
            buffer_type=buffer_type,
            usage=usage,
            joint_type=0,
            unknown_tag=205,
            bone_id=bone_id,
            weight=1.0,
            buffer_size=0,
            buffer_offset=0,
            basis=(0.0, 0.0, 0.0, 0.0),
            lerp_offset=0,
        ),
        raw_buffer=b"",
        lerp_basis=None,
    )


def _action(
    *,
    action_id: int,
    timl_offset: int = 0,
    tracks: tuple[LmtTrack, ...] = (),
) -> LmtAction:
    return LmtAction(
        header=LmtActionHeader(
            id=action_id,
            fcurve_offset=0,
            fcurve_count=len(tracks),
            frame_count=40,
            loop_frame=-1,
            null0=(0, 0, 0),
            translation=(0.0, 0.0, 0.0, 0.0),
            rotation_lerp=(0.0, 0.0, 0.0, 1.0),
            flags=7,
            null2=b"\x00\x00",
            flags2=9,
            null3=(0, 0, 0, 0, 0),
            timl_offset=timl_offset,
        ),
        tracks=tracks,
    )


class LmtExportContextTests(unittest.TestCase):
    def test_build_source_action_export_context_preserves_metadata(self):
        lmt = LmtFile(
            source_name="sample.lmt",
            file_size=256,
            header=LmtHeader(signature=b"LMT\x00", version=88, entry_count=1, unknown=b"ABCDEFGH"),
            entry_offsets=(32,),
            actions=(
                _action(
                    action_id=5,
                    tracks=(
                        _track(bone_id=3, usage=1, buffer_type=5),
                    ),
                ),
            ),
        )

        context = build_source_action_export_context(lmt, 5)

        self.assertEqual(context.source_name, "sample.lmt")
        self.assertEqual(context.version, 88)
        self.assertEqual(context.header_unknown, b"ABCDEFGH")
        self.assertEqual(context.action_id, 5)
        self.assertEqual(context.flags, 7)
        self.assertEqual(context.flags2, 9)
        self.assertFalse(context.has_timl)
        self.assertIn((3, 1), context.track_metadata_by_identity)
        self.assertEqual(context.track_metadata_by_identity[(3, 1)]["buffer_type"], 5)

    def test_assess_standalone_export_context_warns_without_source_context(self):
        report = assess_standalone_export_context(None)

        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.standalone")

    def test_assess_standalone_export_context_blocks_timl_and_multi_action_sources(self):
        lmt = LmtFile(
            source_name="multi.lmt",
            file_size=512,
            header=LmtHeader(signature=b"LMT\x00", version=95, entry_count=2, unknown=b"\x00" * 8),
            entry_offsets=(32, 128),
            actions=(
                _action(action_id=0, timl_offset=256, tracks=(_track(bone_id=0, usage=0, buffer_type=7),)),
                _action(action_id=1, tracks=(_track(bone_id=1, usage=1, buffer_type=3),)),
            ),
        )

        context = build_source_action_export_context(lmt, 0)
        report = assess_standalone_export_context(context)

        self.assertEqual(report.error_count, 2)
        self.assertEqual({item.code for item in report.diagnostics}, {"lmt.export.timl", "lmt.export.container"})

    def test_extract_raw_timl_payloads_preserves_unique_offset_payloads(self):
        timl_offset = 32
        timl_payload = bytearray(144)
        struct.pack_into(
            TIML_DATA_STRUCT.format,
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
        struct.pack_into(TIML_TYPE_STRUCT.format, timl_payload, 48, timl_offset + 80, 1, 1234, 0)
        struct.pack_into(TIML_TRANSFORM_STRUCT.format, timl_payload, 80, timl_offset + 112, 1, 5678, 2)
        struct.pack_into("<ffffhh", timl_payload, 112, 1.0, 0.0, 0.0, 0.0, 0, 2)
        source_bytes = (b"\x00" * 32) + bytes(timl_payload) + (b"\x00" * 8)
        lmt = LmtFile(
            source_name="timl-source.lmt",
            file_size=len(source_bytes),
            header=LmtHeader(signature=b"LMT\x00", version=95, entry_count=2, unknown=b"\x00" * 8),
            entry_offsets=(32, 128),
            actions=(
                _action(action_id=0, timl_offset=32),
                _action(action_id=1, timl_offset=32),
            ),
        )

        payloads = extract_raw_timl_payloads(lmt, source_bytes)

        self.assertEqual(payloads, {32: bytes(timl_payload)})


if __name__ == "__main__":
    unittest.main()
