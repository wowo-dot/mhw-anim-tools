from dataclasses import asdict, replace
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest

from core.diagnostics.errors import ValidationError
from core.formats.lmt.content_signature import action_header_content_signature, track_content_signature, timl_payload_content_signature
from core.formats.lmt.decoder import decode_action_tracks
from core.formats.lmt.export_context import RawTimlPayload, extract_raw_timl_payload_layouts
from core.formats.lmt.merge_writer import write_merged_lmt_bytes, write_source_action_lmt_bytes
from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.reconstructed import LmtReconstructedAction, LmtReconstructedKeyframe, LmtReconstructedTrack
from core.formats.lmt.source_bank import LmtSourceBankCache
from blender_adapter.export_workflow import ExportAnalysis, resolve_source_action_export_metadata, write_source_action_export_file
from blender_adapter.source_identity import SourceFileIdentity, store_source_file_identity
from test_lmt_merge_writer import _build_source_container_with_shared_timl, _build_source_container_with_lerp_before_raw_tracks


class SourceActionExportTests(unittest.TestCase):
    def test_no_edit_raw_quaternion_export_remains_byte_identical(self):
        raw = _build_source_container_with_lerp_before_raw_tracks()
        source = read_lmt_bytes(raw)
        action = LmtReconstructedAction("no edit", 0, 20, tuple(
            LmtReconstructedTrack(bone_id=bone, usage=0, basis_value=(1., 0., 0., 0.), source_track_index=index)
            for index, bone in enumerate((1, 2))
        ))
        output = write_source_action_lmt_bytes(
            source, raw, action, action_id=0, preserve_source_identities={(1, 0), (2, 0)},
        )
        self.assertEqual(output, raw)

    def test_intermediate_keeps_slot_timing_tracks_and_rebased_advanced_timl(self):
        raw, _ = _build_source_container_with_shared_timl()
        source = read_lmt_bytes(raw)
        action = LmtReconstructedAction(
            action_name="edited", frame_start=0, frame_end=20,
            tracks=(LmtReconstructedTrack(
                bone_id=9, usage=1, basis_value=(0., 0., 0.),
                keyframes=(LmtReconstructedKeyframe(0, (1., 2., 3.)), LmtReconstructedKeyframe(19, (5., 6., 7.))),
            ),),
        )
        full_bytes = write_merged_lmt_bytes(source, raw, action, action_id=1)
        single_bytes = write_source_action_lmt_bytes(source, raw, action, action_id=1)
        full = read_lmt_bytes(full_bytes)
        single = read_lmt_bytes(single_bytes)
        self.assertEqual(single.header, source.header)
        self.assertEqual(tuple(a.id for a in single.actions), (1,))
        self.assertEqual(single.entry_offsets[0], 0)
        expected, actual = full.actions[1], single.actions[0]
        self.assertEqual(single.entry_offsets[1], full.entry_offsets[1])
        self.assertEqual(actual.tracks, expected.tracks)
        self.assertEqual(action_header_content_signature(expected), action_header_content_signature(actual))
        self.assertEqual([track_content_signature(t) for t in expected.tracks], [track_content_signature(t) for t in actual.tracks])
        self.assertEqual(decode_action_tracks(expected), decode_action_tracks(actual))
        self.assertEqual(actual.header.frame_count, 20)
        self.assertEqual(actual.header.loop_frame, source.actions[1].header.loop_frame)
        original_payload = extract_raw_timl_payload_layouts(source, raw)[224]
        payload = extract_raw_timl_payload_layouts(single, single_bytes)[actual.header.timl_offset]
        self.assertNotEqual(actual.header.timl_offset, 224)
        self.assertEqual(timl_payload_content_signature(original_payload, source_offset=224),
                         timl_payload_content_signature(payload, source_offset=actual.header.timl_offset))
        # Reusing old absolute pointers at a new address does not compare equal.
        with self.assertRaises(ValidationError):
            timl_payload_content_signature(original_payload, source_offset=actual.header.timl_offset)
        changed = bytearray(payload.payload)
        struct.pack_into("<f", changed, 112, 999.)
        self.assertNotEqual(timl_payload_content_signature(payload, source_offset=actual.header.timl_offset),
                            timl_payload_content_signature(RawTimlPayload(bytes(changed), payload.rebase_offsets), source_offset=actual.header.timl_offset))
        self.assertEqual(single_bytes, write_source_action_lmt_bytes(source, raw, action, action_id=1))

    def test_raw_track_signatures_match_deep_copy_audit_and_detect_all_fields(self):
        raw = _build_source_container_with_lerp_before_raw_tracks()
        track = read_lmt_bytes(raw).actions[0].tracks[0]
        relocated = replace(track, header=replace(track.header, buffer_offset=9999, lerp_offset=99999))

        def old_signature(value):
            header = asdict(value.header)
            header.pop("buffer_offset")
            header.pop("lerp_offset")
            return header, value.raw_buffer, value.lerp_basis

        variations = [relocated, replace(track, raw_buffer=b"modified"),
                      replace(track, lerp_basis=replace(track.lerp_basis, mult=(2., 3., 4., 5.)))]
        for field, value in asdict(track.header).items():
            if field in {"buffer_offset", "lerp_offset"}:
                continue
            altered = tuple(v + 1 for v in value) if isinstance(value, tuple) else value + 1
            variations.append(replace(track, header=replace(track.header, **{field: altered})))
        for other in variations:
            self.assertEqual(old_signature(track) == old_signature(other),
                             track_content_signature(track) == track_content_signature(other))

    def test_intermediate_rebases_replacement_timl_and_preserves_loop_boundary(self):
        raw, _ = _build_source_container_with_shared_timl()
        source = read_lmt_bytes(raw)
        payload = extract_raw_timl_payload_layouts(source, raw)[224]
        changed = bytearray(payload.payload)
        struct.pack_into("<f", changed, 112, 9.5)
        replacement = RawTimlPayload(bytes(changed), payload.rebase_offsets)
        action = LmtReconstructedAction("event value edit", 0, 10, ())
        output = write_source_action_lmt_bytes(source, raw, action, action_id=0,
                                               replacement_timl_payloads={224: replacement})
        parsed = read_lmt_bytes(output)
        result_action = parsed.actions[0]
        self.assertEqual(result_action.header.loop_frame, 7)
        self.assertEqual(result_action.header.frame_count, 10)
        result_payload = extract_raw_timl_payload_layouts(parsed, output)[result_action.header.timl_offset]
        self.assertEqual(timl_payload_content_signature(replacement, source_offset=224),
                         timl_payload_content_signature(result_payload, source_offset=result_action.header.timl_offset))

    def test_invalid_plans_still_fail_and_do_not_create_an_artifact(self):
        raw, _ = _build_source_container_with_shared_timl()
        source = read_lmt_bytes(raw)
        bad = LmtReconstructedAction("bad", 0, 10, (
            LmtReconstructedTrack(bone_id=1, usage=1, basis_value=(float("nan"), 0., 0.)),
        ))
        with self.assertRaises(ValidationError):
            write_source_action_lmt_bytes(source, raw, bad, action_id=0)
        with self.assertRaises(ValidationError):
            write_source_action_lmt_bytes(source, raw, bad, action_id=999)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rejected.lmt"
            with self.assertRaises(ValidationError):
                write_source_action_export_file(str(path), ExportAnalysis())
            self.assertFalse(path.exists())

    def test_cached_export_metadata_checks_current_bytes_against_import_identity(self):
        raw, _ = _build_source_container_with_shared_timl()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.lmt"
            path.write_bytes(raw)
            cache = LmtSourceBankCache()
            bank = cache.load(path)
            action = dict(mhw_anim_tools_source_lmt=str(path), mhw_anim_tools_entry_id=0,
                          mhw_anim_tools_import_kind="lmt_action")
            store_source_file_identity(action, SourceFileIdentity(len(bank.data), bank.sha256))
            scene = SimpleNamespace(last_lmt_path="", lmt_entries=[], selected_entry_index=0)
            metadata, report = resolve_source_action_export_metadata(scene, action, source_cache=cache)
            self.assertEqual(report.error_count, 0)
            self.assertIs(metadata.source_lmt, bank.lmt)
            changed = bytearray(raw)
            changed[8] ^= 1
            path.write_bytes(changed)
            updated, report = resolve_source_action_export_metadata(scene, action, source_cache=cache)
            self.assertGreater(report.error_count, 0)
            self.assertTrue(any(d.code == "lmt.export.source_identity" for d in report.diagnostics))
            self.assertIsNot(updated.source_lmt, bank.lmt)
