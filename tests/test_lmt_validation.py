from __future__ import annotations

import struct
import unittest

from core.diagnostics.errors import BinaryFormatError
from core.formats.lmt.reader import read_lmt_bytes


HEADER_STRUCT = struct.Struct("<4shh8s")


class LmtValidationTests(unittest.TestCase):
    def test_invalid_signature_raises(self):
        data = HEADER_STRUCT.pack(b"BAD\x00", 95, 0, b"\x00" * 8)
        with self.assertRaises(BinaryFormatError):
            read_lmt_bytes(data, source_name="bad.lmt")


if __name__ == "__main__":
    unittest.main()
