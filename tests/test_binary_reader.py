import struct
import unittest

from core.binary.reader import BinaryReader
from core.diagnostics.errors import BinaryFormatError


class BinaryReaderTests(unittest.TestCase):
    def test_struct_reads_advance_only_the_sequential_cursor(self):
        reader = BinaryReader(struct.pack("<IIf", 7, 19, 1.25))
        self.assertEqual(reader.read_struct(struct.Struct("<I")), (7,))
        self.assertEqual(reader.read_struct_at(8, struct.Struct("<f")), (1.25,))
        self.assertEqual(reader.tell(), 4)
        self.assertEqual(reader.read_struct(struct.Struct("<I")), (19,))

    def test_invalid_offsets_and_truncation_do_not_move_cursor(self):
        reader = BinaryReader(b"12345", "test.bin")
        reader.seek(2)
        for offset in (-1, 6, 4, 5):
            with self.subTest(offset=offset), self.assertRaises(BinaryFormatError):
                reader.read_struct_at(offset, struct.Struct("<I"))
            self.assertEqual(reader.tell(), 2)
        with self.assertRaises(BinaryFormatError):
            reader.read_struct(struct.Struct("<I"))
        self.assertEqual(reader.tell(), 2)
        self.assertEqual(reader.read_struct_at(5, struct.Struct("")), ())
