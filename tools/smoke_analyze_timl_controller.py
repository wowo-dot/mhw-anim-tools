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
        bpy.data.objects,
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
    for index in range(2):
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


def _operator_status(result) -> str:
    if isinstance(result, set):
        return ",".join(sorted(result))
    return str(result)


def main():
    args = _parse_cli_args()
    lmt_path = Path(args.get("lmt", ""))
    mod3_path = Path(args.get("mod3", ""))
    if not lmt_path.is_file():
        raise SystemExit("Provide --lmt <path-to-lmt> for the TIML controller smoke test.")

    repo_root = Path(__file__).resolve().parents[1]
    addon = _register_addon(repo_root)
    try:
        _reset_scene()
        if mod3_path.is_file():
            target_armature = _import_live_mod3_armature(mod3_path)
        else:
            target_armature = _create_smoke_armature()

        scene_props = bpy.context.scene.mhw_anim_tools
        scene_props.target_armature = target_armature

        inspect_result = bpy.ops.mhw_anim_tools.inspect_lmt("EXEC_DEFAULT", filepath=str(lmt_path))
        scene_props.selected_entry_index = int(args.get("entry-index", "0"))
        import_result = bpy.ops.mhw_anim_tools.import_selected_attached_timl("EXEC_DEFAULT")
        analyze_result = bpy.ops.mhw_anim_tools.analyze_timl_controller("EXEC_DEFAULT")

        controller = scene_props.timl_controller
        action = controller.animation_data.action if controller and controller.animation_data else None
        payload = {
            "inspect_result": _operator_status(inspect_result),
            "import_result": _operator_status(import_result),
            "analyze_result": _operator_status(analyze_result),
            "status": scene_props.last_status,
            "controller_name": controller.name if controller else "",
            "action_name": action.name if action else "",
            "transform_count": scene_props.last_timl_analysis_transform_count,
            "keyframe_count": scene_props.last_timl_analysis_keyframe_count,
            "frame_end": scene_props.last_timl_analysis_frame_end,
            "warning_count": scene_props.last_timl_analysis_warning_count,
            "error_count": scene_props.last_timl_analysis_error_count,
            "writeback_available": bool(scene_props.last_timl_writeback_available),
            "writeback_preserve_raw_count": int(scene_props.last_timl_writeback_preserve_raw_count),
            "writeback_patch_values_count": int(scene_props.last_timl_writeback_patch_values_count),
            "writeback_rebuild_count": int(scene_props.last_timl_writeback_rebuild_count),
            "writeback_blocked_count": int(scene_props.last_timl_writeback_blocked_count),
            "edit_policy_value_only_count": int(scene_props.last_timl_edit_value_only_count),
            "edit_policy_rebuild_capable_count": int(scene_props.last_timl_edit_rebuild_capable_count),
            "edit_policy_blocked_count": int(scene_props.last_timl_edit_blocked_count),
            "payload_scope": str(scene_props.last_timl_payload_scope),
            "controller_transform_items": len(scene_props.timl_controller_transforms),
            "diagnostics": [
                {
                    "level": item.level,
                    "source": item.source,
                    "message": item.message,
                }
                for item in scene_props.diagnostics
            ],
        }
        print(json.dumps(payload, indent=2))

        if "FINISHED" not in inspect_result:
            raise SystemExit("Inspect operator did not finish successfully.")
        if "FINISHED" not in import_result:
            raise SystemExit("TIML import operator did not finish successfully.")
        if "FINISHED" not in analyze_result:
            raise SystemExit("TIML analyze operator did not finish successfully.")
        if controller is None:
            raise SystemExit("TIML analysis did not resolve a controller object.")
        if action is None:
            raise SystemExit("TIML analysis did not find an active controller action.")
        if scene_props.last_timl_analysis_transform_count <= 0:
            raise SystemExit("TIML analysis did not sample any controller transforms.")
        if len(scene_props.timl_controller_transforms) <= 0:
            raise SystemExit("TIML analysis did not populate controller inspector transform items.")
        if scene_props.last_timl_writeback_available:
            summarized = (
                int(scene_props.last_timl_writeback_preserve_raw_count)
                + int(scene_props.last_timl_writeback_patch_values_count)
                + int(scene_props.last_timl_writeback_rebuild_count)
                + int(scene_props.last_timl_writeback_blocked_count)
            )
            if summarized != len(scene_props.timl_controller_transforms):
                raise SystemExit("TIML writeback summary counts do not match inspector transform items.")
            policy_summarized = (
                int(scene_props.last_timl_edit_value_only_count)
                + int(scene_props.last_timl_edit_rebuild_capable_count)
                + int(scene_props.last_timl_edit_blocked_count)
            )
            if policy_summarized != len(scene_props.timl_controller_transforms):
                raise SystemExit("TIML edit policy counts do not match inspector transform items.")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
