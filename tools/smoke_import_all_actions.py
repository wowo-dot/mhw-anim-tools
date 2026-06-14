from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

import bpy


HEADER_STRUCT = struct.Struct("<4shh8s")
ACTION_STRUCT = struct.Struct("<QIIi3i4f4fB2sB5iQ")
TRACK_STRUCT = struct.Struct("<BBBBifiq4fq")


def _register_addon(repo_root: Path):
    package_parent = repo_root.parent
    if str(package_parent) not in sys.path:
        sys.path.insert(0, str(package_parent))
    import mhw_anim_tools

    mhw_anim_tools.register()
    return mhw_anim_tools


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


def _operator_status(result) -> str:
    if isinstance(result, set):
        return ",".join(sorted(result))
    return str(result)


def _build_multi_action_lmt() -> bytes:
    entry_count = 2
    header = HEADER_STRUCT.pack(b"LMT\x00", 95, entry_count, b"\x00" * 8)
    entry_table_offset = 16
    entry_offsets = [40, 136]
    entry_blob = struct.pack("<QQ", *entry_offsets)
    header_padding = b"\x00" * 8

    action0 = ACTION_STRUCT.pack(
        232,  # track offset
        1,    # track count
        20,   # frame count
        -1,
        0, 0, 0,
        0.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
        0,
        b"\x00\x00",
        0,
        0, 0, 0, 0, 0,
        0,
    )
    action1 = ACTION_STRUCT.pack(
        280,  # track offset
        1,    # track count
        42,   # frame count
        -1,
        0, 0, 0,
        0.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
        0,
        b"\x00\x00",
        0,
        0, 0, 0, 0, 0,
        0,
    )
    track0 = TRACK_STRUCT.pack(
        1,    # buffer type
        1,    # usage local translation
        0,
        205,
        0,    # bone 0
        1.0,
        0,
        0,
        1.0, 0.0, 0.0, 0.0,
        0,
    )
    track1 = TRACK_STRUCT.pack(
        1,
        1,
        0,
        205,
        1,    # bone 1
        1.0,
        0,
        0,
        0.0, 2.0, 0.0, 0.0,
        0,
    )
    assert entry_table_offset + len(entry_blob) + len(header_padding) == 40
    assert 40 + len(action0) == 136
    assert 136 + len(action1) == 232
    assert 232 + len(track0) == 280
    return header + entry_blob + header_padding + action0 + action1 + track0 + track1


def main():
    repo_root = Path(__file__).resolve().parents[1]
    addon = _register_addon(repo_root)
    temp_dir = Path(tempfile.mkdtemp(prefix="mhw_anim_tools_smoke_"))
    temp_lmt = temp_dir / "smoke_multi_action.lmt"
    temp_lmt.write_bytes(_build_multi_action_lmt())
    try:
        _reset_scene()
        target_armature = _create_smoke_armature()
        scene_props = bpy.context.scene.mhw_anim_tools
        scene_props.target_armature = target_armature

        inspect_result = bpy.ops.mhw_anim_tools.inspect_lmt("EXEC_DEFAULT", filepath=str(temp_lmt))
        import_result = bpy.ops.mhw_anim_tools.import_all_lmt_actions("EXEC_DEFAULT")

        imported_actions = sorted(action.name for action in bpy.data.actions if action.name.startswith("LMT::smoke_multi_action::"))
        active_action = target_armature.animation_data.action if target_armature.animation_data else None
        payload = {
            "inspect_result": _operator_status(inspect_result),
            "import_result": _operator_status(import_result),
            "status": scene_props.last_status,
            "entry_count": scene_props.last_entry_count,
            "imported_action_count": int(scene_props.last_imported_action_count),
            "last_imported_action_name": scene_props.last_imported_action_name,
            "actions": imported_actions,
            "active_action": active_action.name if active_action else "",
            "frame_end": int(bpy.context.scene.frame_end),
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
            raise SystemExit("Import-all operator did not finish successfully.")
        if scene_props.last_entry_count != 2:
            raise SystemExit("Synthetic multi-action LMT did not expose the expected entry count.")
        if int(scene_props.last_imported_action_count) != 2:
            raise SystemExit("Import-all did not record the expected imported action count.")
        if len(imported_actions) != 2:
            raise SystemExit("Import-all did not create the expected number of Blender Actions.")
        if active_action is None or active_action.name != imported_actions[-1]:
            raise SystemExit("Target armature did not end on the last imported action.")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
