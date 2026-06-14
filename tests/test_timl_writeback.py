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
from blender_adapter.timl_writeback import build_matching_timl_writeback


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
    def test_unchanged_controller_preserves_raw_payload_without_rewrite(self):
        export_action = _FakeAction(
            "LMT::sample::000",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=0,
            mhw_anim_tools_source_has_timl=True,
        )
        raw_signature = imported_preview_signature_json(
            [
                _ImportedTransform(
                    type_index=0,
                    transform_index=0,
                    data_type=2,
                    keyframes=(
                        _ImportedKeyframe(frame=0.0, value=(1.0,), interpolation=3),
                        _ImportedKeyframe(frame=10.0, value=(2.0,), interpolation=3),
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
                TIML_ENTRY_ID_KEY: 0,
                TIML_SOURCE_OFFSET_KEY: 0x1234,
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: raw_signature,
            },
        )
        source_lmt = _FakeSourceLmt("sample.lmt", [_FakeSourceAction(0, 0x1234)])
        sampled = TimlSamplingResult(
            metadata=TimlControllerMetadata(
                carrier_name=controller.name,
                action_name=controller_action.name,
                source_lmt="sample.lmt",
                entry_id=0,
                source_offset=0x1234,
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
                        SampledTimlKeyframe(frame=0.0, value=(1.0,), interpolation="LINEAR"),
                        SampledTimlKeyframe(frame=10.0, value=(2.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        with patch("blender_adapter.timl_writeback.sample_timl_controller_action", return_value=sampled):
            result = build_matching_timl_writeback(
                export_action,
                [controller],
                source_lmt=source_lmt,
                source_bytes=b"",
            )

        self.assertEqual(result.replacement_payloads, {})
        self.assertTrue(any("unchanged" in diagnostic.message for diagnostic in result.diagnostics))
        self.assertEqual(result.error_count, 0)


if __name__ == "__main__":
    unittest.main()
