from __future__ import annotations

import unittest
from unittest.mock import patch

from blender_adapter.timl_metadata import TIML_ACTION_NAME_KEY
from blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from blender_adapter.timl_metadata import TIML_ENTRY_ID_KEY
from blender_adapter.timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_LMT_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_OFFSET_KEY
from blender_adapter.timl_preview_state import imported_preview_signature_json
from blender_adapter.timl_sampling import SampledTimlKeyframe
from blender_adapter.timl_sampling import SampledTimlTransform
from blender_adapter.timl_sampling import TimlControllerMetadata
from blender_adapter.timl_sampling import TimlSamplingResult
from blender_adapter.timl_writeback import assess_timl_controller_shared_payload
from blender_adapter.timl_writeback import build_matching_timl_writeback
from blender_adapter.timl_writeback import matching_timl_controllers_for_export_action
from blender_adapter.timl_writeback import shared_source_action_ids
from tests.test_timl_reader import _build_embedded_timl_source_bytes


class _FakeAnimationData:
    def __init__(self, action):
        self.action = action


class _FakeController(dict):
    def __init__(self, name: str, *, action=None, **metadata):
        super().__init__(metadata)
        self.name = name
        self.animation_data = _FakeAnimationData(action)


class _FakeAction(dict):
    def __init__(self, name: str, **metadata):
        super().__init__(metadata)
        self.name = name


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


class _FakeHeader:
    def __init__(self, timl_offset: int):
        self.timl_offset = int(timl_offset)


class _FakeSourceAction:
    def __init__(self, action_id: int, timl_offset: int):
        self.id = int(action_id)
        self.header = _FakeHeader(timl_offset)


class _FakeSourceLmt:
    def __init__(self, source_name: str, actions):
        self.source_name = source_name
        self.actions = tuple(actions)


class TimlWritebackTests(unittest.TestCase):
    def test_shared_source_action_ids_collect_all_matching_actions(self):
        source_lmt = _FakeSourceLmt(
            "sample.lmt",
            [
                _FakeSourceAction(7, 224),
                _FakeSourceAction(8, 224),
                _FakeSourceAction(9, 0),
            ],
        )

        self.assertEqual(shared_source_action_ids(source_lmt, 224), (7, 8))

    def test_unchanged_controller_preserves_raw_payload_without_rewrite(self):
        export_action = _FakeAction(
            "LMT::sample::000",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=7,
            mhw_anim_tools_source_has_timl=True,
        )
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        raw_signature = imported_preview_signature_json(
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
        )
        controller_action = _FakeAction("TIML::sample::000", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::000",
            action=controller_action,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 7,
                TIML_SOURCE_OFFSET_KEY: source_offset,
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: raw_signature,
            },
        )
        source_lmt = _FakeSourceLmt("sample.lmt", [_FakeSourceAction(7, source_offset)])
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
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            result = build_matching_timl_writeback(
                export_action,
                [controller],
                source_lmt=source_lmt,
                source_bytes=source_bytes,
            )

        self.assertEqual(result.replacement_payloads, {})
        self.assertTrue(any("unchanged" in diagnostic.message for diagnostic in result.diagnostics))
        self.assertEqual(result.error_count, 0)

    def test_shared_source_offset_controller_matches_even_when_entry_id_differs(self):
        export_action = _FakeAction(
            "LMT::sample::008",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=8,
            mhw_anim_tools_source_timl_offset=224,
            mhw_anim_tools_source_has_timl=True,
        )
        controller_action = _FakeAction("TIML::sample::007", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::007",
            action=controller_action,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 7,
                TIML_SOURCE_OFFSET_KEY: 224,
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
            },
        )

        matches = matching_timl_controllers_for_export_action(export_action, [controller])

        self.assertEqual(matches, (controller,))

    def test_edited_shared_payload_can_use_sibling_controller_with_same_offset(self):
        export_action = _FakeAction(
            "LMT::sample::008",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=8,
            mhw_anim_tools_source_timl_offset=224,
            mhw_anim_tools_source_has_timl=True,
        )
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        raw_signature = imported_preview_signature_json(
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
        )
        controller_action = _FakeAction("TIML::sample::007", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::007",
            action=controller_action,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 7,
                TIML_SOURCE_OFFSET_KEY: source_offset,
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: raw_signature,
            },
        )
        source_lmt = _FakeSourceLmt("sample.lmt", [_FakeSourceAction(7, source_offset), _FakeSourceAction(8, source_offset)])
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
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(6.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            result = build_matching_timl_writeback(
                export_action,
                [controller],
                source_lmt=source_lmt,
                source_bytes=source_bytes,
            )

        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.shared_action_ids, (7, 8))
        self.assertIn(source_offset, result.replacement_payloads)
        self.assertTrue(any("shared by source actions 007, 008" in diagnostic.message for diagnostic in result.diagnostics))

    def test_conflicting_shared_payload_controllers_are_rejected(self):
        export_action = _FakeAction(
            "LMT::sample::008",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=8,
            mhw_anim_tools_source_timl_offset=224,
            mhw_anim_tools_source_has_timl=True,
        )
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        raw_signature = imported_preview_signature_json(
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
        )
        controller_action_a = _FakeAction("TIML::sample::007", mhw_anim_tools_import_kind="attached_timl")
        controller_a = _FakeController(
            "TIML Controller::sample::007",
            action=controller_action_a,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 7,
                TIML_SOURCE_OFFSET_KEY: source_offset,
                TIML_ACTION_NAME_KEY: controller_action_a.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: raw_signature,
            },
        )
        controller_action_b = _FakeAction("TIML::sample::008", mhw_anim_tools_import_kind="attached_timl")
        controller_b = _FakeController(
            "TIML Controller::sample::008",
            action=controller_action_b,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 8,
                TIML_SOURCE_OFFSET_KEY: source_offset,
                TIML_ACTION_NAME_KEY: controller_action_b.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: raw_signature,
            },
        )
        source_lmt = _FakeSourceLmt("sample.lmt", [_FakeSourceAction(7, source_offset), _FakeSourceAction(8, source_offset)])
        sampled_a = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller_a.name,
                action_name=controller_action_a.name,
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
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(6.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )
        sampled_b = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller_b.name,
                action_name=controller_action_b.name,
                source_lmt="sample.lmt",
                entry_id=8,
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
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(9.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        def _sample_side_effect(controller_object):
            if controller_object is controller_a:
                return sampled_a
            if controller_object is controller_b:
                return sampled_b
            raise AssertionError("unexpected controller")

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", side_effect=_sample_side_effect):
            result = build_matching_timl_writeback(
                export_action,
                [controller_a, controller_b],
                source_lmt=source_lmt,
                source_bytes=source_bytes,
            )

        self.assertEqual(result.replacement_payloads, {})
        self.assertGreater(result.error_count, 0)
        self.assertTrue(any("produce different edited TIML data" in diagnostic.message for diagnostic in result.diagnostics))

    def test_assess_shared_payload_reports_single_matching_controller(self):
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        controller_action = _FakeAction("TIML::sample::007", mhw_anim_tools_import_kind="attached_timl")
        controller = _FakeController(
            "TIML Controller::sample::007",
            action=controller_action,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 7,
                TIML_SOURCE_OFFSET_KEY: source_offset,
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
            },
        )
        source_lmt = _FakeSourceLmt("sample.lmt", [_FakeSourceAction(7, source_offset), _FakeSourceAction(8, source_offset)])

        assessment = assess_timl_controller_shared_payload(
            controller,
            [controller],
            source_lmt=source_lmt,
            source_bytes=source_bytes,
        )

        self.assertEqual(assessment.status, "single")
        self.assertEqual(assessment.shared_action_ids, (7, 8))
        self.assertEqual(assessment.matching_controller_names, ("TIML Controller::sample::007",))
        self.assertTrue(any("only one imported controller currently matches" in diagnostic.message for diagnostic in assessment.diagnostics))

    def test_assess_shared_payload_reports_conflict_before_export(self):
        source_bytes, source_offset = _build_embedded_timl_source_bytes()
        raw_signature = imported_preview_signature_json(
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
        )
        controller_action_a = _FakeAction("TIML::sample::007", mhw_anim_tools_import_kind="attached_timl")
        controller_a = _FakeController(
            "TIML Controller::sample::007",
            action=controller_action_a,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 7,
                TIML_SOURCE_OFFSET_KEY: source_offset,
                TIML_ACTION_NAME_KEY: controller_action_a.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: raw_signature,
            },
        )
        controller_action_b = _FakeAction("TIML::sample::008", mhw_anim_tools_import_kind="attached_timl")
        controller_b = _FakeController(
            "TIML Controller::sample::008",
            action=controller_action_b,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 8,
                TIML_SOURCE_OFFSET_KEY: source_offset,
                TIML_ACTION_NAME_KEY: controller_action_b.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: raw_signature,
            },
        )
        source_lmt = _FakeSourceLmt("sample.lmt", [_FakeSourceAction(7, source_offset), _FakeSourceAction(8, source_offset)])
        sampled_a = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller_a.name,
                action_name=controller_action_a.name,
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
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(6.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )
        sampled_b = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller_b.name,
                action_name=controller_action_b.name,
                source_lmt="sample.lmt",
                entry_id=8,
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
                    timeline_parameter_hash=0x11223344,
                    datatype_hash=0x55667788,
                    data_type=2,
                    data_type_name="float",
                    value_kind="scalar",
                    control_kind="float",
                    component_labels=("value",),
                    keyframes=(
                        SampledTimlKeyframe(frame=12.0, value=(9.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        def _sample_side_effect(controller_object):
            if controller_object is controller_a:
                return sampled_a
            if controller_object is controller_b:
                return sampled_b
            raise AssertionError("unexpected controller")

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", side_effect=_sample_side_effect):
            assessment = assess_timl_controller_shared_payload(
                controller_a,
                [controller_a, controller_b],
                source_lmt=source_lmt,
                source_bytes=source_bytes,
            )

        self.assertEqual(assessment.status, "conflict")
        self.assertEqual(assessment.shared_action_ids, (7, 8))
        self.assertEqual(
            assessment.matching_controller_names,
            ("TIML Controller::sample::007", "TIML Controller::sample::008"),
        )
        self.assertTrue(any("do not currently resolve to one consistent writeback payload" in diagnostic.message for diagnostic in assessment.diagnostics))


if __name__ == "__main__":
    unittest.main()
