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


def _apply_structural_linear_edit(controller, action):
    bindings = _load_timl_bindings(controller)
    for binding in bindings:
        property_name = str(binding.get("property_name", ""))
        fcurve = _first_matching_fcurve(action, property_name=property_name, array_index=0)
        if fcurve is None or not fcurve.keyframe_points:
            continue
        first = fcurve.keyframe_points[0]
        first_frame = float(first.co[0])
        first_value = float(first.co[1])
        insert_frame = first_frame + 12.0
        insert_value = first_value + 1.0
        inserted = fcurve.keyframe_points.insert(insert_frame, insert_value, options={"FAST"})
        inserted.interpolation = "LINEAR"
        for point in fcurve.keyframe_points:
            point.interpolation = "LINEAR"
        fcurve.update()
        return {
            "binding": binding,
            "insert_frame": insert_frame,
            "insert_value": insert_value,
        }
    raise SystemExit("Could not find a TIML controller fcurve to apply a structural edit.")


def main():
    args = _parse_cli_args()
    lmt_path = Path(args.get("lmt", ""))
    mod3_path = Path(args.get("mod3", ""))
    if not lmt_path.is_file():
        raise SystemExit("Provide --lmt <path-to-lmt> for the structural TIML merge-export smoke test.")
    if not mod3_path.is_file():
        raise SystemExit("Provide --mod3 <path-to-mod3> for the structural TIML merge-export smoke test.")

    repo_root = Path(__file__).resolve().parents[1]
    addon = _register_addon(repo_root)
    try:
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
        edit_info = _apply_structural_linear_edit(controller, timl_action)

        lmt_action = bpy.data.actions.get(scene_props.last_imported_action_name)
        if lmt_action is None:
            raise SystemExit("LMT skeletal action was not imported.")
        scene_props.export_action = lmt_action

        with tempfile.NamedTemporaryFile(suffix=".lmt", delete=False) as handle:
            output_path = Path(handle.name)
        export_result = bpy.ops.mhw_anim_tools.export_lmt_action("EXEC_DEFAULT", filepath=str(output_path))

        payload = {
            "inspect_result": _operator_status(inspect_result),
            "import_lmt_result": _operator_status(import_lmt_result),
            "import_timl_result": _operator_status(import_timl_result),
            "export_result": _operator_status(export_result),
            "status": scene_props.last_status,
            "edit_info": edit_info,
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
        if "CANCELLED" not in export_result:
            raise SystemExit("Advanced-source structural TIML merge export should have been rejected cleanly.")
        messages = "\n".join(item["message"] for item in payload["diagnostics"])
        if "Structural rebuild is blocked" not in messages:
            raise SystemExit("Expected a clear advanced-source structural rebuild diagnostic.")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
