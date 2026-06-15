from __future__ import annotations

import addon_utils
import json
import sys
import tempfile
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


def _load_timl_bindings(controller):
    raw_value = controller.get("mhw_anim_tools_timl_bindings", "")
    if not isinstance(raw_value, str) or not raw_value:
        return []
    return json.loads(raw_value)


def _first_matching_fcurve(action, *, property_name: str, array_index: int):
    target_path = f'["{property_name}"]'
    for fcurve in action.fcurves:
        if fcurve.data_path == target_path and int(fcurve.array_index) == int(array_index):
            return fcurve
    return None


def _first_key_value(fcurve):
    if not fcurve.keyframe_points:
        raise SystemExit("Selected TIML controller fcurve has no keyframes.")
    return float(fcurve.keyframe_points[0].co[1])


def _tweak_timl_controller_value(controller, action):
    bindings = _load_timl_bindings(controller)
    for binding in bindings:
        data_type = int(binding.get("data_type", 0))
        property_name = str(binding.get("property_name", ""))
        fcurve = _first_matching_fcurve(action, property_name=property_name, array_index=0)
        if fcurve is None:
            continue
        before = _first_key_value(fcurve)
        after = before
        expected_native_value = None
        if data_type == 2:
            after = before + 5.0
            expected_native_value = after
        elif data_type == 0:
            after = round(before) + 2.0
            expected_native_value = int(round(after))
        elif data_type == 1:
            after = round(before) + 2.0
            expected_native_value = int(round(after))
        elif data_type == 4:
            after = 0.0 if before >= 0.5 else 1.0
            expected_native_value = int(round(after))
        elif data_type == 3:
            after = min(1.0, before + (32.0 / 255.0))
            expected_native_value = int(round(after * 255.0))
        else:
            continue
        fcurve.keyframe_points[0].co = (float(fcurve.keyframe_points[0].co[0]), float(after))
        fcurve.update()
        return {
            "binding": binding,
            "before_preview_value": before,
            "after_preview_value": after,
            "expected_native_value": expected_native_value,
        }
    raise SystemExit("Could not find a writable TIML controller fcurve to edit.")


def _timl_transform_snapshots(blob: bytes, *, timl_offset: int, entry_id: int):
    from mhw_anim_tools.core.formats.timl.reader import read_timl_data_bytes

    entry = read_timl_data_bytes(
        blob,
        data_offset=timl_offset,
        source_name="timl-smoke#timl",
        entry_id=entry_id,
    )
    snapshots = {}
    for type_index, type_entry in enumerate(entry.types):
        for transform_index, transform in enumerate(type_entry.transforms):
            snapshots[(int(type_index), int(transform_index))] = tuple(
                (
                    keyframe.value,
                    keyframe.control_left,
                    keyframe.control_right,
                    float(keyframe.frame_timing),
                    int(keyframe.interpolation),
                    int(keyframe.easing),
                )
                for keyframe in transform.keyframes
            )
    return snapshots


def _lmt_action_map_by_id(lmt):
    mapping = {}
    for action in lmt.actions:
        mapping[int(action.id)] = action
    return mapping


def _shared_action_ids_for_offset(lmt, source_offset: int) -> tuple[int, ...]:
    return tuple(
        int(action.id)
        for action in lmt.actions
        if int(action.header.timl_offset) == int(source_offset)
    )


def _first_other_timl_action_id(lmt, *, excluded_offset: int) -> int:
    for action in lmt.actions:
        offset = int(action.header.timl_offset)
        if offset > 0 and offset != int(excluded_offset):
            return int(action.id)
    return -1


def main():
    args = _parse_cli_args()
    lmt_path = Path(args.get("lmt", ""))
    mod3_path = Path(args.get("mod3", ""))
    if not lmt_path.is_file():
        raise SystemExit("Provide --lmt <path-to-lmt> for the shared TIML merge-export smoke test.")
    if not mod3_path.is_file():
        raise SystemExit("Provide --mod3 <path-to-mod3> for the shared TIML merge-export smoke test.")

    repo_root = Path(__file__).resolve().parents[1]
    addon = _register_addon(repo_root)
    try:
        from mhw_anim_tools.core.formats.lmt.reader import read_lmt_bytes

        _reset_scene()
        target_armature = _import_live_mod3_armature(mod3_path)

        scene_props = bpy.context.scene.mhw_anim_tools
        scene_props.target_armature = target_armature
        inspect_result = bpy.ops.mhw_anim_tools.inspect_lmt("EXEC_DEFAULT", filepath=str(lmt_path))
        scene_props.selected_entry_index = int(args.get("entry-index", "0"))
        import_lmt_result = bpy.ops.mhw_anim_tools.import_selected_lmt_action("EXEC_DEFAULT")
        import_timl_result = bpy.ops.mhw_anim_tools.import_selected_attached_timl("EXEC_DEFAULT")
        analyze_result = bpy.ops.mhw_anim_tools.analyze_timl_controller("EXEC_DEFAULT")

        controller = scene_props.timl_controller
        if controller is None or controller.animation_data is None or controller.animation_data.action is None:
            raise SystemExit("TIML import did not create a usable controller action.")
        timl_action = controller.animation_data.action
        edit_info = _tweak_timl_controller_value(controller, timl_action)

        lmt_action = bpy.data.actions.get(scene_props.last_imported_action_name)
        if lmt_action is None:
            raise SystemExit("LMT skeletal action was not imported.")
        scene_props.export_action = lmt_action

        with tempfile.NamedTemporaryFile(suffix=".lmt", delete=False) as handle:
            output_path = Path(handle.name)
        export_result = bpy.ops.mhw_anim_tools.export_lmt_action("EXEC_DEFAULT", filepath=str(output_path))

        source_bytes = lmt_path.read_bytes()
        output_bytes = output_path.read_bytes()
        source_lmt = read_lmt_bytes(source_bytes, source_name=str(lmt_path))
        output_lmt = read_lmt_bytes(output_bytes, source_name=str(output_path))
        selected_entry = int(scene_props.selected_entry_index)
        source_action = source_lmt.actions[selected_entry]
        source_action_map = _lmt_action_map_by_id(source_lmt)
        output_action_map = _lmt_action_map_by_id(output_lmt)
        source_offset = int(source_action.header.timl_offset)
        shared_action_ids = _shared_action_ids_for_offset(source_lmt, source_offset)
        if len(shared_action_ids) <= 1:
            raise SystemExit("Selected source action does not belong to a shared TIML payload group.")

        binding = edit_info["binding"]
        edited_identity = (int(binding["type_index"]), int(binding["transform_index"]))
        source_reference_snapshots = _timl_transform_snapshots(
            source_bytes,
            timl_offset=source_offset,
            entry_id=int(source_action.id),
        )

        output_shared_offsets = {}
        output_shared_snapshots = {}
        output_shared_values = {}
        for action_id in shared_action_ids:
            output_action = output_action_map.get(int(action_id))
            if output_action is None:
                raise SystemExit(f"Output LMT is missing shared source action id {action_id}.")
            output_offset = int(output_action.header.timl_offset)
            output_shared_offsets[int(action_id)] = output_offset
            output_snapshot = _timl_transform_snapshots(
                output_bytes,
                timl_offset=output_offset,
                entry_id=int(output_action.id),
            )
            output_shared_snapshots[int(action_id)] = output_snapshot
            output_shared_values[int(action_id)] = output_snapshot[edited_identity][0][0]

        reference_output_snapshot = output_shared_snapshots[int(shared_action_ids[0])]
        shared_snapshot_mismatches = [
            int(action_id)
            for action_id, snapshot in sorted(output_shared_snapshots.items())
            if snapshot != reference_output_snapshot
        ]
        untouched_mismatches = [
            f"{type_index:02d}:{transform_index:02d}"
            for (type_index, transform_index), source_snapshot in sorted(source_reference_snapshots.items())
            if (type_index, transform_index) != edited_identity
            and reference_output_snapshot.get((type_index, transform_index)) != source_snapshot
        ]

        other_action_id = _first_other_timl_action_id(source_lmt, excluded_offset=source_offset)
        other_payload_preserved = None
        if other_action_id >= 0:
            other_source_action = source_action_map[int(other_action_id)]
            other_output_action = output_action_map[int(other_action_id)]
            other_source_snapshots = _timl_transform_snapshots(
                source_bytes,
                timl_offset=int(other_source_action.header.timl_offset),
                entry_id=int(other_source_action.id),
            )
            other_output_snapshots = _timl_transform_snapshots(
                output_bytes,
                timl_offset=int(other_output_action.header.timl_offset),
                entry_id=int(other_output_action.id),
            )
            other_payload_preserved = other_source_snapshots == other_output_snapshots

        payload = {
            "inspect_result": _operator_status(inspect_result),
            "import_lmt_result": _operator_status(import_lmt_result),
            "import_timl_result": _operator_status(import_timl_result),
            "analyze_result": _operator_status(analyze_result),
            "export_result": _operator_status(export_result),
            "status": scene_props.last_status,
            "payload_scope": str(scene_props.last_timl_payload_scope),
            "shared_action_ids": [int(action_id) for action_id in shared_action_ids],
            "output_shared_offsets": output_shared_offsets,
            "output_shared_values": output_shared_values,
            "shared_snapshot_mismatches": shared_snapshot_mismatches,
            "untouched_mismatch_count": len(untouched_mismatches),
            "untouched_mismatches": untouched_mismatches,
            "other_action_id": int(other_action_id),
            "other_payload_preserved": other_payload_preserved,
            "binding": binding,
            "before_preview_value": edit_info["before_preview_value"],
            "after_preview_value": edit_info["after_preview_value"],
            "expected_native_value": edit_info["expected_native_value"],
            "diagnostics": [
                {
                    "level": item.level,
                    "source": item.source,
                    "message": item.message,
                }
                for item in scene_props.diagnostics
            ],
            "written_file": str(output_path),
        }
        print(json.dumps(payload, indent=2))

        if "FINISHED" not in inspect_result or "FINISHED" not in import_lmt_result or "FINISHED" not in import_timl_result:
            raise SystemExit("Source import path did not finish successfully before shared TIML merge export.")
        if "FINISHED" not in analyze_result:
            raise SystemExit("TIML analysis did not finish successfully before shared TIML edit.")
        if "FINISHED" not in export_result:
            raise SystemExit("Merge export with shared TIML edit did not finish successfully.")
        if len(set(int(offset) for offset in output_shared_offsets.values())) != 1:
            raise SystemExit("Shared output actions no longer point at the same embedded TIML payload offset.")
        if any(int(offset) <= 0 for offset in output_shared_offsets.values()):
            raise SystemExit("One or more shared output actions lost their embedded TIML payload offset.")
        if shared_snapshot_mismatches:
            raise SystemExit(
                "Shared output actions do not decode to the same edited TIML payload: "
                + ", ".join(f"{action_id:03d}" for action_id in shared_snapshot_mismatches)
            )
        expected = edit_info["expected_native_value"]
        actual_values = {int(action_id): value for action_id, value in output_shared_values.items()}
        if any(abs(float(value) - float(expected)) > 1e-4 for value in actual_values.values()):
            raise SystemExit(f"Shared output actions do not all carry the expected edited TIML value {expected}.")
        if untouched_mismatches:
            raise SystemExit(f"Untouched transforms in the shared payload changed unexpectedly: {', '.join(untouched_mismatches)}")
        if other_action_id >= 0 and not other_payload_preserved:
            raise SystemExit(f"Non-shared TIML action {other_action_id:03d} changed unexpectedly during shared-payload export.")
        if "Shared by source actions" not in str(scene_props.last_timl_payload_scope):
            raise SystemExit("TIML analysis did not surface the shared payload scope summary.")
        messages = "\n".join(item["message"] for item in payload["diagnostics"])
        if "shared by source actions" not in messages.lower():
            raise SystemExit("Expected a shared-payload writeback diagnostic during export.")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
