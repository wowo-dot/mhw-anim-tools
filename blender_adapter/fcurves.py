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


def bind_action_slot(animation_data, action=None):
    if animation_data is None:
        return None
    if action is None:
        action = getattr(animation_data, "action", None)
    if action is None:
        return None

    slots = getattr(action, "slots", None)
    if slots is None:
        return None
    try:
        if len(slots) <= 0:
            return None
    except TypeError:
        return None

    chosen_slot = None
    suitable_slots = getattr(animation_data, "action_suitable_slots", None)
    if suitable_slots is not None:
        try:
            suitable_slots = list(suitable_slots)
        except TypeError:
            suitable_slots = []
        if suitable_slots:
            chosen_slot = suitable_slots[0]
            chosen_handle = getattr(chosen_slot, "handle", None)
            if chosen_handle is not None:
                matching_slot = next(
                    (slot for slot in slots if getattr(slot, "handle", None) == chosen_handle),
                    None,
                )
                if matching_slot is not None:
                    chosen_slot = matching_slot
    if chosen_slot is None:
        try:
            chosen_slot = slots[0]
        except (IndexError, KeyError, TypeError):
            return None

    try:
        animation_data.action_slot = chosen_slot
    except AttributeError:
        pass
    except TypeError:
        pass

    chosen_handle = getattr(chosen_slot, "handle", None)
    if chosen_handle is not None:
        try:
            animation_data.action_slot_handle = chosen_handle
        except AttributeError:
            pass
        except TypeError:
            pass
    return chosen_slot


def assign_action(animation_data, action):
    if animation_data is None:
        return None
    animation_data.action = action
    return bind_action_slot(animation_data, action)


def clear_action_assignment(animation_data, action=None):
    if animation_data is None:
        return
    if action is not None and getattr(animation_data, "action", None) != action:
        return
    try:
        animation_data.action_slot = None
    except AttributeError:
        pass
    except TypeError:
        pass
    try:
        animation_data.action_slot_handle = 0
    except AttributeError:
        pass
    except TypeError:
        pass
    animation_data.action = None


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
