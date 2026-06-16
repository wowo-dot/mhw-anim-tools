from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.diagnostics.errors import ValidationError
from core.formats.timl.reader import read_timl_bytes
from core.formats.timl.writer import TimlEntryWriteRequest
from core.formats.timl.writer import write_timl_bytes


def _keyframe(frame: float, value, *, interpolation: str = "LINEAR"):
    return SimpleNamespace(
        frame=float(frame),
        value=tuple(float(component) for component in value),
        interpolation=str(interpolation),
    )


def _transform(
    *,
    type_index: int,
    transform_index: int,
    timeline_parameter_hash: int,
    datatype_hash: int,
    data_type: int,
    data_type_name: str,
    keyframes,
):
    return SimpleNamespace(
        type_index=int(type_index),
        transform_index=int(transform_index),
        timeline_parameter_hash=int(timeline_parameter_hash),
        datatype_hash=int(datatype_hash),
        data_type=int(data_type),
        data_type_name=str(data_type_name),
        keyframes=tuple(keyframes),
    )


class TimlWriterTests(unittest.TestCase):
    def test_writes_standalone_timl_entry_roundtrip(self):
        blob = write_timl_bytes(
            [
                TimlEntryWriteRequest(
                    entry_id=0,
                    sampled_transforms=(
                        _transform(
                            type_index=0,
                            transform_index=0,
                            timeline_parameter_hash=0x11223344,
                            datatype_hash=0x55667788,
                            data_type=2,
                            data_type_name="float",
                            keyframes=(
                                _keyframe(0.0, (1.0,)),
                                _keyframe(20.0, (3.5,)),
                            ),
                        ),
                    ),
                    data_index_a=3,
                    data_index_b=4,
                    animation_length=12.0,
                    loop_start_point=2.0,
                    loop_control=1,
                    label_hash=0xCAFEBABE,
                )
            ]
        )

        timl = read_timl_bytes(blob, source_name="roundtrip.timl")
        self.assertEqual(timl.header.entry_count, 1)
        self.assertEqual(timl.entry_offsets[0] > 0, True)
        entry = timl.data_entries[0]
        self.assertEqual(entry.data_index_a, 3)
        self.assertEqual(entry.data_index_b, 4)
        self.assertEqual(entry.animation_length, 20.0)
        self.assertEqual(entry.loop_start_point, 2.0)
        self.assertEqual(entry.loop_control, 1)
        self.assertEqual(entry.label_hash, 0xCAFEBABE)
        transform = entry.types[0].transforms[0]
        self.assertEqual(transform.data_type, 2)
        self.assertEqual(transform.datatype_hash, 0x55667788)
        self.assertEqual(transform.keyframes[0].value, 1.0)
        self.assertEqual(transform.keyframes[1].value, 3.5)
        self.assertEqual(transform.keyframes[1].frame_timing, 20.0)

    def test_preserves_sparse_entry_ids_and_empty_entries(self):
        blob = write_timl_bytes(
            [
                TimlEntryWriteRequest(
                    entry_id=1,
                    sampled_transforms=(),
                    data_index_a=7,
                    data_index_b=8,
                    animation_length=15.0,
                    loop_start_point=0.0,
                    loop_control=0,
                    label_hash=0x01020304,
                ),
                TimlEntryWriteRequest(
                    entry_id=3,
                    sampled_transforms=(
                        _transform(
                            type_index=0,
                            transform_index=0,
                            timeline_parameter_hash=0x99,
                            datatype_hash=0x77,
                            data_type=1,
                            data_type_name="uint32",
                            keyframes=(
                                _keyframe(0.0, (5.0,)),
                                _keyframe(10.0, (9.0,)),
                            ),
                        ),
                    ),
                ),
            ],
            entry_count=5,
        )

        timl = read_timl_bytes(blob, source_name="sparse.timl")
        self.assertEqual(timl.header.entry_count, 5)
        self.assertEqual(timl.entry_offsets[0], 0)
        self.assertEqual(timl.entry_offsets[2], 0)
        self.assertEqual(timl.entry_offsets[4], 0)
        entries_by_id = {entry.id: entry for entry in timl.data_entries}
        self.assertEqual(entries_by_id[1].type_count, 0)
        self.assertEqual(entries_by_id[1].animation_length, 15.0)
        self.assertEqual(entries_by_id[3].types[0].transforms[0].keyframes[1].value, 9)

    def test_rejects_duplicate_entry_ids(self):
        with self.assertRaises(ValidationError):
            write_timl_bytes(
                [
                    TimlEntryWriteRequest(entry_id=0),
                    TimlEntryWriteRequest(entry_id=0),
                ]
            )


if __name__ == "__main__":
    unittest.main()
