"""Explicit native pose helper creation; source authoring stays separate."""
import bpy

from ..blender_adapter.pose_helpers import create_evaluated_helper
from ..core.formats.lmt.source_bank import LmtSourceBankCache


class MHWANIMTOOLS_OT_build_pose_helper(bpy.types.Operator):
    bl_idname = 'mhw_anim_tools.build_pose_helper'
    bl_label = 'Build Evaluated Helper'
    bl_description = 'Evaluate the native skeletal record rule on a separate helper armature; preserve original source records'
    bl_options = {'REGISTER', 'UNDO'}

    base_policy: bpy.props.EnumProperty(
        name='Missing components',
        items=(('REST', 'Use rest pose', 'Explicitly use rest for components absent from this clip'),
               ('ACTION', 'Use selected export action', 'Require a complete compatible base action for absent components')),
        default='REST')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        props = context.scene.mhw_anim_tools
        try:
            entry = props.lmt_entries[props.selected_entry_index]
            if entry.entry_state != 'source':
                raise ValueError('Choose a populated source entry')
            bank = LmtSourceBankCache(max_banks=0).load(props.last_lmt_path)
            result = create_evaluated_helper(bank, entry.entry_id, props.target_armature,
                base_policy=self.base_policy,
                base_action=props.export_action if self.base_policy == 'ACTION' else None)
        except (ValueError, OSError, IndexError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        result.armature.select_set(True)
        context.view_layer.objects.active = result.armature
        context.scene.frame_start = 0
        context.scene.frame_end = max(1, result.evaluation.source.header.frame_count - 1)
        result.set_frame(0)
        repeated = sum(len(b.source_indices) > 1 for b in result.evaluation.bindings)
        unbound = sum(len(d.source_indices) for d in result.evaluation.diagnostics if d.level == 'INFO')
        props.last_status = f'Created {result.armature.name}: {repeated} repeated destinations resolved; {unbound} unbound records retained. Raw source action: {result.raw_action.name}.'
        self.report({'INFO'}, props.last_status)
        return {'FINISHED'}


def register():
    bpy.utils.register_class(MHWANIMTOOLS_OT_build_pose_helper)


def unregister():
    bpy.utils.unregister_class(MHWANIMTOOLS_OT_build_pose_helper)
