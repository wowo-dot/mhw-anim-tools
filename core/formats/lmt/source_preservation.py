"""Helpers for preserving raw source LMT tracks during source-aware export.

When an imported Blender Action still represents the same motion as the source
LMT track, we prefer preserving the original raw buffer bytes instead of
re-encoding through Blender's normalized quaternion space. This is especially
important for source quaternion lerp buffers whose raw component ranges are not
strictly unit-length even though they describe the same rotation.
"""

from __future__ import annotations

from ...animation.transforms import canonicalize_quaternion_frames_wxyz
from ...animation.transforms import flip_quaternion_wxyz
from ...animation.transforms import normalize_quaternion_wxyz
from ...animation.transforms import quaternion_dot_wxyz
from .semantics import get_usage_semantics


def _supported_decoded_tracks(decoded_action):
    supported = []
    for track in decoded_action.tracks:
        usage = get_usage_semantics(track.usage)
        if usage.transform in {"rotation", "translation", "scale"} and usage.blender_path_hint and not track.decode_error:
            supported.append(track)
    return supported


def _decoded_explicit_frames(decoded_track):
    usage = get_usage_semantics(decoded_track.usage)
    if decoded_track.keyframes:
        frames = [(float(sample.frame), tuple(float(component) for component in sample.value)) for sample in decoded_track.keyframes]
    else:
        frames = [(0.0, tuple(float(component) for component in decoded_track.basis_value))]
    if decoded_track.tail_frame is not None and decoded_track.tail_value is not None:
        frames.append((float(decoded_track.tail_frame), tuple(float(component) for component in decoded_track.tail_value)))
    if usage.is_quaternion:
        frames = canonicalize_quaternion_frames_wxyz(frames)
    return frames


def _dense_decoded_track_frames(decoded_track, frame_end: int) -> dict[int, tuple[float, ...]]:
    usage = get_usage_semantics(decoded_track.usage)
    explicit_frames = _decoded_explicit_frames(decoded_track)
    if not explicit_frames:
        return {}

    dense_frames: list[tuple[float, tuple[float, ...]]] = []
    for index, (start_frame, start_value) in enumerate(explicit_frames):
        start_frame_int = int(round(start_frame))
        if index + 1 >= len(explicit_frames):
            for frame in range(start_frame_int, int(frame_end) + 1):
                dense_frames.append((float(frame), tuple(float(component) for component in start_value)))
            break

        end_frame, end_value = explicit_frames[index + 1]
        end_frame_int = int(round(end_frame))
        if end_frame_int <= start_frame_int:
            continue
        for frame in range(start_frame_int, end_frame_int):
            blend = (frame - start_frame_int) / float(end_frame_int - start_frame_int)
            dense_frames.append(
                (
                    float(frame),
                    tuple(
                        float(left_component) + (float(right_component) - float(left_component)) * blend
                        for left_component, right_component in zip(start_value, end_value)
                    ),
                )
            )
    last_frame, last_value = explicit_frames[-1]
    if int(round(last_frame)) <= int(frame_end):
        dense_frames.append((float(int(round(last_frame))), tuple(float(component) for component in last_value)))

    if usage.is_quaternion:
        dense_frames = canonicalize_quaternion_frames_wxyz(dense_frames, normalize=True)
    return {
        int(round(frame)): tuple(float(component) for component in value)
        for frame, value in dense_frames
        if int(round(frame)) <= int(frame_end)
    }


def _quaternion_values_match(expected, actual, tolerance: float) -> bool:
    expected_quaternion = normalize_quaternion_wxyz(tuple(float(component) for component in expected))
    actual_quaternion = normalize_quaternion_wxyz(tuple(float(component) for component in actual))
    if quaternion_dot_wxyz(expected_quaternion, actual_quaternion) < 0.0:
        actual_quaternion = flip_quaternion_wxyz(actual_quaternion)
    return all(
        abs(actual_component - expected_component) <= tolerance
        for actual_component, expected_component in zip(actual_quaternion, expected_quaternion)
    )


def identify_preservable_decoded_track_identities(
    decoded_action,
    sampled_tracks,
    *,
    tolerance: float = 1e-3,
) -> frozenset[tuple[int, int]]:
    """Return track identities whose sampled motion still matches the source."""

    sampled_map = {
        (int(track.bone_id), int(track.usage)): {
            int(sample.frame): tuple(float(component) for component in sample.value)
            for sample in track.frames
        }
        for track in sampled_tracks
    }

    preservable: set[tuple[int, int]] = set()
    for decoded_track in _supported_decoded_tracks(decoded_action):
        identity = (int(decoded_track.bone_id), int(decoded_track.usage))
        sampled_frames = sampled_map.get(identity)
        if not sampled_frames:
            continue

        expected_frames = _dense_decoded_track_frames(decoded_track, max(sampled_frames))
        if not expected_frames:
            continue

        usage = get_usage_semantics(decoded_track.usage)
        matches = True
        for frame, expected_value in expected_frames.items():
            actual_value = sampled_frames.get(frame)
            if actual_value is None:
                matches = False
                break
            if usage.is_quaternion:
                if not _quaternion_values_match(expected_value, actual_value, tolerance):
                    matches = False
                    break
            else:
                if any(abs(actual - expected) > tolerance for actual, expected in zip(actual_value, expected_value)):
                    matches = False
                    break
        if matches:
            preservable.add(identity)

    return frozenset(preservable)
