from __future__ import annotations

import unittest

from blender_adapter.timl_metadata import TIML_ACTION_NAME_KEY
from blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from blender_adapter.timl_metadata import TIML_ENTRY_ID_KEY
from blender_adapter.timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_LMT_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_OFFSET_KEY
from blender_adapter.timl_sampling import SampledTimlKeyframe
from blender_adapter.timl_sampling import SampledTimlTransform
from blender_adapter.timl_sampling import TimlControllerMetadata
from blender_adapter.timl_sampling import TimlSamplingResult
from blender_adapter.timl_templates import default_event_loop_template_header
from blender_adapter.timl_templates import encode_timl_template_header
from blender_adapter.timl_templates import EVENT_LOOP_MFLAG_HASH
from blender_adapter.timl_templates import EVENT_LOOP_RELEASE_TIME_A_HASH
from blender_adapter.timl_templates import EVENT_LOOP_REQNO_A_HASH
from blender_adapter.timl_templates import EVENT_LOOP_TEMPLATE_KIND
from blender_adapter.timl_templates import EVENT_LOOP_TIMELINE_HASH
from blender_adapter.timl_writeback import build_matching_timl_writeback
from blender_adapter.timl_writeback_plan import plan_timl_controller_writeback
from core.formats.timl.embedded_writer import build_embedded_timl_data_payload_from_sampled
from core.formats.timl.reader import read_timl_data_bytes
from tests.test_timl_reader import _build_embedded_timl_source_bytes


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


def _build_empty_embedded_timl_source_bytes() -> tuple[bytes, int]:
    timl_offset = 224
    payload = bytearray(48)
    from tests.test_timl_reader import DATA_STRUCT

    DATA_STRUCT.pack_into(payload, 0, 0, 0, 0, 0, 0.0, 0.0, 0, 0)
    source_bytes = (b"\x00" * timl_offset) + bytes(payload)
    return source_bytes, timl_offset


def _eventloop_sampled_result(*, source_offset: int) -> TimlSamplingResult:
    return TimlSamplingResult(
        metadata=TimlControllerMetadata(
            carrier_name="TIML Controller::sample::005",
            action_name="TIML::sample::005",
            source_lmt="sample.lmt",
            entry_id=5,
            source_offset=source_offset,
            transform_count=3,
        ),
        sampled_transform_count=3,
        keyframe_count=4,
        sampled_transforms=(
            SampledTimlTransform(
                property_name="timl_eventloop_reqno_a_t00_x00",
                type_index=0,
                transform_index=0,
                timeline_parameter_hash=EVENT_LOOP_TIMELINE_HASH,
                datatype_hash=EVENT_LOOP_REQNO_A_HASH,
                data_type=1,
                data_type_name="uint32",
                value_kind="integer",
                control_kind="integer",
                component_labels=("value",),
                keyframes=(SampledTimlKeyframe(frame=0.0, value=(7304.0,), interpolation="LINEAR"),),
            ),
            SampledTimlTransform(
                property_name="timl_eventloop_releasetime_a_t00_x01",
                type_index=0,
                transform_index=1,
                timeline_parameter_hash=EVENT_LOOP_TIMELINE_HASH,
                datatype_hash=EVENT_LOOP_RELEASE_TIME_A_HASH,
                data_type=1,
                data_type_name="uint32",
                value_kind="integer",
                control_kind="integer",
                component_labels=("value",),
                keyframes=(SampledTimlKeyframe(frame=0.0, value=(100.0,), interpolation="LINEAR"),),
            ),
            SampledTimlTransform(
                property_name="timl_eventloop_mflag_t00_x02",
                type_index=0,
                transform_index=2,
                timeline_parameter_hash=EVENT_LOOP_TIMELINE_HASH,
                datatype_hash=EVENT_LOOP_MFLAG_HASH,
                data_type=1,
                data_type_name="uint32",
                value_kind="integer",
                control_kind="integer",
                component_labels=("value",),
                keyframes=(
                    SampledTimlKeyframe(frame=0.0, value=(1.0,), interpolation="LINEAR"),
                    SampledTimlKeyframe(frame=77.0, value=(0.0,), interpolation="LINEAR"),
                ),
            ),
        ),
    )


class TimlTemplateWriterTests(unittest.TestCase):
    def test_build_embedded_timl_payload_from_sampled_roundtrips_eventloop(self):
        payload, _rebase_offsets = build_embedded_timl_data_payload_from_sampled(
            _eventloop_sampled_result(source_offset=224).sampled_transforms,
            base_offset=224,
            data_index_a=3,
            data_index_b=4,
            animation_length=77.0,
            loop_start_point=0.0,
            loop_control=0,
            label_hash=0x8F64576D,
        )

        entry = read_timl_data_bytes(
            (b"\x00" * 224) + payload,
            data_offset=224,
            source_name="generated.lmt#timl",
            entry_id=5,
        )
        self.assertEqual(entry.type_count, 1)
        self.assertEqual(entry.data_index_a, 3)
        self.assertEqual(entry.data_index_b, 4)
        self.assertEqual(entry.animation_length, 77.0)
        self.assertEqual(entry.types[0].timeline_parameter_hash, EVENT_LOOP_TIMELINE_HASH)
        self.assertEqual(entry.types[0].transforms[0].datatype_hash, EVENT_LOOP_REQNO_A_HASH)
        self.assertEqual(entry.types[0].transforms[0].keyframes[0].value, 7304)
        self.assertEqual(entry.types[0].transforms[2].keyframes[-1].value, 0)

    def test_empty_source_eventloop_plan_is_rebuildable(self):
        source_bytes, source_offset = _build_empty_embedded_timl_source_bytes()
        controller_action = _FakeAction("TIML::sample::005", mhw_anim_tools_import_kind="attached_timl")
        header = default_event_loop_template_header(
            source_lmt="sample.lmt",
            entry_id=5,
            animation_length=77.0,
        )
        controller = _FakeController(
            "TIML Controller::sample::005",
            action=controller_action,
            **{
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: '{"transforms":[]}',
                "mhw_anim_tools_timl_template_kind": EVENT_LOOP_TEMPLATE_KIND,
                "mhw_anim_tools_timl_template_header": encode_timl_template_header(header),
            },
        )
        sampled = _eventloop_sampled_result(source_offset=source_offset)

        from unittest.mock import patch

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            plan = plan_timl_controller_writeback(
                controller,
                source_bytes=source_bytes,
                source_name="sample.lmt#timl",
                entry_id=5,
                source_offset=source_offset,
            )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual([item.status for item in plan.transform_plans], ["rewrite_preview", "rewrite_preview", "rewrite_preview"])

    def test_empty_source_eventloop_writeback_builds_replacement_payload(self):
        source_bytes, source_offset = _build_empty_embedded_timl_source_bytes()
        export_action = _FakeAction(
            "LMT::sample::005",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=5,
            mhw_anim_tools_source_timl_offset=source_offset,
            mhw_anim_tools_source_has_timl=True,
        )
        controller_action = _FakeAction("TIML::sample::005", mhw_anim_tools_import_kind="attached_timl")
        header = default_event_loop_template_header(
            source_lmt="sample.lmt",
            entry_id=5,
            animation_length=77.0,
        )
        controller = _FakeController(
            "TIML Controller::sample::005",
            action=controller_action,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 5,
                TIML_SOURCE_OFFSET_KEY: source_offset,
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
                TIML_IMPORTED_PREVIEW_SIGNATURE_KEY: '{"transforms":[]}',
                "mhw_anim_tools_timl_template_kind": EVENT_LOOP_TEMPLATE_KIND,
                "mhw_anim_tools_timl_template_header": encode_timl_template_header(header),
            },
        )
        source_lmt = _FakeSourceLmt("sample.lmt", [_FakeSourceAction(5, source_offset)])
        sampled = _eventloop_sampled_result(source_offset=source_offset)

        from unittest.mock import patch

        with patch("blender_adapter.timl_writeback_plan.sample_timl_controller_action", return_value=sampled):
            result = build_matching_timl_writeback(
                export_action,
                [controller],
                source_lmt=source_lmt,
                source_bytes=source_bytes,
            )

        self.assertEqual(result.error_count, 0)
        self.assertIn(source_offset, result.replacement_payloads)
        payload = result.replacement_payloads[source_offset].payload
        entry = read_timl_data_bytes(
            (b"\x00" * source_offset) + payload,
            data_offset=source_offset,
            source_name="generated.lmt#timl",
            entry_id=5,
        )
        self.assertEqual(entry.type_count, 1)
        self.assertEqual(entry.types[0].transforms[2].keyframes[-1].frame_timing, 77.0)


if __name__ == "__main__":
    unittest.main()
