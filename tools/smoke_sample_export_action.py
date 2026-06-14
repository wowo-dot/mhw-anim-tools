from __future__ import annotations

import addon_utils
import json
import sys
from pathlib import Path

import bpy


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


def _create_smoke_armature(name: str = "SmokeTarget"):
    armature_data = bpy.data.armatures.new(f"{name}Data")
    armature_object = bpy.data.objects.new(name, armature_data)
    bpy.context.scene.collection.objects.link(armature_object)
    bpy.context.view_layer.objects.active = armature_object
    armature_object.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature_data.edit_bones

    root = edit_bones.new("Root")
    root.head = (0.0, 0.0, 0.0)
    root.tail = (0.0, 0.0, 0.2)

    previous = root
    for index in range(4):
        bone = edit_bones.new(f"MhBone_{index:03d}")
        bone.head = (0.0, 0.0, 0.2 + (index * 0.2))
        bone.tail = (0.0, 0.0, 0.4 + (index * 0.2))
        bone.parent = previous
        previous = bone

    bpy.ops.object.mode_set(mode="OBJECT")
    return armature_object


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


def _supported_decoded_tracks(decoded_action):
    from mhw_anim_tools.core.formats.lmt.semantics import get_usage_semantics

    supported = []
    for track in decoded_action.tracks:
        usage = get_usage_semantics(track.usage)
        if usage.transform in {"rotation", "translation", "scale"} and usage.blender_path_hint and not track.decode_error:
            supported.append(track)
    return supported


def _expected_track_frames(decoded_track):
    from mhw_anim_tools.core.animation.transforms import canonicalize_quaternion_frames_wxyz
    from mhw_anim_tools.core.formats.lmt.semantics import get_usage_semantics

    usage = get_usage_semantics(decoded_track.usage)
    frames = [(0.0, tuple(decoded_track.basis_value))]
    frames.extend((float(sample.frame), tuple(sample.value)) for sample in decoded_track.keyframes)
    if decoded_track.tail_frame is not None and decoded_track.tail_value is not None:
        frames.append((float(decoded_track.tail_frame), tuple(decoded_track.tail_value)))
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


def _compare_sampled_tracks(sampled_result, decoded_action, tolerance=1e-3):
    from mhw_anim_tools.core.formats.lmt.semantics import get_usage_semantics

    sampled_map = {
        (track.bone_id, track.usage): {sample.frame: sample.value for sample in track.frames}
        for track in sampled_result.sampled_tracks
    }
    mismatches = []
    for decoded_track in _supported_decoded_tracks(decoded_action):
        key = (decoded_track.bone_id, decoded_track.usage)
        if key not in sampled_map:
            mismatches.append(f"Missing sampled track bone={decoded_track.bone_id} usage={decoded_track.usage}")
            continue
        expected_frames = _expected_track_frames(decoded_track)
        usage_info = get_usage_semantics(decoded_track.usage)
        for frame, expected in expected_frames.items():
            actual = sampled_map[key].get(frame)
            if actual is None:
                mismatches.append(f"Missing sampled frame {frame} for bone={decoded_track.bone_id} usage={decoded_track.usage}")
                continue
            values_match = (
                _quaternion_values_match(expected, actual, tolerance)
                if usage_info.is_quaternion
                else all(abs(actual_component - expected_component) <= tolerance for actual_component, expected_component in zip(actual, expected))
            )
            if not values_match:
                mismatches.append(
                    "Value mismatch for bone=%d usage=%d frame=%d expected=%s actual=%s"
                    % (decoded_track.bone_id, decoded_track.usage, frame, expected, actual)
                )
    return mismatches


def _compare_reconstructed_tracks(reconstructed_action, decoded_action, tolerance=1e-3):
    from mhw_anim_tools.core.animation.transforms import canonicalize_quaternion_frames_wxyz
    from mhw_anim_tools.core.formats.lmt.semantics import get_usage_semantics

    reconstructed_map = {
        (track.bone_id, track.usage): track
        for track in reconstructed_action.tracks
    }
    mismatches = []
    for decoded_track in _supported_decoded_tracks(decoded_action):
        key = (decoded_track.bone_id, decoded_track.usage)
        reconstructed = reconstructed_map.get(key)
        if reconstructed is None:
            mismatches.append(f"Missing reconstructed track bone={decoded_track.bone_id} usage={decoded_track.usage}")
            continue
        usage_info = get_usage_semantics(decoded_track.usage)
        if len(reconstructed.keyframes) != len(decoded_track.keyframes):
            mismatches.append(
                "Keyframe count mismatch for bone=%d usage=%d expected=%d actual=%d"
                % (decoded_track.bone_id, decoded_track.usage, len(decoded_track.keyframes), len(reconstructed.keyframes))
            )
            continue
        expected_frames = [(0.0, tuple(float(component) for component in decoded_track.basis_value))]
        expected_frames.extend((float(sample.frame), tuple(float(component) for component in sample.value)) for sample in decoded_track.keyframes)
        if decoded_track.tail_frame is not None and decoded_track.tail_value is not None:
            expected_frames.append((float(decoded_track.tail_frame), tuple(float(component) for component in decoded_track.tail_value)))
        if usage_info.is_quaternion:
            expected_frames = canonicalize_quaternion_frames_wxyz(expected_frames, normalize=True)

        expected_basis = expected_frames[0][1]
        expected_keyframes = expected_frames[1:]
        expected_tail_frame = decoded_track.tail_frame
        expected_tail_value = None if decoded_track.tail_value is None else tuple(float(component) for component in decoded_track.tail_value)
        if decoded_track.tail_frame is not None and decoded_track.tail_value is not None:
            expected_tail_frame = int(expected_frames[-1][0])
            expected_tail_value = expected_frames[-1][1]
            expected_keyframes = expected_frames[1:-1]

        basis_matches = (
            _quaternion_values_match(expected_basis, reconstructed.basis_value, tolerance)
            if usage_info.is_quaternion
            else all(abs(actual - expected) <= tolerance for actual, expected in zip(reconstructed.basis_value, expected_basis))
        )
        if not basis_matches:
            mismatches.append(
                "Basis mismatch for bone=%d usage=%d expected=%s actual=%s"
                % (decoded_track.bone_id, decoded_track.usage, expected_basis, reconstructed.basis_value)
            )
        for (expected_frame, expected_value), actual_key in zip(expected_keyframes, reconstructed.keyframes):
            if int(expected_frame) != int(actual_key.frame):
                mismatches.append(
                    "Keyframe timing mismatch for bone=%d usage=%d expected=%d actual=%d"
                    % (decoded_track.bone_id, decoded_track.usage, expected_frame, actual_key.frame)
                )
                continue
            values_match = (
                _quaternion_values_match(expected_value, actual_key.value, tolerance)
                if usage_info.is_quaternion
                else all(abs(actual - expected) <= tolerance for actual, expected in zip(actual_key.value, expected_value))
            )
            if not values_match:
                mismatches.append(
                    "Keyframe value mismatch for bone=%d usage=%d frame=%d expected=%s actual=%s"
                    % (decoded_track.bone_id, decoded_track.usage, expected_frame, expected_value, actual_key.value)
                )
        actual_tail_frame = reconstructed.tail_frame
        if expected_tail_frame != actual_tail_frame:
            mismatches.append(
                "Tail timing mismatch for bone=%d usage=%d expected=%s actual=%s"
                % (decoded_track.bone_id, decoded_track.usage, expected_tail_frame, actual_tail_frame)
            )
        actual_tail_value = reconstructed.tail_value
        if expected_tail_value is None and actual_tail_value is not None:
            mismatches.append(
                "Unexpected tail for bone=%d usage=%d actual=%s"
                % (decoded_track.bone_id, decoded_track.usage, actual_tail_value)
            )
        elif expected_tail_value is not None and actual_tail_value is None:
            mismatches.append(
                "Missing tail for bone=%d usage=%d expected=%s"
                % (decoded_track.bone_id, decoded_track.usage, expected_tail_value)
            )
        elif expected_tail_value is not None and actual_tail_value is not None:
            values_match = (
                _quaternion_values_match(expected_tail_value, actual_tail_value, tolerance)
                if usage_info.is_quaternion
                else all(abs(actual - expected) <= tolerance for actual, expected in zip(actual_tail_value, expected_tail_value))
            )
            if not values_match:
                mismatches.append(
                    "Tail value mismatch for bone=%d usage=%d expected=%s actual=%s"
                    % (decoded_track.bone_id, decoded_track.usage, expected_tail_value, actual_tail_value)
                )
    return mismatches


def _operator_status(result) -> str:
    if isinstance(result, set):
        return ",".join(sorted(result))
    return str(result)


def _track_metadata_map(source_action) -> dict[tuple[int, int], dict[str, float | int]]:
    return {
        (track.header.bone_id, track.header.usage): {
            "buffer_type": track.header.buffer_type,
            "joint_type": track.header.joint_type,
            "unknown_tag": track.header.unknown_tag,
            "weight": track.header.weight,
            "lerp_mult": track.lerp_basis.mult if track.lerp_basis is not None else None,
            "lerp_add": track.lerp_basis.add if track.lerp_basis is not None else None,
        }
        for track in source_action.tracks
    }


def main():
    args = _parse_cli_args()
    lmt_path = Path(args.get("lmt", ""))
    mod3_path = Path(args.get("mod3", ""))
    if not lmt_path.is_file():
        raise SystemExit("Provide --lmt <path-to-lmt> for the smoke test.")

    repo_root = Path(__file__).resolve().parents[1]
    addon = _register_addon(repo_root)
    try:
        from mhw_anim_tools.blender_adapter.export_sampling import sample_action_for_lmt_export
        from mhw_anim_tools.core.formats.lmt.decoder import decode_action_tracks
        from mhw_anim_tools.core.formats.lmt.export_plan import plan_reconstructed_action_export
        from mhw_anim_tools.core.formats.lmt.quaternion_source_diagnostics import identify_raw_sensitive_quaternion_identities
        from mhw_anim_tools.core.formats.lmt.reader import read_lmt_file
        from mhw_anim_tools.core.formats.lmt.reconstruction import reconstruct_sampled_action

        _reset_scene()
        if mod3_path.is_file():
            target_armature = _import_live_mod3_armature(mod3_path)
        else:
            target_armature = _create_smoke_armature()

        scene_props = bpy.context.scene.mhw_anim_tools
        scene_props.target_armature = target_armature
        inspect_result = bpy.ops.mhw_anim_tools.inspect_lmt(
            "EXEC_DEFAULT",
            filepath=str(lmt_path),
        )
        scene_props.selected_entry_index = int(args.get("entry-index", "0"))
        import_result = bpy.ops.mhw_anim_tools.import_selected_lmt_action("EXEC_DEFAULT")

        action = target_armature.animation_data.action if target_armature.animation_data else None
        if action is None:
            raise SystemExit("No Blender Action was assigned before export sampling.")

        sampled_result = sample_action_for_lmt_export(action, target_armature)
        lmt = read_lmt_file(lmt_path)
        source_action = lmt.actions[scene_props.selected_entry_index]
        decoded_action = decode_action_tracks(source_action, strict=False)
        raw_quaternion_source_identities = identify_raw_sensitive_quaternion_identities(decoded_action)
        source_track_metadata = _track_metadata_map(source_action)
        reconstructed_action = reconstruct_sampled_action(
            action_name=sampled_result.action_name,
            frame_start=sampled_result.frame_start,
            frame_end=sampled_result.frame_end,
            sampled_tracks=sampled_result.sampled_tracks,
            raw_quaternion_source_identities=raw_quaternion_source_identities,
        )
        export_plan = plan_reconstructed_action_export(
            reconstructed_action,
            track_metadata_by_identity=source_track_metadata,
            raw_quaternion_source_identities=raw_quaternion_source_identities,
        )
        mismatches = _compare_sampled_tracks(sampled_result, decoded_action)
        sparse_mismatches = _compare_reconstructed_tracks(reconstructed_action, decoded_action)

        payload = {
            "inspect_result": _operator_status(inspect_result),
            "import_result": _operator_status(import_result),
            "target_armature": target_armature.name,
            "action_name": action.name,
            "sampled_track_count": sampled_result.sampled_track_count,
            "skipped_track_count": sampled_result.skipped_track_count,
            "warning_count": sampled_result.warning_count,
            "error_count": sampled_result.error_count,
            "frame_end": sampled_result.frame_end,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches[:20],
            "reconstructed_track_count": reconstructed_action.track_count,
            "reconstructed_sparse_key_count": reconstructed_action.sparse_key_count,
            "sparse_mismatch_count": len(sparse_mismatches),
            "sparse_mismatches": sparse_mismatches[:20],
            "planned_track_count": export_plan.track_count,
            "planned_supported_track_count": export_plan.supported_track_count,
            "planned_buffer_breakdown": export_plan.buffer_breakdown,
            "plan_warning_count": export_plan.warning_count,
            "plan_error_count": export_plan.error_count,
            "plan_diagnostics": [
                {
                    "level": item.level,
                    "source": item.source,
                    "message": item.message,
                }
                for item in export_plan.diagnostics
            ][:20],
            "diagnostics": [
                {
                    "level": item.level,
                    "source": item.source,
                    "message": item.message,
                }
                for item in sampled_result.diagnostics
            ],
        }
        print(json.dumps(payload, indent=2))

        if "FINISHED" not in inspect_result or "FINISHED" not in import_result:
            raise SystemExit("Import path did not finish successfully before export sampling.")
        if sampled_result.error_count:
            raise SystemExit("Export sampling reported errors.")
        if mismatches:
            raise SystemExit(f"Export sampling mismatched {len(mismatches)} decoded track sample(s).")
        if export_plan.error_count:
            raise SystemExit(f"Export planning reported {export_plan.error_count} error(s).")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
