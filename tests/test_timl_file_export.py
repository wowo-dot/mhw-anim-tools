from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from blender_adapter.timl_file_export import analyze_standalone_timl_export
from blender_adapter.timl_file_export import write_standalone_timl_file
from blender_adapter.timl_metadata import TIML_ACTION_NAME_KEY
from blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from blender_adapter.timl_metadata import TIML_ENTRY_ID_KEY
from blender_adapter.timl_metadata import TIML_SESSION_ID_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_ENTRY_COUNT_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_ENTRY_IDS_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_KIND_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_KIND_STANDALONE_FILE
from blender_adapter.timl_metadata import TIML_SOURCE_LMT_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_OFFSET_KEY
from core.formats.timl.reader import read_timl_bytes
from core.formats.timl.writer import TimlEntryWriteRequest
from core.formats.timl.writer import write_timl_bytes


class FakeAnimationData:
    def __init__(self, action):
        self.action = action


class FakeController(dict):
    def __init__(self, name: str, *, action=None, **metadata):
        super().__init__(metadata)
        self.name = name
        self.animation_data = FakeAnimationData(action)


class FakeFCurve:
    def __init__(self, data_path: str, array_index: int, values_by_frame, *, interpolation="LINEAR"):
        self.data_path = data_path
        self.array_index = array_index
        self._values_by_frame = {float(frame): float(value) for frame, value in values_by_frame.items()}
        self.keyframe_points = [
            type(
                "FakeKeyframePoint",
                (),
                {
                    "co": (float(frame), float(value)),
                    "interpolation": interpolation,
                },
            )()
            for frame, value in values_by_frame.items()
        ]

    def evaluate(self, frame: float) -> float:
        return self._values_by_frame[float(frame)]


class FakeAction(dict):
    def __init__(self, name: str, fcurves, **metadata):
        super().__init__(metadata)
        self.name = name
        self.fcurves = list(fcurves)


def _binding(property_name: str, *, type_index: int, transform_index: int, datatype_hash: int = 0x55):
    return {
        "property_name": property_name,
        "type_index": int(type_index),
        "transform_index": int(transform_index),
        "timeline_parameter_hash": 0x11,
        "datatype_hash": int(datatype_hash),
        "data_type": 2,
        "data_type_name": "float",
        "component_labels": ["value"],
        "normalized_color": False,
    }


def _keyframe(frame: float, value: float):
    return SimpleNamespace(
        frame=float(frame),
        value=(float(value),),
        interpolation="LINEAR",
    )


def _source_entry_request(
    entry_id: int,
    *,
    first_value: float,
    second_value: float,
    data_index_a: int,
    data_index_b: int,
    animation_length: float,
    loop_start_point: float,
    loop_control: int,
    label_hash: int,
):
    return TimlEntryWriteRequest(
        entry_id=int(entry_id),
        sampled_transforms=(
            SimpleNamespace(
                type_index=0,
                transform_index=0,
                timeline_parameter_hash=0x11,
                datatype_hash=0x100 + int(entry_id),
                data_type=2,
                data_type_name="float",
                keyframes=(
                    _keyframe(0.0, first_value),
                    _keyframe(6.0, second_value),
                ),
            ),
        ),
        data_index_a=int(data_index_a),
        data_index_b=int(data_index_b),
        animation_length=float(animation_length),
        loop_start_point=float(loop_start_point),
        loop_control=int(loop_control),
        label_hash=int(label_hash),
    )


def _write_source_timl(path: Path, *, entry_requests, entry_count: int):
    path.write_bytes(write_timl_bytes(entry_requests, entry_count=int(entry_count)))


def _standalone_controller(source_path: str, *, entry_id: int, session_id: str, expected_entry_ids, source_entry_count: int):
    action = FakeAction(
        f"TIML::{Path(source_path).stem}::{entry_id:03d}",
        [FakeFCurve(f'["timl_float_{entry_id}"]', 0, {0.0: 1.0 + entry_id, 6.0: 2.0 + entry_id})],
        mhw_anim_tools_import_kind="standalone_timl",
        mhw_anim_tools_timl_transform_count=1,
    )
    return FakeController(
        f"TIML Controller::{Path(source_path).stem}::{entry_id:03d}",
        action=action,
        **{
            TIML_SOURCE_LMT_KEY: source_path,
            TIML_SOURCE_KIND_KEY: TIML_SOURCE_KIND_STANDALONE_FILE,
            TIML_SOURCE_ENTRY_COUNT_KEY: int(source_entry_count),
            TIML_SOURCE_ENTRY_IDS_KEY: json.dumps(list(expected_entry_ids)),
            TIML_ENTRY_ID_KEY: entry_id,
            TIML_SOURCE_OFFSET_KEY: 0x80 + (entry_id * 0x40),
            TIML_SESSION_ID_KEY: session_id,
            TIML_ACTION_NAME_KEY: action.name,
            TIML_BINDINGS_KEY: json.dumps(
                [
                    _binding(
                        f"timl_float_{entry_id}",
                        type_index=0,
                        transform_index=0,
                        datatype_hash=0x100 + entry_id,
                    )
                ]
            ),
            "mhw_anim_tools_timl_header_data_index_a": entry_id,
            "mhw_anim_tools_timl_header_data_index_b": entry_id + 1,
            "mhw_anim_tools_timl_header_animation_length": 6.0,
            "mhw_anim_tools_timl_header_loop_start_point": 0.0,
            "mhw_anim_tools_timl_header_loop_control": 0,
            "mhw_anim_tools_timl_header_label_hash": 0x2200 + entry_id,
        },
    )


class StandaloneTimlExportTests(unittest.TestCase):
    def test_analyze_and_write_full_standalone_timl(self):
        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.timl"
            _write_source_timl(
                source_path,
                entry_requests=(
                    _source_entry_request(
                        0,
                        first_value=10.0,
                        second_value=20.0,
                        data_index_a=30,
                        data_index_b=31,
                        animation_length=6.0,
                        loop_start_point=0.0,
                        loop_control=0,
                        label_hash=0x1000,
                    ),
                    _source_entry_request(
                        1,
                        first_value=40.0,
                        second_value=50.0,
                        data_index_a=32,
                        data_index_b=33,
                        animation_length=6.0,
                        loop_start_point=1.0,
                        loop_control=1,
                        label_hash=0x1001,
                    ),
                ),
                entry_count=2,
            )
            session_id = "session-001"
            expected_entry_ids = (0, 1)
            controller_a = _standalone_controller(
                str(source_path),
                entry_id=0,
                session_id=session_id,
                expected_entry_ids=expected_entry_ids,
                source_entry_count=2,
            )
            controller_b = _standalone_controller(
                str(source_path),
                entry_id=1,
                session_id=session_id,
                expected_entry_ids=expected_entry_ids,
                source_entry_count=2,
            )

            analysis = analyze_standalone_timl_export(
                controller_a,
                controller_objects=(controller_a, controller_b),
            )

            self.assertEqual(analysis.error_count, 0)
            self.assertEqual(analysis.warning_count, 0)
            self.assertEqual(analysis.sampled_entry_count, 2)
            self.assertEqual(analysis.sampled_transform_count, 2)
            self.assertEqual(analysis.source_entry_count, 2)

            output_path = Path(temp_dir) / "roundtrip.timl"
            write_standalone_timl_file(output_path, analysis)
            timl = read_timl_bytes(output_path.read_bytes(), source_name=str(output_path))

        self.assertEqual(timl.header.entry_count, 2)
        self.assertEqual({entry.id for entry in timl.data_entries}, {0, 1})
        self.assertEqual(timl.data_entries[0].data_index_a, 0)
        self.assertEqual(timl.data_entries[1].data_index_a, 1)
        self.assertEqual(timl.data_entries[0].types[0].transforms[0].keyframes[0].value, 1.0)
        self.assertEqual(timl.data_entries[1].types[0].transforms[0].keyframes[1].value, 3.0)

    def test_preserves_unimported_entries_and_empty_slots(self):
        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source_sparse.timl"
            _write_source_timl(
                source_path,
                entry_requests=(
                    _source_entry_request(
                        0,
                        first_value=10.0,
                        second_value=20.0,
                        data_index_a=70,
                        data_index_b=71,
                        animation_length=6.0,
                        loop_start_point=0.0,
                        loop_control=0,
                        label_hash=0x2000,
                    ),
                    _source_entry_request(
                        2,
                        first_value=80.0,
                        second_value=90.0,
                        data_index_a=72,
                        data_index_b=73,
                        animation_length=9.0,
                        loop_start_point=3.0,
                        loop_control=2,
                        label_hash=0x2002,
                    ),
                ),
                entry_count=3,
            )
            controller = _standalone_controller(
                str(source_path),
                entry_id=0,
                session_id="session-002",
                expected_entry_ids=(0, 2),
                source_entry_count=3,
            )

            analysis = analyze_standalone_timl_export(
                controller,
                controller_objects=(controller,),
            )
            self.assertEqual(analysis.error_count, 0)
            self.assertEqual(analysis.sampled_entry_count, 1)
            self.assertEqual(analysis.source_entry_count, 3)

            output_path = Path(temp_dir) / "subset.timl"
            write_standalone_timl_file(output_path, analysis)
            timl = read_timl_bytes(output_path.read_bytes(), source_name=str(output_path))

        self.assertEqual(timl.header.entry_count, 3)
        self.assertEqual(timl.entry_offsets[1], 0)
        entries_by_id = {entry.id: entry for entry in timl.data_entries}
        self.assertEqual(entries_by_id[0].data_index_a, 0)
        self.assertEqual(entries_by_id[0].types[0].transforms[0].keyframes[1].value, 2.0)
        self.assertEqual(entries_by_id[2].data_index_a, 72)
        self.assertEqual(entries_by_id[2].loop_control, 2)
        self.assertEqual(entries_by_id[2].types[0].transforms[0].keyframes[0].value, 80.0)
        self.assertEqual(entries_by_id[2].types[0].transforms[0].keyframes[1].value, 90.0)


if __name__ == "__main__":
    unittest.main()
