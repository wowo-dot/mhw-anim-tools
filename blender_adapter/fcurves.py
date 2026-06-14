"""Small Blender FCurve helpers for the new importer."""

from __future__ import annotations

import bpy


TIML_INTERPOLATION_TO_BLENDER = {
    0: "CONSTANT",
    1: "LINEAR",
}


def clear_action_fcurves(action):
    for fcurve in list(action.fcurves):
        action.fcurves.remove(fcurve)


def ensure_action(action_name: str):
    action = bpy.data.actions.get(action_name)
    if action is None:
        action = bpy.data.actions.new(action_name)
    else:
        clear_action_fcurves(action)
    return action


def ensure_armature_animation_data(armature_object):
    if armature_object.animation_data is None:
        armature_object.animation_data_create()
    return armature_object.animation_data


def ensure_object_animation_data(target_object):
    if target_object.animation_data is None:
        target_object.animation_data_create()
    return target_object.animation_data


def build_channel_value_lists(frames: list[tuple[float, tuple[float, ...]]]) -> list[list[tuple[float, float]]]:
    if not frames:
        return []
    channel_count = len(frames[0][1])
    channels = [[] for _ in range(channel_count)]
    for frame, value in frames:
        for index, component in enumerate(value):
            channels[index].append((float(frame), float(component)))
    return channels


def _keyframe_interpolation_name(code):
    return TIML_INTERPOLATION_TO_BLENDER.get(int(code), "LINEAR")


def _populate_fcurve_keyframes(fcurve, keyframes, interpolations=None):
    fcurve.keyframe_points.add(len(keyframes))
    for key_index, (frame, value) in enumerate(keyframes):
        keyframe = fcurve.keyframe_points[key_index]
        keyframe.co = (frame, value)
        if interpolations is None:
            keyframe.interpolation = "LINEAR"
        else:
            keyframe.interpolation = _keyframe_interpolation_name(interpolations[key_index])
    fcurve.update()


def create_scalar_action_fcurve(action, *, data_path: str, action_group: str, keyframes, interpolations=None):
    fcurve = action.fcurves.new(data_path=data_path, action_group=action_group)
    _populate_fcurve_keyframes(fcurve, keyframes, interpolations=interpolations)
    return fcurve


def create_action_fcurves(
    action,
    *,
    data_path: str,
    action_group: str,
    channel_values: list[list[tuple[float, float]]],
    channel_interpolations=None,
):
    created = []
    for array_index, keyframes in enumerate(channel_values):
        fcurve = action.fcurves.new(data_path=data_path, index=array_index, action_group=action_group)
        interpolations = None if channel_interpolations is None else channel_interpolations[array_index]
        _populate_fcurve_keyframes(fcurve, keyframes, interpolations=interpolations)
        created.append(fcurve)
    return created


def create_transform_fcurves(action, *, bone_name: str, data_path_suffix: str, channel_values: list[list[tuple[float, float]]]):
    data_path = f'pose.bones["{bone_name}"].{data_path_suffix}'
    return create_action_fcurves(
        action,
        data_path=data_path,
        action_group=bone_name,
        channel_values=channel_values,
    )
