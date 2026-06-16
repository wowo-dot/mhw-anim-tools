from __future__ import annotations

import addon_utils
import json
import struct
import sys
import tempfile
from pathlib import Path

import bpy


UINT64_STRUCT = struct.Struct("<Q")


def _parse_cli_args() -> dict[str, str]:
    if "--" not in sys.argv:
        return {}
    raw_args = sys.argv[sys.argv.index("--") + 1 :]
    parsed: dict[str, str] = {}
    iterator = iter(raw_args)
    for token in iterator:
        if not token.startswith("--"):
            continue
        key = token[2:]
        try:
            parsed[key] = next(iterator)
        except StopIteration as exc:
            raise SystemExit(f"Missing value for argument {token}") from exc
    return parsed


def _register_addon(repo_root: Path):
    package_parent = repo_root.parent
    if str(package_parent) not in sys.path:
        sys.path.insert(0, str(package_parent))
    import mhw_anim_tools

    mhw_anim_tools.register()
    return mhw_anim_tools


def _enable_mhw_model_editor():
    module_name = ""
    for module in addon_utils.modules():
        if module.__name__ in {"MHW_Model_Editor-main", "MHW_Model_Editor"}:
            module_name = module.__name__
            break
    if not module_name:
        raise SystemExit("MHW_Model_Editor add-on is not installed for the live-scene smoke test.")
    addon_utils.enable(module_name, default_set=False, persistent=False)
    return module_name


def _find_loaded_module(module_suffix: str):
    for module_name, module in sys.modules.items():
        if module_name.endswith(module_suffix):
            return module
    return None


def _reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (
        bpy.data.actions,
        bpy.data.armatures,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.images,
    ):
        for datablock in list(collection):
            if datablock.users == 0:
                collection.remove(datablock)


def _import_live_mod3_armature(mod3_path: Path):
    _enable_mhw_model_editor()
    blender_mod3_module = _find_loaded_module(".modules.mod3.blender_mod3")
    if blender_mod3_module is None or not hasattr(blender_mod3_module, "importMHWMod3File"):
        raise SystemExit("Could not locate MHW_Model_Editor's MOD3 import module.")
    success = blender_mod3_module.importMHWMod3File(
        str(mod3_path),
        {
            "clearScene": False,
            "loadMaterials": False,
            "loadMrl3Data": False,
            "loadUnusedTextures": False,
            "loadUnusedProps": False,
            "useBackfaceCulling": False,
            "reloadCachedTextures": False,
            "mrl3Path": "",
            "ArmatureDisplayType": "OCTAHEDRAL",
            "BonesDisplaySize": 5.0,
            "createCollections": True,
            "importArmatureOnly": True,
            "importAllLODs": False,
            "importBoundingBoxes": False,
            "loadPhysics": False,
            "addNestedCollections": True,
        },
    )
    if not success:
        raise SystemExit("MHW_Model_Editor failed to import the MOD3 smoke asset.")
    from mhw_anim_tools.integration.model_editor import choose_best_armature

    target_armature = choose_best_armature(bpy.context)
    if target_armature is None:
        raise SystemExit("Could not find a compatible armature after MOD3 import.")
    return target_armature


def _operator_status(result) -> str:
    if isinstance(result, set):
        return ",".join(sorted(result))
    return str(result)


def _normalized_timl_payloads(lmt, blob: bytes) -> tuple[bytes, ...]:
    from mhw_anim_tools.core.formats.lmt.export_context import extract_raw_timl_payload_layouts

    layouts = extract_raw_timl_payload_layouts(lmt, blob)
    normalized: list[bytes] = []
    for payload_offset, layout in sorted(layouts.items()):
        payload = bytearray(layout.payload)
        for field_offset in layout.rebase_offsets:
            (absolute_offset,) = UINT64_STRUCT.unpack_from(payload, field_offset)
            relative_offset = 0 if absolute_offset == 0 else absolute_offset - payload_offset
            UINT64_STRUCT.pack_into(payload, field_offset, relative_offset)
        normalized.append(bytes(payload))
    return tuple(normalized)


def _timl_sharing_groups(lmt) -> tuple[tuple[int, ...], ...]:
    groups: dict[int, list[int]] = {}
    for index, action in enumerate(lmt.actions):
        timl_offset = int(action.header.timl_offset)
        if timl_offset:
            groups.setdefault(timl_offset, []).append(index)
    return tuple(sorted(tuple(indices) for indices in groups.values()))


def _supported_decoded_tracks(decoded_action):
    from mhw_anim_tools.core.formats.lmt.semantics import get_usage_semantics

    supported = []
    for track in decoded_action.tracks:
        usage = get_usage_semantics(track.usage)
        if usage.transform in {"rotation", "translation", "scale"} and usage.blender_path_hint and not track.decode_error:
            supported.append(track)
    return supported


def _canonical_track_frames(decoded_track):
    from mhw_anim_tools.core.animation.transforms import canonicalize_quaternion_frames_wxyz
    from mhw_anim_tools.core.formats.lmt.semantics import get_usage_semantics

    usage = get_usage_semantics(decoded_track.usage)
    frames = [(0.0, tuple(float(component) for component in decoded_track.basis_value))]
    frames.extend((float(sample.frame), tuple(float(component) for component in sample.value)) for sample in decoded_track.keyframes)
    if decoded_track.tail_frame is not None and decoded_track.tail_value is not None:
        frames.append((float(decoded_track.tail_frame), tuple(float(component) for component in decoded_track.tail_value)))
    if usage.is_quaternion:
        frames = canonicalize_quaternion_frames_wxyz(frames, normalize=True)
    return {int(frame): tuple(float(component) for component in value) for frame, value in frames}


def _quaternion_values_match(expected, actual, tolerance: float) -> bool:
    from mhw_anim_tools.core.animation.transforms import flip_quaternion_wxyz
    from mhw_anim_tools.core.animation.transforms import normalize_quaternion_wxyz
    from mhw_anim_tools.core.animation.transforms import quaternion_dot_wxyz

    expected_quaternion = normalize_quaternion_wxyz(tuple(float(component) for component in expected))
    actual_quaternion = normalize_quaternion_wxyz(tuple(float(component) for component in actual))
    if quaternion_dot_wxyz(expected_quaternion, actual_quaternion) < 0.0:
        actual_quaternion = flip_quaternion_wxyz(actual_quaternion)
    return all(
        abs(actual_component - expected_component) <= tolerance
        for actual_component, expected_component in zip(actual_quaternion, expected_quaternion)
    )


def _compare_decoded_actions(expected_action, actual_action, tolerance=1e-3):
    from mhw_anim_tools.core.formats.lmt.semantics import get_usage_semantics

    actual_map = {
        (track.bone_id, track.usage): _canonical_track_frames(track)
        for track in _supported_decoded_tracks(actual_action)
    }
    mismatches = []
    for expected_track in _supported_decoded_tracks(expected_action):
        identity = (expected_track.bone_id, expected_track.usage)
        expected_frames = _canonical_track_frames(expected_track)
        actual_frames = actual_map.get(identity)
        usage_info = get_usage_semantics(expected_track.usage)
        if actual_frames is None:
            mismatches.append(f"Missing roundtrip track bone={expected_track.bone_id} usage={expected_track.usage}")
            continue
        missing_frames = sorted(frame for frame in expected_frames if frame not in actual_frames)
        if missing_frames:
            mismatches.append(
                "Missing frame(s) for bone=%d usage=%d expected=%s actual=%s"
                % (expected_track.bone_id, expected_track.usage, missing_frames, sorted(actual_frames))
            )
            continue
        for frame, expected_value in expected_frames.items():
            actual_value = actual_frames[frame]
            values_match = (
                _quaternion_values_match(expected_value, actual_value, tolerance)
                if usage_info.is_quaternion
                else all(abs(actual - expected) <= tolerance for actual, expected in zip(actual_value, expected_value))
            )
            if not values_match:
                mismatches.append(
                    "Value mismatch for bone=%d usage=%d frame=%d expected=%s actual=%s"
                    % (expected_track.bone_id, expected_track.usage, frame, expected_value, actual_value)
                )
    return mismatches


def _sibling_header_signature(action):
    return {
        "id": int(action.id),
        "frame_count": int(action.header.frame_count),
        "loop_frame": int(action.header.loop_frame),
        "flags": int(action.header.flags),
        "flags2": int(action.header.flags2),
        "null2": bytes(action.header.null2),
        "null3": tuple(int(value) for value in action.header.null3),
        "has_timl": bool(action.header.timl_offset),
        "track_headers": tuple(
            (
                int(track.header.bone_id),
                int(track.header.usage),
                int(track.header.buffer_type),
                int(track.header.buffer_size),
                int(track.header.joint_type),
                int(track.header.unknown_tag),
            )
            for track in action.tracks
        ),
    }


def main():
    args = _parse_cli_args()
    lmt_path = Path(args.get("lmt", ""))
    mod3_path = Path(args.get("mod3", ""))
    if not lmt_path.is_file():
        raise SystemExit("Provide --lmt <path-to-lmt> for the smoke test.")
    if not mod3_path.is_file():
        raise SystemExit("Provide --mod3 <path-to-mod3> for the merge-export smoke test.")

    repo_root = Path(__file__).resolve().parents[1]
    addon = _register_addon(repo_root)
    try:
        from mhw_anim_tools.core.formats.lmt.decoder import decode_action_tracks
        from mhw_anim_tools.core.formats.lmt.reader import read_lmt_bytes

        _reset_scene()
        target_armature = _import_live_mod3_armature(mod3_path)

        scene_props = bpy.context.scene.mhw_anim_tools
        scene_props.target_armature = target_armature
        inspect_result = bpy.ops.mhw_anim_tools.inspect_lmt("EXEC_DEFAULT", filepath=str(lmt_path))
        scene_props.selected_entry_index = int(args.get("entry-index", "0"))
        import_result = bpy.ops.mhw_anim_tools.import_selected_lmt_action("EXEC_DEFAULT")

        with tempfile.NamedTemporaryFile(suffix=".lmt", delete=False) as handle:
            output_path = Path(handle.name)
        export_result = bpy.ops.mhw_anim_tools.export_source_lmt("EXEC_DEFAULT", filepath=str(output_path))
        export_status = scene_props.last_status
        export_diagnostics = [
            {
                "level": item.level,
                "source": item.source,
                "message": item.message,
            }
            for item in scene_props.diagnostics
        ]

        source_bytes = lmt_path.read_bytes()
        output_bytes = output_path.read_bytes()
        source_lmt = read_lmt_bytes(source_bytes, source_name=str(lmt_path))
        output_lmt = read_lmt_bytes(output_bytes, source_name=str(output_path))

        selected_index = int(scene_props.selected_entry_index)
        sibling_mismatches = []
        for action_index, (source_action, output_action) in enumerate(zip(source_lmt.actions, output_lmt.actions)):
            if action_index == selected_index:
                continue
            if _sibling_header_signature(source_action) != _sibling_header_signature(output_action):
                sibling_mismatches.append(f"Header signature mismatch for sibling action index {action_index}.")
                continue
            source_decoded = decode_action_tracks(source_action, strict=True)
            output_decoded = decode_action_tracks(output_action, strict=True)
            for mismatch in _compare_decoded_actions(source_decoded, output_decoded):
                sibling_mismatches.append(f"Action {action_index}: {mismatch}")

        source_timl_payloads = _normalized_timl_payloads(source_lmt, source_bytes)
        output_timl_payloads = _normalized_timl_payloads(output_lmt, output_bytes)

        inspect_roundtrip = bpy.ops.mhw_anim_tools.inspect_lmt("EXEC_DEFAULT", filepath=str(output_path))
        scene_props.selected_entry_index = selected_index
        import_roundtrip = bpy.ops.mhw_anim_tools.import_selected_lmt_action("EXEC_DEFAULT")
        roundtrip_action = target_armature.animation_data.action if target_armature.animation_data else None

        payload = {
            "inspect_result": _operator_status(inspect_result),
            "import_result": _operator_status(import_result),
            "export_result": _operator_status(export_result),
            "export_status": export_status,
            "export_warning_count": scene_props.last_export_warning_count,
            "export_error_count": scene_props.last_export_error_count,
            "export_diagnostics": export_diagnostics[:50],
            "inspect_roundtrip": _operator_status(inspect_roundtrip),
            "import_roundtrip": _operator_status(import_roundtrip),
            "target_armature": target_armature.name,
            "source_entry_count": source_lmt.header.entry_count,
            "output_entry_count": output_lmt.header.entry_count,
            "source_action_count": len(source_lmt.actions),
            "output_action_count": len(output_lmt.actions),
            "source_action_ids": [int(action.id) for action in source_lmt.actions],
            "output_action_ids": [int(action.id) for action in output_lmt.actions],
            "source_timl_action_count": sum(1 for action in source_lmt.actions if action.header.timl_offset),
            "output_timl_action_count": sum(1 for action in output_lmt.actions if action.header.timl_offset),
            "source_timl_payload_count": len(source_timl_payloads),
            "output_timl_payload_count": len(output_timl_payloads),
            "source_timl_sharing_groups": _timl_sharing_groups(source_lmt),
            "output_timl_sharing_groups": _timl_sharing_groups(output_lmt),
            "timl_payloads_match": source_timl_payloads == output_timl_payloads,
            "selected_output_track_count": len(output_lmt.actions[selected_index].tracks),
            "sibling_mismatch_count": len(sibling_mismatches),
            "sibling_mismatches": sibling_mismatches[:20],
            "written_file": str(output_path),
            "written_size": output_path.stat().st_size,
            "roundtrip_action_name": roundtrip_action.name if roundtrip_action is not None else "",
            "roundtrip_fcurve_count": len(roundtrip_action.fcurves) if roundtrip_action is not None else 0,
        }
        print(json.dumps(payload, indent=2))

        if "FINISHED" not in inspect_result or "FINISHED" not in import_result:
            raise SystemExit("Initial source import path did not finish successfully before merge export.")
        if "FINISHED" not in export_result:
            raise SystemExit("Merge export operator did not finish successfully.")
        if "mode=merge" not in export_status:
            raise SystemExit(f"Expected merge export mode, got status: {export_status}")
        if source_lmt.header.entry_count != output_lmt.header.entry_count:
            raise SystemExit("Merged export changed the source entry count.")
        if len(source_lmt.actions) != len(output_lmt.actions):
            raise SystemExit("Merged export changed the source action count.")
        if [int(action.id) for action in source_lmt.actions] != [int(action.id) for action in output_lmt.actions]:
            raise SystemExit("Merged export changed the action id ordering.")
        if _timl_sharing_groups(source_lmt) != _timl_sharing_groups(output_lmt):
            raise SystemExit("Merged export changed TIML sharing groups.")
        if source_timl_payloads != output_timl_payloads:
            raise SystemExit("Merged export changed normalized raw TIML payloads.")
        if sibling_mismatches:
            raise SystemExit(f"Merged export changed {len(sibling_mismatches)} sibling action sample(s).")
        if "FINISHED" not in inspect_roundtrip or "FINISHED" not in import_roundtrip:
            raise SystemExit("Re-importing the merged output did not finish successfully.")
        if roundtrip_action is None or not roundtrip_action.fcurves:
            raise SystemExit("Merged output did not re-import into a usable Blender Action.")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
