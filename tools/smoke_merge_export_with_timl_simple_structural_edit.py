from __future__ import annotations

import addon_utils
import json
import sys
import tempfile
from pathlib import Path

import bpy


SCALAR_TIML_DATA_TYPES = {0, 1, 2, 4}


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


def _binding_map_by_identity(controller) -> dict[tuple[int, int], dict[str, object]]:
    return {
        (int(binding.get("type_index", 0)), int(binding.get("transform_index", 0))): binding
        for binding in _load_timl_bindings(controller)
    }


def _first_matching_fcurve(action, *, property_name: str, array_index: int):
    target_path = f'["{property_name}"]'
    for fcurve in action.fcurves:
        if fcurve.data_path == target_path and int(fcurve.array_index) == int(array_index):
            return fcurve
    return None


def _choose_rebuild_candidate(scene_props, controller):
    binding_map = _binding_map_by_identity(controller)
    preferred: list[tuple[int, object, dict[str, object]]] = []
    fallback: list[tuple[int, object, dict[str, object]]] = []
    for item in scene_props.timl_controller_transforms:
        if str(item.edit_policy_code) != "rebuild_capable" or bool(item.source_advanced):
            continue
        identity = (int(item.type_index), int(item.transform_index))
        binding = binding_map.get(identity)
        if binding is None:
            continue
        data_type = int(binding.get("data_type", -1))
        sort_key = (int(item.type_index) * 1000) + int(item.transform_index)
        entry = (sort_key, item, binding)
        if data_type in SCALAR_TIML_DATA_TYPES:
            preferred.append(entry)
        else:
            fallback.append(entry)
    for candidates in (preferred, fallback):
        if candidates:
            _sort_key, item, binding = sorted(candidates, key=lambda value: value[0])[0]
            return item, binding
    return None, None


def _apply_structural_linear_edit(scene_props, controller, action):
    analyze_result = bpy.ops.mhw_anim_tools.analyze_timl_controller("EXEC_DEFAULT")
    if "FINISHED" not in analyze_result:
        raise SystemExit("TIML analysis did not finish before the structural edit smoke step.")

    transform_item, binding = _choose_rebuild_candidate(scene_props, controller)
    if transform_item is None or binding is None:
        raise SystemExit("Could not find a simple-source TIML transform classified as rebuild_capable.")

    property_name = str(binding.get("property_name", "") or transform_item.property_name)
    data_type = int(binding.get("data_type", -1))
    if data_type not in SCALAR_TIML_DATA_TYPES:
        raise SystemExit(
            f"Selected rebuild candidate {transform_item.type_index:02d}:{transform_item.transform_index:02d} "
            f"uses unsupported smoke-test data type {data_type}."
        )

    fcurve = _first_matching_fcurve(action, property_name=property_name, array_index=0)
    if fcurve is None or not fcurve.keyframe_points:
        raise SystemExit(f"Could not find a writable TIML controller fcurve for '{property_name}'.")

    frames = [float(point.co[0]) for point in fcurve.keyframe_points]
    last_value = float(fcurve.keyframe_points[-1].co[1])
    insert_frame = max(frames) + 5.0
    while any(abs(insert_frame - frame) <= 1e-6 for frame in frames):
        insert_frame += 1.0
    if data_type == 4:
        insert_value = 0.0 if last_value >= 0.5 else 1.0
    elif data_type in {0, 1}:
        insert_value = round(last_value) + 1.0
    else:
        insert_value = last_value + 1.0

    inserted = fcurve.keyframe_points.insert(insert_frame, insert_value, options={"FAST"})
    inserted.interpolation = "LINEAR"
    for point in fcurve.keyframe_points:
        point.interpolation = "LINEAR"
    fcurve.update()

    return analyze_result, {
        "type_index": int(transform_item.type_index),
        "transform_index": int(transform_item.transform_index),
        "property_name": property_name,
        "data_type": data_type,
        "insert_frame": float(insert_frame),
        "insert_value": float(insert_value),
        "source_advanced": bool(transform_item.source_advanced),
        "edit_policy_code": str(transform_item.edit_policy_code),
        "writeback_status_code": str(transform_item.writeback_status_code),
    }


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


def main():
    args = _parse_cli_args()
    lmt_path = Path(args.get("lmt", ""))
    mod3_path = Path(args.get("mod3", ""))
    if not lmt_path.is_file():
        raise SystemExit("Provide --lmt <path-to-lmt> for the simple structural TIML merge-export smoke test.")
    if not mod3_path.is_file():
        raise SystemExit("Provide --mod3 <path-to-mod3> for the simple structural TIML merge-export smoke test.")

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

        controller = scene_props.timl_controller
        if controller is None or controller.animation_data is None or controller.animation_data.action is None:
            raise SystemExit("TIML import did not create a usable controller action.")
        timl_action = controller.animation_data.action

        analyze_result, edit_info = _apply_structural_linear_edit(scene_props, controller, timl_action)

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
        output_action = output_lmt.actions[selected_entry]

        source_snapshots = _timl_transform_snapshots(
            source_bytes,
            timl_offset=int(source_action.header.timl_offset),
            entry_id=int(source_action.id),
        )
        output_snapshots = _timl_transform_snapshots(
            output_bytes,
            timl_offset=int(output_action.header.timl_offset),
            entry_id=int(output_action.id),
        )
        edited_identity = (int(edit_info["type_index"]), int(edit_info["transform_index"]))
        edited_source_snapshot = source_snapshots.get(edited_identity, ())
        edited_output_snapshot = output_snapshots.get(edited_identity, ())
        untouched_mismatches = [
            f"{type_index:02d}:{transform_index:02d}"
            for (type_index, transform_index), source_snapshot in sorted(source_snapshots.items())
            if (type_index, transform_index) != edited_identity and output_snapshots.get((type_index, transform_index)) != source_snapshot
        ]
        output_frames = [keyframe[3] for keyframe in edited_output_snapshot]
        output_interpolations = [keyframe[4] for keyframe in edited_output_snapshot]
        output_easing = [keyframe[5] for keyframe in edited_output_snapshot]

        payload = {
            "inspect_result": _operator_status(inspect_result),
            "import_lmt_result": _operator_status(import_lmt_result),
            "import_timl_result": _operator_status(import_timl_result),
            "analyze_result": _operator_status(analyze_result),
            "export_result": _operator_status(export_result),
            "status": scene_props.last_status,
            "edit_info": edit_info,
            "edited_source_key_count": len(edited_source_snapshot),
            "edited_output_key_count": len(edited_output_snapshot),
            "output_frames": output_frames,
            "output_interpolations": output_interpolations,
            "output_easing": output_easing,
            "untouched_mismatch_count": len(untouched_mismatches),
            "untouched_mismatches": untouched_mismatches,
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
            raise SystemExit("Source import path did not finish successfully before structural TIML merge export.")
        if "FINISHED" not in analyze_result:
            raise SystemExit("TIML analysis did not finish successfully before structural TIML edit.")
        if "FINISHED" not in export_result:
            raise SystemExit("Merge export with simple structural TIML edit did not finish successfully.")
        if int(source_action.header.timl_offset) == 0 or int(output_action.header.timl_offset) == 0:
            raise SystemExit("Expected both source and output actions to keep attached TIML payloads.")
        if len(edited_output_snapshot) != len(edited_source_snapshot) + 1:
            raise SystemExit(
                "Edited TIML transform did not rebuild with one additional keyframe "
                f"(source={len(edited_source_snapshot)}, output={len(edited_output_snapshot)})."
            )
        if not any(abs(float(frame) - float(edit_info["insert_frame"])) <= 1e-6 for frame in output_frames):
            raise SystemExit("Edited TIML transform is missing the inserted structural keyframe in the exported payload.")
        if any(int(code) != 1 for code in output_interpolations):
            raise SystemExit("Edited TIML transform did not rebuild with linear interpolation as authored in Blender.")
        if any(int(code) != 0 for code in output_easing):
            raise SystemExit("Edited TIML transform rebuild unexpectedly introduced nonzero easing codes.")
        if untouched_mismatches:
            raise SystemExit(f"Untouched TIML transforms changed unexpectedly: {', '.join(untouched_mismatches)}")
        messages = "\n".join(item["message"] for item in payload["diagnostics"])
        if "will be rebuilt from the current Blender keys" not in messages:
            raise SystemExit("Expected a clear rebuild-preview TIML diagnostic during export.")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
