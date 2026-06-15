from __future__ import annotations

import unittest
from unittest.mock import patch

from blender_adapter.timl_metadata import TIML_ACTION_NAME_KEY
from blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from blender_adapter.timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
from blender_adapter.timl_preview_state import imported_preview_signature_json
from blender_adapter.timl_sampling import SampledTimlKeyframe
from blender_adapter.timl_sampling import SampledTimlTransform
from blender_adapter.timl_sampling import TimlControllerMetadata
from blender_adapter.timl_sampling import TimlSamplingResult
from blender_adapter.timl_writeback_plan import plan_timl_controller_writeback
from core.formats.timl.reader import SIGNED_KEYFRAME_STRUCT
from core.formats.timl.reader import UNSIGNED_KEYFRAME_STRUCT
from tests.test_timl_reader import _build_embedded_timl_source_bytes
from tests.test_timl_reader import _build_simple_embedded_timl_source_bytes
from tests.test_timl_reader import DATA_STRUCT
from tests.test_timl_reader import TRANSFORM_STRUCT
from tests.test_timl_reader import TYPE_STRUCT


class _FakeAnimationData:
    def __init__(self, action):
        self.action = action


class _FakeAction(dict):
    def __init__(self, name: str, **metadata):
        super().__init__(metadata)
        self.name = name


class _FakeController(dict):
    def __init__(self, name: str, *, action=None, **metadata):
        super().__init__(metadata)
        self.name = name
        self.animation_data = _FakeAnimationData(action)


class _ImportedKeyframe:
    def __init__(self, *, frame: float, value, interpolation: int):
        self.frame = float(frame)
        self.value = tuple(float(component) for component in value)
        self.interpolation = int(interpolation)


class _ImportedTransform:
    def __init__(self, *, type_index: int, transform_index: int, data_type: int, keyframes):
        self.type_index = int(type_index)
        self.transform_index = int(transform_index)
        self.data_type = int(data_type)
        self.keyframes = tuple(keyframes)


def _build_simple_integer_embedded_timl_source_bytes(*, data_type: int, key_value: int = 0) -> tuple[bytes, int]:
    timl_offset = 224
    payload = bytearray(144)
    DATA_STRUCT.pack_into(payload, 0, timl_offset + 48, 1, 0, 0, 10.0, 2.0, 0, 0x12345678)
    TYPE_STRUCT.pack_into(payload, 48, timl_offset + 80, 1, 0x11223344, 0)
    TRANSFORM_STRUCT.pack_into(payload, 80, timl_offset + 112, 1, 0x55667788, data_type)
    if int(data_type) == 0:
        SIGNED_KEYFRAME_STRUCT.pack_into(payload, 112, int(key_value), 0, 0, 12.0, 1, 0)
    else:
        UNSIGNED_KEYFRAME_STRUCT.pack_into(payload, 112, int(key_value), 0, 0, 12.0, 1, 0)
    source_bytes = (b"\x00" * timl_offset) + bytes(payload)
    return source_bytes, timl_offset


class TimlWritebackPlanTests(unittest.TestCase):
    def test_structural_linear_edit_is_planned_as_preview_rebuild(self):
        source_bytes, source_offset = _build_simple_embedded_timl_source_bytes()
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: imported_preview_signature_json(
                    [
                        _ImportedTransform(
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            keyframes=(
                                _ImportedKeyframe(frame=12.0, value=(3.5,), interpolation=1),
                            ),
                        )
                    ]
                ),
            },
        )
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=7,
                source_offset=source_offset,
                transform_count=1,
            ),
            sampled_transform_count=1,
            keyframe_count=2,
            sampled_transforms=(
                SampledTimlTransform(
                    property_name="timl_float",
                    type_index=0,
                    transform_index=0,
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(3.5,), interpolation="LINEAR"),
                        SampledTimlKeyframe(frame=24.0, value=(6.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=7,
                source_offset=source_offset,
            )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.transform_plans[0].status, "rewrite_preview")
        self.assertTrue(any("Blender keys" in diagnostic.message for diagnostic in plan.diagnostics))

    def test_structural_linear_edit_on_advanced_source_is_blocked(self):
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: imported_preview_signature_json(
                    [
                        _ImportedTransform(
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            keyframes=(
                                _ImportedKeyframe(frame=12.0, value=(3.5,), interpolation=1),
                            ),
                        )
                    ]
                ),
            },
        )
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=7,
                source_offset=source_offset,
                transform_count=1,
            ),
            sampled_transform_count=1,
            keyframe_count=2,
            sampled_transforms=(
                SampledTimlTransform(
                    property_name="timl_float",
                    type_index=0,
                    transform_index=0,
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(3.5,), interpolation="LINEAR"),
                        SampledTimlKeyframe(frame=24.0, value=(6.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=7,
                source_offset=source_offset,
            )

        self.assertGreater(plan.error_count, 0)
        self.assertEqual(plan.transform_plans[0].status, "unsupported_rebuild")
        self.assertEqual(plan.transform_plans[0].reason, "advanced_source_rebuild")
        self.assertTrue(any("Structural rebuild is blocked" in diagnostic.message for diagnostic in plan.diagnostics))

    def test_structural_bezier_edit_is_rejected_before_writer(self):
        source_bytes, source_offset = _build_simple_embedded_timl_source_bytes()
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: imported_preview_signature_json(
                    [
                        _ImportedTransform(
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            keyframes=(
                                _ImportedKeyframe(frame=12.0, value=(3.5,), interpolation=1),
                            ),
                        )
                    ]
                ),
            },
        )
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=7,
                source_offset=source_offset,
                transform_count=1,
            ),
            sampled_transform_count=1,
            keyframe_count=2,
            sampled_transforms=(
                SampledTimlTransform(
                    property_name="timl_float",
                    type_index=0,
                    transform_index=0,
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(3.5,), interpolation="LINEAR"),
                        SampledTimlKeyframe(frame=24.0, value=(6.0,), interpolation="BEZIER"),
                    ),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=7,
                source_offset=source_offset,
            )

        self.assertEqual(plan.transform_plans[0].status, "unsupported_rebuild")
        self.assertEqual(plan.error_count, 1)
        self.assertTrue(any("unsupported preview interpolation" in diagnostic.message for diagnostic in plan.diagnostics))

    def test_duplicate_sampled_transform_identity_is_rejected(self):
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: imported_preview_signature_json(()),
            },
        )
        duplicated_transform = SampledTimlTransform(
            property_name="timl_float",
            type_index=0,
            transform_index=0,
            timeline_parameter_hash=0x11223344,
            datatype_hash=0x55667788,
            data_type=2,
            data_type_name="float",
            value_kind="scalar",
            control_kind="float",
            component_labels=("value",),
            keyframes=(
                SampledTimlKeyframe(frame=12.0, value=(3.5,), interpolation="LINEAR"),
            ),
        )
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=7,
                source_offset=source_offset,
                transform_count=2,
            ),
            sampled_transform_count=2,
            keyframe_count=2,
            sampled_transforms=(duplicated_transform, duplicated_transform),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=7,
                source_offset=source_offset,
            )

        self.assertGreater(plan.error_count, 0)
        self.assertEqual(plan.transform_plans, ())
        self.assertTrue(any("duplicate transform identities" in diagnostic.message for diagnostic in plan.diagnostics))

    def test_timeline_hash_mismatch_is_blocked_before_writer(self):
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: imported_preview_signature_json(
                    [
                        _ImportedTransform(
                            type_index=0,
                            transform_index=0,
                            data_type=2,
                            keyframes=(_ImportedKeyframe(frame=12.0, value=(3.5,), interpolation=1),),
                        )
                    ]
                ),
            },
        )
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=7,
                source_offset=source_offset,
                transform_count=1,
            ),
            sampled_transform_count=1,
            keyframe_count=1,
            sampled_transforms=(
                SampledTimlTransform(
                    property_name="timl_float",
                    type_index=0,
                    transform_index=0,
                    timeline_parameter_hash=0x99887766,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(SampledTimlKeyframe(frame=12.0, value=(6.0,), interpolation="LINEAR"),),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=7,
                source_offset=source_offset,
            )

        self.assertGreater(plan.error_count, 0)
        self.assertEqual(plan.transform_plans[0].status, "unsupported_rebuild")
        self.assertEqual(plan.transform_plans[0].reason, "timeline_hash_mismatch")
        self.assertTrue(any("timeline hash changed" in diagnostic.message for diagnostic in plan.diagnostics))

    def test_integer_off_grid_edit_is_blocked_before_writer(self):
        source_bytes, source_offset = _build_simple_integer_embedded_timl_source_bytes(data_type=0, key_value=3)
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: imported_preview_signature_json(
                    [
                        _ImportedTransform(
                            type_index=0,
                            transform_index=0,
                            data_type=0,
                            keyframes=(_ImportedKeyframe(frame=12.0, value=(3.0,), interpolation=1),),
                        )
                    ]
                ),
            },
        )
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=7,
                source_offset=source_offset,
                transform_count=1,
            ),
            sampled_transform_count=1,
            keyframe_count=2,
            sampled_transforms=(
                SampledTimlTransform(
                    property_name="timl_int",
                    type_index=0,
                    transform_index=0,
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=0,
                    data_type_name="sint32",
                    value_kind="integer",
                    control_kind="integer",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(3.0,), interpolation="LINEAR"),
                        SampledTimlKeyframe(frame=24.0, value=(3.5,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=7,
                source_offset=source_offset,
            )

        self.assertGreater(plan.error_count, 0)
        self.assertEqual(plan.transform_plans[0].status, "unsupported_rebuild")
        self.assertEqual(plan.transform_plans[0].reason, "integer_off_grid")
        self.assertTrue(any("lossy quantization" in diagnostic.message for diagnostic in plan.diagnostics))

    def test_boolean_off_grid_edit_is_blocked_before_writer(self):
        source_bytes, source_offset = _build_simple_integer_embedded_timl_source_bytes(data_type=4, key_value=1)
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: imported_preview_signature_json(
                    [
                        _ImportedTransform(
                            type_index=0,
                            transform_index=0,
                            data_type=4,
                            keyframes=(_ImportedKeyframe(frame=12.0, value=(1.0,), interpolation=1),),
                        )
                    ]
                ),
            },
        )
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=7,
                source_offset=source_offset,
                transform_count=1,
            ),
            sampled_transform_count=1,
            keyframe_count=1,
            sampled_transforms=(
                SampledTimlTransform(
                    property_name="timl_bool",
                    type_index=0,
                    transform_index=0,
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=4,
                    data_type_name="bool_uint32",
                    value_kind="boolean",
                    control_kind="integer",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(0.5,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=7,
                source_offset=source_offset,
            )

        self.assertGreater(plan.error_count, 0)
        self.assertEqual(plan.transform_plans[0].status, "unsupported_rebuild")
        self.assertEqual(plan.transform_plans[0].reason, "boolean_off_grid")
        self.assertTrue(any("0 or 1" in diagnostic.message for diagnostic in plan.diagnostics))

    def test_integer_precision_risk_is_blocked_before_writer(self):
        source_bytes, source_offset = _build_simple_integer_embedded_timl_source_bytes(data_type=1, key_value=3)
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: imported_preview_signature_json(
                    [
                        _ImportedTransform(
                            type_index=0,
                            transform_index=0,
                            data_type=1,
                            keyframes=(_ImportedKeyframe(frame=12.0, value=(3.0,), interpolation=1),),
                        )
                    ]
                ),
            },
        )
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=7,
                source_offset=source_offset,
                transform_count=1,
            ),
            sampled_transform_count=1,
            keyframe_count=1,
            sampled_transforms=(
                SampledTimlTransform(
                    property_name="timl_uint",
                    type_index=0,
                    transform_index=0,
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=1,
                    data_type_name="uint32",
                    value_kind="integer",
                    control_kind="integer",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(20000000.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=7,
                source_offset=source_offset,
            )

        self.assertGreater(plan.error_count, 0)
        self.assertEqual(plan.transform_plans[0].status, "unsupported_rebuild")
        self.assertEqual(plan.transform_plans[0].reason, "integer_precision_risk")
        self.assertTrue(any("exact Blender float precision" in diagnostic.message for diagnostic in plan.diagnostics))


if __name__ == "__main__":
    unittest.main()
