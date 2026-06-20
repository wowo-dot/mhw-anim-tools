from __future__ import annotations

import unittest

from core.diagnostics.errors import ValidationError
from core.formats.timl.embedded_writer import build_embedded_timl_data_payload
from core.formats.timl.embedded_writer import build_embedded_timl_data_payload_from_sampled
from core.formats.timl.reader import UNSIGNED_KEYFRAME_STRUCT
from core.formats.timl.reader import read_timl_bytes
from core.formats.timl.reader import read_timl_data_bytes
from tests.test_timl_reader import DATA_STRUCT
from tests.test_timl_reader import FLOAT_KEYFRAME_STRUCT
from tests.test_timl_reader import _build_color_timl_bytes
from tests.test_timl_reader import _build_embedded_timl_source_bytes
from tests.test_timl_reader import TRANSFORM_STRUCT
from tests.test_timl_reader import TYPE_STRUCT


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
        source_type_index: int | None = None,
        source_transform_index: int | None = None,
    ):
        self.type_index = int(type_index)
        self.transform_index = int(transform_index)
        self.timeline_parameter_hash = int(timeline_parameter_hash)
        self.datatype_hash = int(datatype_hash)
        self.data_type = int(data_type)
        self.data_type_name = str(data_type_name)
        self.component_labels = tuple(component_labels)
        self.keyframes = tuple(keyframes)
        self.source_type_index = None if source_type_index is None else int(source_type_index)
        self.source_transform_index = None if source_transform_index is None else int(source_transform_index)


def _build_multi_transform_embedded_source_bytes() -> tuple[bytes, int]:
    timl_offset = 224
    data_rel = 0
    type_rel = DATA_STRUCT.size
    transform_rel = 80
    transform0_keyframe_rel = 128
    transform1_keyframe_rel = transform0_keyframe_rel + FLOAT_KEYFRAME_STRUCT.size
    payload_size = transform1_keyframe_rel + UNSIGNED_KEYFRAME_STRUCT.size
    payload = bytearray(payload_size)
    DATA_STRUCT.pack_into(payload, data_rel, timl_offset + type_rel, 1, 0, 0, 10.0, 0.0, 0, 0x01020304)
    TYPE_STRUCT.pack_into(payload, type_rel, timl_offset + transform_rel, 2, 0x11223344, 0)
    TRANSFORM_STRUCT.pack_into(payload, transform_rel + (0 * TRANSFORM_STRUCT.size), timl_offset + transform0_keyframe_rel, 1, 0xAAAABBBB, 2)
    TRANSFORM_STRUCT.pack_into(payload, transform_rel + (1 * TRANSFORM_STRUCT.size), timl_offset + transform1_keyframe_rel, 1, 0xCCCCDDDD, 1)
    FLOAT_KEYFRAME_STRUCT.pack_into(payload, transform0_keyframe_rel, 1.5, 0.25, 0.75, 5.0, 3, 4)
    UNSIGNED_KEYFRAME_STRUCT.pack_into(payload, transform1_keyframe_rel, 7, 0, 0, 10.0, 1, 0)
    return (b"\x00" * timl_offset) + bytes(payload), timl_offset


class TimlEmbeddedWriterTests(unittest.TestCase):
    def test_embedded_writer_can_build_empty_payload_from_zero_sampled_transforms(self):
        payload, rebase_offsets = build_embedded_timl_data_payload_from_sampled(
            (),
            base_offset=0x4000000000000000,
            data_index_a=3,
            data_index_b=4,
            animation_length=12.5,
            loop_start_point=1.0,
            loop_control=2,
            label_hash=0x12345678,
        )

        rebuilt_source = (b"\x00" * 48) + payload
        rebuilt_entry = read_timl_data_bytes(
            rebuilt_source,
            data_offset=48,
            source_name="empty-added#timl",
            entry_id=0,
        )

        self.assertEqual(rebase_offsets, ())
        self.assertEqual(rebuilt_entry.type_count, 0)
        self.assertEqual(len(rebuilt_entry.types), 0)
        self.assertEqual(rebuilt_entry.data_index_a, 3)
        self.assertEqual(rebuilt_entry.data_index_b, 4)
        self.assertEqual(rebuilt_entry.animation_length, 12.5)
        self.assertEqual(rebuilt_entry.loop_start_point, 1.0)
        self.assertEqual(rebuilt_entry.loop_control, 2)
        self.assertEqual(rebuilt_entry.label_hash, 0x12345678)

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

    def test_embedded_writer_preserves_missing_source_transforms_exactly(self):
        source_bytes, source_offset = _build_multi_transform_embedded_source_bytes()
        source_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=source_offset,
            source_name="multi-source#timl",
            entry_id=0,
        )
        sampled_transform = _Transform(
            type_index=0,
            transform_index=1,
            timeline_parameter_hash=0x11223344,
            datatype_hash=0xCCCCDDDD,
            data_type=1,
            data_type_name="uint32",
            component_labels=("value",),
            keyframes=(
                _Keyframe(frame=10.0, value=(9.0,), interpolation="LINEAR"),
            ),
        )

        payload, _rebase_offsets = build_embedded_timl_data_payload(
            source_entry,
            (sampled_transform,),
            base_offset=source_offset,
        )

        rebuilt_source = (b"\x00" * source_offset) + payload
        rebuilt_entry = read_timl_data_bytes(
            rebuilt_source,
            data_offset=source_offset,
            source_name="multi-rebuilt#timl",
            entry_id=0,
        )
        preserved = rebuilt_entry.types[0].transforms[0].keyframes[0]
        changed = rebuilt_entry.types[0].transforms[1].keyframes[0]
        self.assertEqual(preserved.value, 1.5)
        self.assertEqual(preserved.control_left, 0.25)
        self.assertEqual(preserved.control_right, 0.75)
        self.assertEqual(preserved.interpolation, 3)
        self.assertEqual(preserved.easing, 4)
        self.assertEqual(changed.value, 9)

    def test_embedded_writer_preserves_advanced_source_semantics_for_value_only_edit(self):
        source_bytes, source_offset = _build_multi_transform_embedded_source_bytes()
        source_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=source_offset,
            source_name="advanced-source#timl",
            entry_id=0,
        )
        sampled_transform = _Transform(
            type_index=0,
            transform_index=0,
            timeline_parameter_hash=0x11223344,
            datatype_hash=0xAAAABBBB,
            data_type=2,
            data_type_name="float",
            component_labels=("value",),
            keyframes=(
                _Keyframe(frame=5.0, value=(9.5,), interpolation="LINEAR"),
            ),
        )

        payload, _rebase_offsets = build_embedded_timl_data_payload(
            source_entry,
            (sampled_transform,),
            base_offset=source_offset,
        )

        rebuilt_source = (b"\x00" * source_offset) + payload
        rebuilt_entry = read_timl_data_bytes(
            rebuilt_source,
            data_offset=source_offset,
            source_name="advanced-rebuilt#timl",
            entry_id=0,
        )
        keyframe = rebuilt_entry.types[0].transforms[0].keyframes[0]
        self.assertEqual(keyframe.value, 9.5)
        self.assertEqual(keyframe.control_left, 0.25)
        self.assertEqual(keyframe.control_right, 0.75)
        self.assertEqual(keyframe.frame_timing, 5.0)
        self.assertEqual(keyframe.interpolation, 3)
        self.assertEqual(keyframe.easing, 4)

    def test_embedded_writer_rejects_timeline_hash_change(self):
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
            timeline_parameter_hash=0x99887766,
            datatype_hash=0x55667788,
            data_type=2,
            data_type_name="float",
            component_labels=("value",),
            keyframes=(
                _Keyframe(frame=12.0, value=(3.5,), interpolation="LINEAR"),
            ),
        )

        with self.assertRaises(ValidationError):
            build_embedded_timl_data_payload(
                source_entry,
                (sampled_transform,),
                base_offset=source_offset,
            )

    def test_embedded_writer_can_move_source_transforms_by_preserved_origin_identity(self):
        source_bytes, source_offset = _build_multi_transform_embedded_source_bytes()
        source_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=source_offset,
            source_name="moved-source#timl",
            entry_id=0,
        )
        moved_uint = _Transform(
            type_index=0,
            transform_index=0,
            source_type_index=0,
            source_transform_index=1,
            timeline_parameter_hash=0x11223344,
            datatype_hash=0xCCCCDDDD,
            data_type=1,
            data_type_name="uint32",
            component_labels=("value",),
            keyframes=(
                _Keyframe(frame=10.0, value=(7.0,), interpolation="LINEAR"),
            ),
        )
        moved_float = _Transform(
            type_index=0,
            transform_index=1,
            source_type_index=0,
            source_transform_index=0,
            timeline_parameter_hash=0x11223344,
            datatype_hash=0xAAAABBBB,
            data_type=2,
            data_type_name="float",
            component_labels=("value",),
            keyframes=(
                _Keyframe(frame=5.0, value=(1.5,), interpolation="LINEAR"),
            ),
        )

        payload, _rebase_offsets = build_embedded_timl_data_payload(
            source_entry,
            (moved_uint, moved_float),
            base_offset=source_offset,
        )

        rebuilt_source = (b"\x00" * source_offset) + payload
        rebuilt_entry = read_timl_data_bytes(
            rebuilt_source,
            data_offset=source_offset,
            source_name="moved-rebuilt#timl",
            entry_id=0,
        )
        first_transform = rebuilt_entry.types[0].transforms[0]
        second_transform = rebuilt_entry.types[0].transforms[1]
        self.assertEqual(first_transform.data_type, 1)
        self.assertEqual(first_transform.keyframes[0].value, 7)
        self.assertEqual(second_transform.data_type, 2)
        self.assertEqual(second_transform.keyframes[0].value, 1.5)
        self.assertEqual(second_transform.keyframes[0].control_left, 0.25)
        self.assertEqual(second_transform.keyframes[0].control_right, 0.75)


if __name__ == "__main__":
    unittest.main()
