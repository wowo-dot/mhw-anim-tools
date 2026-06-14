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


def _collect_diagnostics(scene_props):
    return [
        {
            "level": item.level,
            "source": item.source,
            "message": item.message,
        }
        for item in scene_props.diagnostics
    ]


def main():
    args = _parse_cli_args()
    lmt_path = Path(args.get("lmt", ""))
    mod3_path = Path(args.get("mod3", ""))
    if not lmt_path.is_file():
        raise SystemExit("Provide --lmt <path-to-lmt> for the TIML export-readiness smoke test.")
    if not mod3_path.is_file():
        raise SystemExit("Provide --mod3 <path-to-mod3> for the TIML export-readiness smoke test.")

    repo_root = Path(__file__).resolve().parents[1]
    addon = _register_addon(repo_root)
    try:
        _reset_scene()
        target_armature = _import_live_mod3_armature(mod3_path)
        scene_props = bpy.context.scene.mhw_anim_tools
        scene_props.target_armature = target_armature

        inspect_result = bpy.ops.mhw_anim_tools.inspect_lmt("EXEC_DEFAULT", filepath=str(lmt_path))
        import_lmt_result = bpy.ops.mhw_anim_tools.import_selected_lmt_action("EXEC_DEFAULT")
        lmt_action_name = scene_props.last_imported_action_name
        lmt_action = bpy.data.actions.get(lmt_action_name)

        import_timl_result = bpy.ops.mhw_anim_tools.import_selected_attached_timl("EXEC_DEFAULT")
        timl_action_name = scene_props.last_imported_timl_action_name
        timl_action = bpy.data.actions.get(timl_action_name)

        scene_props.export_action = lmt_action
        analyze_lmt_result = bpy.ops.mhw_anim_tools.analyze_export_action("EXEC_DEFAULT")
        lmt_status = scene_props.last_status
        lmt_diagnostics = _collect_diagnostics(scene_props)

        scene_props.export_action = timl_action
        analyze_timl_result = bpy.ops.mhw_anim_tools.analyze_export_action("EXEC_DEFAULT")
        timl_status = scene_props.last_status
        timl_diagnostics = _collect_diagnostics(scene_props)

        payload = {
            "inspect_result": _operator_status(inspect_result),
            "import_lmt_result": _operator_status(import_lmt_result),
            "import_timl_result": _operator_status(import_timl_result),
            "analyze_lmt_result": _operator_status(analyze_lmt_result),
            "analyze_timl_result": _operator_status(analyze_timl_result),
            "lmt_action_name": lmt_action_name,
            "timl_action_name": timl_action_name,
            "lmt_status": lmt_status,
            "timl_status": timl_status,
            "lmt_diagnostics": lmt_diagnostics,
            "timl_diagnostics": timl_diagnostics,
        }
        print(json.dumps(payload, indent=2))

        if "FINISHED" not in inspect_result:
            raise SystemExit("Inspect operator did not finish successfully.")
        if "FINISHED" not in import_lmt_result:
            raise SystemExit("LMT action import did not finish successfully.")
        if "FINISHED" not in import_timl_result:
            raise SystemExit("TIML action import did not finish successfully.")
        if "FINISHED" not in analyze_lmt_result:
            raise SystemExit("LMT export analysis should succeed even when TIML controller edits exist.")
        if "CANCELLED" not in analyze_timl_result:
            raise SystemExit("TIML controller export analysis should be blocked until TIML writing exists.")
        if not any("ignores edited TIML controller curves" in item["message"] for item in lmt_diagnostics):
            raise SystemExit("Expected LMT export analysis to warn that TIML controller edits are ignored.")
        if not any("not implemented yet" in item["message"] for item in timl_diagnostics):
            raise SystemExit("Expected TIML export analysis to block unsupported TIML write-back.")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
