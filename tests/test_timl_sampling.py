from __future__ import annotations

import json
import unittest

from blender_adapter.timl_metadata import TIML_ACTION_NAME_KEY
from blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from blender_adapter.timl_metadata import TIML_ENTRY_ID_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_LMT_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_OFFSET_KEY
from blender_adapter.timl_sampling import is_imported_timl_controller
from blender_adapter.timl_sampling import sample_timl_controller_action


class FakeAnimationData:
    def __init__(self, action):
        self.action = action


class FakeController(dict):
    def __init__(self, name: str, *, action=None, **metadata):
        super().__init__(metadata)
        self.name = name
        self.animation_data = FakeAnimationData(action)


class FakeFCurve:
    def __init__(self, data_path: str, array_index: int, values_by_frame, *, authored_frames=None, interpolation="LINEAR"):
        self.data_path = data_path
        self.array_index = array_index
        self._values_by_frame = {float(frame): float(value) for frame, value in values_by_frame.items()}
        authored = tuple(values_by_frame.keys()) if authored_frames is None else tuple(authored_frames)
        self.keyframe_points = [
            type(
                "FakeKeyframePoint",
                (),
                {
                    "co": (float(frame), float(self._values_by_frame.get(float(frame), 0.0))),
                    "interpolation": interpolation,
                },
            )()
            for frame in authored
        ]

    def evaluate(self, frame: float) -> float:
        return self._values_by_frame.get(float(frame), 0.0)


class FakeAction(dict):
    def __init__(self, name: str, fcurves, **metadata):
        super().__init__(metadata)
        self.name = name
        self.fcurves = list(fcurves)


def _binding(
    *,
    property_name: str,
    type_index: int,
    transform_index: int,
    data_type: int,
    component_labels,
    timeline_parameter_hash: int = 0x00112233,
    datatype_hash: int = 0x44556677,
    data_type_name: str = "",
    normalized_color: bool = False,
):
    return {
        "property_name": property_name,
        "type_index": type_index,
        "transform_index": transform_index,
        "timeline_parameter_hash": timeline_parameter_hash,
        "datatype_hash": datatype_hash,
        "data_type": data_type,
        "data_type_name": data_type_name,
        "component_labels": list(component_labels),
        "normalized_color": normalized_color,
    }


def _attached_timl_action(name: str, fcurves, *, transform_count: int):
    return FakeAction(
        name,
        fcurves,
        mhw_anim_tools_import_kind="attached_timl",
        mhw_anim_tools_timl_transform_count=transform_count,
    )


class TimlSamplingTests(unittest.TestCase):
    def test_samples_float_and_color_controller_curves_back_to_timl_space(self):
        action = _attached_timl_action(
            "TIML::sample::000",
            [
                FakeFCurve('["timl_float"]', 0, {0.0: 1.0, 24.5: 2.0}),
                FakeFCurve('["timl_color"]', 0, {0.0: 16.0 / 255.0, 10.0: 32.0 / 255.0}),
                FakeFCurve('["timl_color"]', 1, {0.0: 32.0 / 255.0, 10.0: 64.0 / 255.0}),
                FakeFCurve('["timl_color"]', 2, {0.0: 64.0 / 255.0, 10.0: 96.0 / 255.0}),
                FakeFCurve('["timl_color"]', 3, {0.0: 1.0, 10.0: 128.0 / 255.0}),
            ],
            transform_count=2,
        )
        controller = FakeController(
            "TIML Controller::sample::000",
            action=action,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 0,
                TIML_SOURCE_OFFSET_KEY: 0x1234,
                TIML_ACTION_NAME_KEY: action.name,
                TIML_BINDINGS_KEY: json.dumps(
                    [
                        _binding(
                            property_name="timl_float",
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            data_type_name="float",
                            component_labels=("value",),
                        ),
                        _binding(
                            property_name="timl_color",
                            type_index=0,
                            transform_index=1,
                            data_type=3,
                            data_type_name="color_rgba8",
                            component_labels=("r", "g", "b", "a"),
                            normalized_color=True,
                        ),
                    ]
                ),
            },
        )

        result = sample_timl_controller_action(controller)

        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.warning_count, 0)
        self.assertTrue(is_imported_timl_controller(controller))
        self.assertIsNotNone(result.metadata)
        self.assertEqual(result.metadata.source_lmt, "sample.lmt")
        self.assertEqual(result.sampled_transform_count, 2)
        self.assertEqual(result.keyframe_count, 4)
        self.assertEqual(result.frame_end, 25)
        transforms = {
            (transform.type_index, transform.transform_index): transform
            for transform in result.sampled_transforms
        }
        float_transform = transforms[(0, 0)]
        self.assertEqual(float_transform.keyframes[1].frame, 24.5)
        self.assertEqual(float_transform.keyframes[1].value, (2.0,))
        color_transform = transforms[(0, 1)]
        self.assertEqual(color_transform.keyframes[0].value, (16.0, 32.0, 64.0, 255.0))
        self.assertEqual(color_transform.keyframes[1].value, (32.0, 64.0, 96.0, 128.0))

    def test_mismatched_channel_keyframe_times_are_rejected(self):
        action = _attached_timl_action(
            "TIML::broken::000",
            [
                FakeFCurve('["timl_color"]', 0, {0.0: 0.0, 2.0: 1.0}, authored_frames=(0.0, 2.0)),
                FakeFCurve('["timl_color"]', 1, {0.0: 0.0, 3.0: 1.0}, authored_frames=(0.0, 3.0)),
                FakeFCurve('["timl_color"]', 2, {0.0: 0.0, 2.0: 1.0}, authored_frames=(0.0, 2.0)),
                FakeFCurve('["timl_color"]', 3, {0.0: 0.0, 2.0: 1.0}, authored_frames=(0.0, 2.0)),
            ],
            transform_count=1,
        )
        controller = FakeController(
            "TIML Controller::broken::000",
            action=action,
            **{
                TIML_ACTION_NAME_KEY: action.name,
                TIML_BINDINGS_KEY: json.dumps(
                    [
                        _binding(
                            property_name="timl_color",
                            type_index=0,
                            transform_index=0,
                            data_type=3,
                            data_type_name="color_rgba8",
                            component_labels=("r", "g", "b", "a"),
                            normalized_color=True,
                        )
                    ]
                ),
            },
        )

        result = sample_timl_controller_action(controller)

        self.assertEqual(result.sampled_transform_count, 0)
        self.assertEqual(result.skipped_transform_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertEqual(result.warning_count, 2)
        self.assertTrue(
            any("keyframe times no longer match" in diagnostic.message for diagnostic in result.diagnostics)
        )

    def test_integer_and_boolean_values_warn_when_off_grid(self):
        action = _attached_timl_action(
            "TIML::quantize::000",
            [
                FakeFCurve('["timl_int"]', 0, {0.0: 1.5}),
                FakeFCurve('["timl_bool"]', 0, {0.0: 0.25}),
            ],
            transform_count=2,
        )
        controller = FakeController(
            "TIML Controller::quantize::000",
            action=action,
            **{
                TIML_ACTION_NAME_KEY: action.name,
                TIML_BINDINGS_KEY: json.dumps(
                    [
                        _binding(
                            property_name="timl_int",
                            type_index=0,
                            transform_index=0,
                            data_type=0,
                            data_type_name="sint32",
                            component_labels=("value",),
                        ),
                        _binding(
                            property_name="timl_bool",
                            type_index=0,
                            transform_index=1,
                            data_type=4,
                            data_type_name="bool_uint32",
                            component_labels=("value",),
                        ),
                    ]
                ),
            },
        )

        result = sample_timl_controller_action(controller)

        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.sampled_transform_count, 2)
        self.assertEqual(result.warning_count, 2)
        messages = "\n".join(diagnostic.message for diagnostic in result.diagnostics)
        self.assertIn("off-grid", messages)
        self.assertIn("not 0/1", messages)

    def test_non_linear_interpolation_warns_but_samples(self):
        action = _attached_timl_action(
            "TIML::bezier::000",
            [
                FakeFCurve('["timl_float"]', 0, {0.0: 1.0, 5.0: 2.0}, interpolation="BEZIER"),
            ],
            transform_count=1,
        )
        controller = FakeController(
            "TIML Controller::bezier::000",
            action=action,
            **{
                TIML_ACTION_NAME_KEY: action.name,
                TIML_BINDINGS_KEY: json.dumps(
                    [
                        _binding(
                            property_name="timl_float",
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            data_type_name="float",
                            component_labels=("value",),
                        )
                    ]
                ),
            },
        )

        result = sample_timl_controller_action(controller)

        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.sampled_transform_count, 1)
        self.assertEqual(result.warning_count, 1)
        self.assertEqual(result.sampled_transforms[0].keyframes[0].interpolation, "BEZIER")

    def test_duplicate_binding_identity_is_rejected(self):
        action = _attached_timl_action(
            "TIML::duplicate_identity::000",
            [
                FakeFCurve('["timl_a"]', 0, {0.0: 1.0}),
                FakeFCurve('["timl_b"]', 0, {0.0: 2.0}),
            ],
            transform_count=2,
        )
        controller = FakeController(
            "TIML Controller::duplicate_identity::000",
            action=action,
            **{
                TIML_ACTION_NAME_KEY: action.name,
                TIML_BINDINGS_KEY: json.dumps(
                    [
                        _binding(
                            property_name="timl_a",
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            data_type_name="float",
                            component_labels=("value",),
                        ),
                        _binding(
                            property_name="timl_b",
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            data_type_name="float",
                            component_labels=("value",),
                        ),
                    ]
                ),
            },
        )

        result = sample_timl_controller_action(controller)

        self.assertGreater(result.error_count, 0)
        self.assertEqual(result.sampled_transform_count, 0)
        self.assertTrue(any("duplicate source transform identities" in diagnostic.message for diagnostic in result.diagnostics))

    def test_duplicate_binding_property_name_is_rejected(self):
        action = _attached_timl_action(
            "TIML::duplicate_property::000",
            [
                FakeFCurve('["timl_shared"]', 0, {0.0: 1.0}),
            ],
            transform_count=2,
        )
        controller = FakeController(
            "TIML Controller::duplicate_property::000",
            action=action,
            **{
                TIML_ACTION_NAME_KEY: action.name,
                TIML_BINDINGS_KEY: json.dumps(
                    [
                        _binding(
                            property_name="timl_shared",
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            data_type_name="float",
                            component_labels=("value",),
                        ),
                        _binding(
                            property_name="timl_shared",
                            type_index=0,
                            transform_index=1,
                            data_type=2,
                            data_type_name="float",
                            component_labels=("value",),
                        ),
                    ]
                ),
            },
        )

        result = sample_timl_controller_action(controller)

        self.assertGreater(result.error_count, 0)
        self.assertEqual(result.sampled_transform_count, 0)
        self.assertTrue(any("reuses custom property names" in diagnostic.message for diagnostic in result.diagnostics))


if __name__ == "__main__":
    unittest.main()
