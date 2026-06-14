from __future__ import annotations

import unittest

from core.diagnostics.errors import ValidationError
from core.formats.timl.embedded_writer import build_embedded_timl_data_payload
from core.formats.timl.reader import read_timl_bytes
from core.formats.timl.reader import read_timl_data_bytes
from tests.test_timl_reader import _build_color_timl_bytes
from tests.test_timl_reader import _build_embedded_timl_source_bytes


class _Keyframe:
    def __init__(self, *, frame: float, value, interpolation: str = "LINEAR"):
        self.frame = float(frame)
        self.value = tuple(float(component) for component in value)
        self.interpolation = interpolation


class _Transform:
    def __init__(
        self,
        *,
        type_index: int,
        transform_index: int,
        timeline_parameter_hash: int,
        datatype_hash: int,
        data_type: int,
        data_type_name: str,
        component_labels,
        keyframes,
    ):
        self.type_index = int(type_index)
        self.transform_index = int(transform_index)
        self.timeline_parameter_hash = int(timeline_parameter_hash)
        self.datatype_hash = int(datatype_hash)
        self.data_type = int(data_type)
        self.data_type_name = str(data_type_name)
        self.component_labels = tuple(component_labels)
        self.keyframes = tuple(keyframes)


class TimlEmbeddedWriterTests(unittest.TestCase):
    def test_embedded_float_payload_roundtrips_through_reader(self):
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        source_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=source_offset,
            source_name="embedded.lmt#timl",
            entry_id=7,
        )
        sampled_transform = _Transform(
            type_index=0,
            transform_index=0,
            timeline_parameter_hash=0x11223344,
            datatype_hash=0x55667788,
            data_type=2,
            data_type_name="float",
            component_labels=("value",),
            keyframes=(
                _Keyframe(frame=12.0, value=(3.5,), interpolation="LINEAR"),
                _Keyframe(frame=24.5, value=(6.25,), interpolation="CONSTANT"),
            ),
        )

        payload, rebase_offsets = build_embedded_timl_data_payload(
            source_entry,
            (sampled_transform,),
            base_offset=source_offset,
        )

        self.assertEqual(rebase_offsets, (0, 48, 80))
        rebuilt_source = (b"\x00" * source_offset) + payload
        rebuilt_entry = read_timl_data_bytes(
            rebuilt_source,
            data_offset=source_offset,
            source_name="rebuilt.lmt#timl",
            entry_id=7,
        )
        self.assertEqual(rebuilt_entry.animation_length, 24.5)
        transform = rebuilt_entry.types[0].transforms[0]
        self.assertEqual(transform.data_type, 2)
        self.assertEqual(len(transform.keyframes), 2)
        self.assertEqual(transform.keyframes[0].value, 3.5)
        self.assertEqual(transform.keyframes[1].value, 6.25)
        self.assertEqual(transform.keyframes[1].frame_timing, 24.5)
        self.assertEqual(transform.keyframes[1].interpolation, 0)

    def test_embedded_color_payload_quantizes_from_preview_range(self):
        timl = read_timl_bytes(_build_color_timl_bytes(), source_name="color.timl")
        source_entry = timl.data_entries[0]
        sampled_transform = _Transform(
            type_index=0,
            transform_index=0,
            timeline_parameter_hash=0xABCD,
            datatype_hash=0xDEAD,
            data_type=3,
            data_type_name="color_rgba8",
            component_labels=("r", "g", "b", "a"),
            keyframes=(
                _Keyframe(frame=8.0, value=(15.6, 32.4, 63.9, 255.0), interpolation="LINEAR"),
            ),
        )

        payload, _rebase_offsets = build_embedded_timl_data_payload(
            source_entry,
            (sampled_transform,),
            base_offset=48,
        )

        rebuilt_source = (b"\x00" * 48) + payload
        rebuilt_entry = read_timl_data_bytes(
            rebuilt_source,
            data_offset=48,
            source_name="rebuilt-color#timl",
            entry_id=0,
        )
        keyframe = rebuilt_entry.types[0].transforms[0].keyframes[0]
        self.assertEqual(keyframe.value, (16, 32, 64, 255))

    def test_embedded_writer_rejects_unsupported_interpolation(self):
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        source_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=source_offset,
            source_name="embedded.lmt#timl",
            entry_id=7,
        )
        sampled_transform = _Transform(
            type_index=0,
            transform_index=0,
            timeline_parameter_hash=0x11223344,
            datatype_hash=0x55667788,
            data_type=2,
            data_type_name="float",
            component_labels=("value",),
            keyframes=(
                _Keyframe(frame=12.0, value=(3.5,), interpolation="BEZIER"),
            ),
        )

        with self.assertRaises(ValidationError):
            build_embedded_timl_data_payload(
                source_entry,
                (sampled_transform,),
                base_offset=source_offset,
            )


if __name__ == "__main__":
    unittest.main()
