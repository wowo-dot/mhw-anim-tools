from __future__ import annotations

import struct
import unittest

from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.validation import validate_lmt


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


class LmtReaderTests(unittest.TestCase):
    def test_parse_minimal_lmt(self):
        lmt = read_lmt_bytes(build_minimal_lmt(), source_name="synthetic.lmt")
        self.assertEqual(lmt.header.entry_count, 1)
        self.assertEqual(lmt.action_count, 1)
        self.assertEqual(lmt.track_count, 1)
        self.assertEqual(lmt.actions[0].header.frame_count, 40)
        self.assertEqual(lmt.actions[0].tracks[0].header.bone_id, 3)

    def test_validate_minimal_lmt(self):
        lmt = read_lmt_bytes(build_minimal_lmt(), source_name="synthetic.lmt")
        report = validate_lmt(lmt)
        self.assertEqual(report.error_count, 0)


if __name__ == "__main__":
    unittest.main()
