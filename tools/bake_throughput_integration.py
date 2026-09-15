"""Opt-in Rig44 caller example, exercised by benchmark_bake_throughput.py.

This file is not loaded by the add-on. install(common) adapts the isolated
worker's imported bake_common module; it never edits the production scripts.
The protected-track policy and append layout below are the existing Rig44
policy. Keep them in the caller rather than making them global add-on policy.
"""

from dataclasses import replace
from pathlib import Path
import struct

from mhw_anim_tools.core.formats.lmt.content_signature import action_header_content_signature, track_content_signature
from mhw_anim_tools.core.formats.lmt.export_context import extract_raw_timl_payload_layouts
from mhw_anim_tools.core.formats.lmt.merge_writer import _serialize_source_action, _serialize_action_bytes
from mhw_anim_tools.core.formats.lmt.reader import read_lmt_file
from mhw_anim_tools.core.formats.lmt.source_bank import LmtSourceBankCache
from mhw_anim_tools.blender_adapter.export_workflow import analyze_action_for_export, write_source_action_export_file
from mhw_anim_tools.blender_adapter.source_identity import SourceFileIdentity


def install(common):
    cache = LmtSourceBankCache()
    original_load_action = common.load_action

    def load_action(rig, path, entry, label):
        path = Path(path)
        if path.suffix == ".lmtpatch" or not path.exists():
            return original_load_action(rig, path, entry, label)
        bank = cache.load(path)
        result = common.import_lmt_action_to_armature(
            bank.lmt, entry, rig, source_path=str(path),
            source_identity=SourceFileIdentity(size=len(bank.data), sha256=bank.sha256),
        )
        assert result.error_count == 0, common.dataclasses.asdict(result)
        action = common.bpy.data.actions[result.action_name]
        action.name = label
        common.attach(rig, action)
        return action

    def encode(profile, source, entry, poses, destination):
        action = common.load_action(profile.rig, source, entry, f"Rig44 - {profile.label} source {entry}").copy()
        action.name = f"Rig44 - {profile.label} baked {Path(source).stem} {entry}"
        common.key_poses(profile, action, poses)
        analysis = analyze_action_for_export(
            common.SimpleNamespace(target_armature=profile.rig, last_lmt_path="", lmt_entries=[], selected_entry_index=0),
            action, actions=common.bpy.data.actions, objects=common.bpy.data.objects,
            source_cache=cache,
        )
        assert analysis.is_ready, [(item.level, item.message) for item in analysis.diagnostics]
        destination.parent.mkdir(exist_ok=True, parents=True)
        write_source_action_export_file(str(destination), analysis)
        return action

    def replace_entries(source, replacements, destination):
        bank = cache.load(source)
        raw, parsed = bank.data, bank.lmt
        actions = {action.id: action for action in parsed.actions}
        # Retain the original caller's embedded-pointer validation.
        extract_raw_timl_payload_layouts(parsed, raw)
        out = bytearray(raw)

        def protected(track):
            return track.header.bone_id in {-1, 0, 251, 252, 253} or track.header.usage >= 3

        for entry, path in sorted(replacements.items()):
            old = actions[entry]
            new = next(action for action in read_lmt_file(path).actions if action.id == entry)
            tracks = tuple(track for track in new.tracks if not protected(track)) + tuple(track for track in old.tracks if protected(track))
            record = _serialize_source_action(replace(old, tracks=tracks))
            while len(out) % 16:
                out.append(0)
            offset = len(out)
            # Valid only because the ENTIRE original payload prefix is retained,
            # and verified below. This pointer must not be used in a rebuilt bank.
            out.extend(_serialize_action_bytes(offset, record, timl_offset=old.header.timl_offset))
            struct.pack_into("<Q", out, 16 + 8 * entry, offset)
        destination.parent.mkdir(exist_ok=True, parents=True)
        destination.write_bytes(out)
        output = cache.load(destination)
        assert output.data == out, "Output changed during readback"
        got = {action.id: action for action in output.lmt.actions}
        for entry, action in actions.items():
            other = got[entry]
            assert action_header_content_signature(action) == action_header_content_signature(other), (entry, "header")
            predicate = protected if entry in replacements else lambda track: True
            assert [track_content_signature(track) for track in action.tracks if predicate(track)] == [track_content_signature(track) for track in other.tracks if predicate(track)], (entry, "protected tracks")
            assert action.header.timl_offset == other.header.timl_offset, (entry, "TIML pointer")
        assert out[16 + 8 * parsed.header.entry_count:len(raw)] == raw[16 + 8 * parsed.header.entry_count:]
        return dict(source_sha256=bank.sha256, output_sha256=output.sha256, entries=sorted(replacements),
                    source_headers_events_root_control_tracks_and_siblings_preserved=True)

    common.load_action = load_action
    common.encode = encode
    common.replace_entries = replace_entries
    return cache
