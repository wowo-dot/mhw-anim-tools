"""Source-backed native pose helpers made of ordinary Blender FCurves.

No drivers, frame handlers, background services or GPU packages are needed.
Key quaternion lengths are retained so Blender's normalized quaternion matrices
implement the native raw-endpoint NLERP at arbitrary subframes and after reopen.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

import bpy

try:
    from ..core.formats.lmt.pose_evaluation import RULE_VERSION, compile_pose_evaluation
    from ..core.formats.lmt.semantics import get_usage_semantics
    from ..integration.mhw_bones import bone_index_from_name, bonefunction_index_from_name, is_mhbone_name, is_bonefunction_name
except ImportError:
    from core.formats.lmt.pose_evaluation import RULE_VERSION, compile_pose_evaluation
    from core.formats.lmt.semantics import get_usage_semantics
    from integration.mhw_bones import bone_index_from_name, bonefunction_index_from_name, is_mhbone_name, is_bonefunction_name
from .actions import import_lmt_action_to_armature
from .armature import ensure_mhw_root_motion_bone
from .fcurves import assign_action, create_action_fcurves, build_channel_value_lists, ensure_armature_animation_data
from .source_identity import source_file_identity_from_bytes
from .space import TrackSpaceTarget, adapt_track_frames_for_target_space, uses_mhw_model_editor_space_adapter

RULE_KEY = "mhw_anim_tools_pose_rule"
CONFIG_KEY = "mhw_anim_tools_pose_source"
_TRANSFORMS = (("rotation_quaternion", (1., 0., 0., 0.)), ("location", (0., 0., 0.)), ("scale", (1., 1., 1.)))


def model_function_map(armature):
    result = {}
    for bone in armature.data.bones:
        function = (bone_index_from_name(bone.name) if is_mhbone_name(bone.name) else
                    bonefunction_index_from_name(bone.name) if is_bonefunction_name(bone.name) else None)
        if function is None:
            continue
        function &= 511
        if function in result:
            raise ValueError(f"Ambiguous model function {function}: provide an explicit function_map")
        result[function] = bone.name
    return result


@dataclass
class EvaluatedHelper:
    armature: object
    action: object
    raw_action: object | None
    evaluation: object
    source_bank: object

    def set_frame(self, frame: float, *, scene=None):
        """Evaluate through Blender's dependency graph, including fractional time.

        Scene time is changed intentionally. Sampling order does not matter. Keep
        this object per bake job to reuse its immutable bank and compiled curves.
        """
        frame = float(frame)
        if not math.isfinite(frame) or not 0 <= frame <= self.evaluation.source.header.frame_count - 1:
            raise ValueError("Frame is outside the native clip range")
        scene = scene or bpy.context.scene
        integer = math.floor(frame)
        scene.frame_set(integer, subframe=frame-integer)
        return self.armature.evaluated_get(bpy.context.evaluated_depsgraph_get())


def _path(bone, transform):
    return f'pose.bones["{bpy.utils.escape_identifier(bone)}"].{transform}'


def _curves(action, path, bone, frames):
    return create_action_fcurves(action, data_path=path, action_group=bone,
                                 channel_values=build_channel_value_lists(frames))


def _native_curve_frames(curve, end):
    times = sorted({0, end, *(f for f in curve.frames if f <= end)})
    values = [(float(t), curve.raw_sample(t)) for t in times]
    if curve.quaternion:
        # A consistent lift to quaternion components; preserve original lengths.
        lifted = []
        for time, value in values:
            if lifted and sum(a*b for a, b in zip(lifted[-1][1], value)) < 0:
                value = tuple(-x for x in value)
            lifted.append((time, value))
        values = lifted
    return values


def _converted_frames(armature, target, usage, curve, end):
    frames = _native_curve_frames(curve, end)
    if not curve.quaternion:
        return adapt_track_frames_for_target_space(armature, target, usage, frames)
    lengths = [math.sqrt(sum(x*x for x in value)) for _, value in frames]
    normalized = [(time, tuple(x/length for x in value)) for (time, value), length in zip(frames, lengths)]
    adapted = adapt_track_frames_for_target_space(armature, target, usage, normalized)
    return [(time, tuple(x*length for x in value)) for (time, value), length in zip(adapted, lengths)]


def create_evaluated_helper(source_bank, entry_id, template, *, base_policy,
                            base_action=None, function_map=None, create_raw_action=True):
    """Build a separate source helper hierarchy and a uniquely owned Action.

    ``REST`` explicitly supplies rest for every unbound component. ``ACTION``
    requires complete base FCurves for every unbound helper component; a helper
    built with REST is a convenient complete base. Nothing samples the current
    pose or changes the template hierarchy, action, constraints or mesh modifiers.

    The raw action (optional for bulk work) uses the unchanged legacy authoring
    path. Editing it does not silently change this evaluated snapshot. Rebuild
    from explicit slot replacements when that is the intended operation.
    """
    if template is None or template.type != 'ARMATURE':
        raise ValueError("Choose a source model armature")
    if base_policy not in ('REST', 'ACTION'):
        raise ValueError("Choose an explicit REST or ACTION base policy")
    if base_policy == 'ACTION' and base_action is None:
        raise ValueError("ACTION base requires a Blender Action")
    if base_policy == 'REST' and base_action is not None:
        raise ValueError("REST base does not accept a base action")
    source = next((a for a in source_bank.lmt.actions if a.id == int(entry_id)), None)
    if source is None or source.header.frame_count < 1:
        raise ValueError("Choose a populated source entry with a positive native frame count")
    mapping = dict(function_map) if function_map is not None else model_function_map(template)
    if not mapping or any(name not in template.data.bones for name in mapping.values()):
        raise ValueError("The source model function map is empty or names missing bones")
    evaluation = compile_pose_evaluation(source, mapping, version=source_bank.lmt.header.version)
    if not evaluation.supported:
        raise ValueError('; '.join(d.message for d in evaluation.diagnostics if d.level == 'ERROR'))
    if source.header.flags2 & 1 and base_policy != 'ACTION':
        raise ValueError("NeedsParent entry requires an explicit ACTION base/context")
    collection = bpy.data.collections.new(f"MHW Pose {entry_id:03d}")
    bpy.context.scene.collection.children.link(collection)
    if uses_mhw_model_editor_space_adapter(template):
        collection["~TYPE"] = "MHW_MOD3_COLLECTION"
    data = template.data.copy()
    helper = bpy.data.objects.new(f"{template.name} Pose {entry_id:03d}", data)
    collection.objects.link(helper)
    helper.matrix_world = template.matrix_world.copy()
    helper.show_in_front = True
    action = raw_action = None
    try:
        root = ensure_mhw_root_motion_bone(helper)
        if root.error or root.name is None:
            raise ValueError(root.error or "A dedicated MHW root helper could not be established")
        if root.name in mapping.values():
            raise ValueError("Root/action channels need a dedicated bone separate from model functions")
        # Newly linked objects with an existing root do not take the edit-mode
        # path above; Blender creates their pose channels on dependency update.
        bpy.context.view_layer.update()
        for bone in helper.pose.bones:
            bone.rotation_mode = 'QUATERNION'
        end = source.header.frame_count - 1
        # Copy only supported unbound base component curves, without other ID
        # properties, slots or import/export ownership metadata from the base.
        selected_paths = {}
        for binding in evaluation.bindings:
            bone = binding.target if binding.target is not None else root.name
            usage = get_usage_semantics(binding.usage)
            path = _path(bone, usage.blender_path_hint)
            selected_paths[path] = (binding, TrackSpaceTarget('bone', bone), usage)
        action = bpy.data.actions.new(f"{helper.name} Evaluated")
        action[RULE_KEY] = RULE_VERSION
        base_curves = {(fc.data_path, fc.array_index): fc for fc in base_action.fcurves} if base_action else {}
        for bone in helper.pose.bones:
            for transform, default in _TRANSFORMS:
                path = _path(bone.name, transform)
                selected = selected_paths.get(path)
                if selected:
                    binding, target, usage = selected
                    frames = _converted_frames(helper, target, usage, binding.curve, end)
                    _curves(action, path, bone.name, frames)
                elif base_policy == 'REST':
                    _curves(action, path, bone.name,
                            [(0., default), (float(end), default)] if end else [(0., default)])
                else:
                    for index in range(len(default)):
                        source_curve = base_curves.get((path, index))
                        if source_curve is None or not source_curve.keyframe_points:
                            raise ValueError(f"Explicit base is missing {path}[{index}]")
                        if source_curve.modifiers or any(p.interpolation not in ('LINEAR', 'CONSTANT') for p in source_curve.keyframe_points):
                            raise ValueError("Base curves must be LINEAR/CONSTANT without modifiers; bake the base first")
                        curve = action.fcurves.new(path, index=index, action_group=bone.name)
                        curve.extrapolation = source_curve.extrapolation
                        for point in source_curve.keyframe_points:
                            copied = curve.keyframe_points.insert(*point.co, options={'FAST'})
                            copied.interpolation = point.interpolation
                        curve.update()
        if create_raw_action:
            result = import_lmt_action_to_armature(source_bank.lmt, entry_id, helper,
                source_path=source_bank.lmt.source_name,
                source_identity=source_file_identity_from_bytes(source_bank.data))
            raw_action = bpy.data.actions.get(result.action_name)
            if raw_action is None:
                raise ValueError("Could not create a raw source authoring action")
            raw_action.use_fake_user = True
        config = dict(rule=RULE_VERSION, source_path=source_bank.lmt.source_name, source_sha256=source_bank.sha256,
                      entry_id=int(entry_id), frame_count=source.header.frame_count, loop_frame=source.header.loop_frame,
                      base_policy=base_policy, base_action=base_action.name if base_action else None,
                      raw_action=raw_action.name if raw_action else None, function_map=sorted(mapping.items()),
                      bindings=[dict(target=b.target, usage=b.usage, source_indices=b.source_indices,
                                     selected=b.source_index, identical=b.identical) for b in evaluation.bindings],
                      diagnostics=[dict(level=d.level, source_indices=d.source_indices, message=d.message)
                                   for d in evaluation.diagnostics])
        helper[CONFIG_KEY] = action[CONFIG_KEY] = json.dumps(config, separators=(',', ':'))
        helper[RULE_KEY] = RULE_VERSION
        action.use_fake_user = True
        action.use_frame_range = True
        action.frame_start, action.frame_end = 0, end
        assign_action(ensure_armature_animation_data(helper), action)
        return EvaluatedHelper(helper, action, raw_action, evaluation, source_bank)
    except Exception:
        bpy.data.objects.remove(helper, do_unlink=True)
        bpy.data.armatures.remove(data)
        for created in (action, raw_action):
            if created is not None:
                bpy.data.actions.remove(created)
        bpy.data.collections.remove(collection)
        raise


def load_helper_source(helper, cache):
    """Resolve the exact pinned source after reopening, rejecting changed files."""
    config = json.loads(helper[CONFIG_KEY])
    if config['rule'] != RULE_VERSION:
        raise ValueError("This helper uses a different evaluation rule version; rebuild explicitly")
    bank = cache.load(config['source_path'])
    if bank.sha256 != config['source_sha256']:
        raise ValueError("Helper source file changed; rebuild explicitly or restore the pinned source")
    return bank


def dispose_evaluated_helper(result):
    """Release an explicitly temporary bake helper after its consumers finish.

    Actions/data reused by another Blender object remain alive. UI-created review
    helpers are not disposed automatically. Drop any separately held bank/plan
    references as well when ending a worker job.
    """
    obj = result.armature
    data = obj.data
    collections = tuple(obj.users_collection)
    bpy.data.objects.remove(obj, do_unlink=True)
    if not data.users:
        bpy.data.armatures.remove(data)
    for action in (result.action, result.raw_action):
        if action is not None and action.users <= int(action.use_fake_user):
            bpy.data.actions.remove(action)
    for collection in collections:
        if not collection.objects and not collection.children:
            bpy.data.collections.remove(collection)
    result.armature = result.action = result.raw_action = result.evaluation = result.source_bank = None
