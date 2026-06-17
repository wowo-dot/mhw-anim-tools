"""Reconstruct sparse LMT-style tracks from dense normalized samples."""

from __future__ import annotations

from ...animation.transforms import canonicalize_quaternion_frames_wxyz
from ...animation.transforms import flip_quaternion_wxyz
from ...animation.transforms import nlerp_quaternion_wxyz
from ...animation.transforms import quaternion_dot_wxyz
from ...animation.transforms import quaternion_norm_squared_wxyz
from ...animation.transforms import QUATERNION_EPSILON
from .reconstructed import LmtReconstructedAction
from .reconstructed import LmtReconstructedKeyframe
from .reconstructed import LmtReconstructedTrack
from .semantics import get_usage_semantics


DEFAULT_RECONSTRUCTION_TOLERANCE = 1e-4
RAW_SOURCE_QUATERNION_TOLERANCE = 1e-3


def _normalized_frames(frames) -> list[tuple[int, tuple[float, ...]]]:
    normalized = []
    for frame in frames:
        if hasattr(frame, "frame") and hasattr(frame, "value"):
            timing = int(frame.frame)
            value = tuple(float(component) for component in frame.value)
        else:
            timing, raw_value = frame
            timing = int(timing)
            value = tuple(float(component) for component in raw_value)
        normalized.append((timing, value))
    normalized.sort(key=lambda item: item[0])
    return normalized


def _raw_quaternion_keyframes_from_authored_frames(
    frames,
    authored_frames,
) -> list[tuple[int, tuple[float, ...]]]:
    normalized = _normalized_frames(frames)
    if not normalized:
        return []
    frame_lookup = {frame: value for frame, value in normalized}
    anchor_frames = sorted({int(frame) for frame in authored_frames if int(frame) in frame_lookup})
    if normalized[0][0] not in anchor_frames:
        anchor_frames.insert(0, normalized[0][0])
    return [(frame, frame_lookup[frame]) for frame in anchor_frames]


def _is_linear_step(previous, current, following, tolerance: float) -> bool:
    previous_time, previous_value = previous
    current_time, current_value = current
    following_time, following_value = following
    if not (previous_time < current_time < following_time):
        return False
    span = following_time - previous_time
    if span <= 0:
        return False
    blend = (current_time - previous_time) / float(span)
    for left, middle, right in zip(previous_value, current_value, following_value):
        expected = left + (right - left) * blend
        if abs(expected - middle) > tolerance:
            return False
    return True


def _is_quaternion_nlerp_step(previous, current, following, tolerance: float) -> bool:
    previous_time, previous_value = previous
    current_time, current_value = current
    following_time, following_value = following
    if not (previous_time < current_time < following_time):
        return False
    span = following_time - previous_time
    if span <= 0:
        return False
    blend = (current_time - previous_time) / float(span)
    expected = nlerp_quaternion_wxyz(previous_value, following_value, blend)
    actual = tuple(float(component) for component in current_value)
    if quaternion_dot_wxyz(expected, actual) < 0.0:
        actual = flip_quaternion_wxyz(actual)
    return all(abs(expected_component - actual_component) <= tolerance for expected_component, actual_component in zip(expected, actual))


def _quaternion_nlerp_error(start, current, end) -> float:
    start_time, start_value = start
    current_time, current_value = current
    end_time, end_value = end
    if not (start_time < current_time < end_time):
        return 0.0
    span = end_time - start_time
    if span <= 0:
        return 0.0
    blend = (current_time - start_time) / float(span)
    expected = nlerp_quaternion_wxyz(start_value, end_value, blend)
    actual = tuple(float(component) for component in current_value)
    if quaternion_dot_wxyz(expected, actual) < 0.0:
        actual = flip_quaternion_wxyz(actual)
    return max(abs(expected_component - actual_component) for expected_component, actual_component in zip(expected, actual))


def _sparsify_quaternion_segment(segment, tolerance: float) -> list[tuple[int, tuple[float, ...]]]:
    if len(segment) <= 2:
        return list(segment)
    start = segment[0]
    end = segment[-1]
    worst_index = None
    worst_error = 0.0
    for index in range(1, len(segment) - 1):
        error = _quaternion_nlerp_error(start, segment[index], end)
        if error > worst_error:
            worst_error = error
            worst_index = index
    if worst_index is None or worst_error <= tolerance:
        return [start, end]
    left = _sparsify_quaternion_segment(segment[: worst_index + 1], tolerance)
    right = _sparsify_quaternion_segment(segment[worst_index:], tolerance)
    return left[:-1] + right


def _sparsify_frames(frames, tolerance: float, *, quaternion: bool = False) -> list[tuple[int, tuple[float, ...]]]:
    if len(frames) <= 2:
        return list(frames)
    if quaternion:
        return _sparsify_quaternion_segment(frames, tolerance)
    sparse = [frames[0]]
    for index in range(1, len(frames) - 1):
        previous = sparse[-1]
        current = frames[index]
        following = frames[index + 1]
        is_redundant = _is_linear_step(previous, current, following, tolerance)
        if is_redundant:
            continue
        sparse.append(current)
    sparse.append(frames[-1])
    return sparse


def _sparsify_frames_with_authored_anchors(
    frames: list[tuple[int, tuple[float, ...]]],
    authored_frames,
    tolerance: float,
    *,
    quaternion: bool = False,
) -> list[tuple[int, tuple[float, ...]]]:
    if len(frames) <= 2:
        return list(frames)
    if not authored_frames:
        return _sparsify_frames(frames, tolerance, quaternion=quaternion)

    frame_lookup = {frame: value for frame, value in frames}
    anchor_times = [int(frame) for frame in authored_frames if int(frame) in frame_lookup]
    if not anchor_times:
        return _sparsify_frames(frames, tolerance, quaternion=quaternion)
    if frames[0][0] not in anchor_times:
        anchor_times.insert(0, frames[0][0])
    anchor_times = sorted(set(anchor_times))
    if len(anchor_times) == 1:
        return [frames[0]]

    index_lookup = {frame: index for index, (frame, _value) in enumerate(frames)}
    anchor_indices = [index_lookup[frame] for frame in anchor_times]
    sparse: list[tuple[int, tuple[float, ...]]] = []
    for start_index, end_index in zip(anchor_indices, anchor_indices[1:]):
        segment = frames[start_index : end_index + 1]
        segment_sparse = _sparsify_frames(segment, tolerance, quaternion=quaternion)
        if sparse:
            segment_sparse = segment_sparse[1:]
        sparse.extend(segment_sparse)
    return sparse or [frames[0]]


def _all_values_match_basis(frames, basis_value: tuple[float, ...], tolerance: float) -> bool:
    for _frame, value in frames[1:]:
        if any(abs(component - basis_component) > tolerance for component, basis_component in zip(value, basis_value)):
            return False
    return True


def _values_match(left: tuple[float, ...], right: tuple[float, ...], tolerance: float) -> bool:
    return all(abs(l_component - r_component) <= tolerance for l_component, r_component in zip(left, right))


def _canonicalize_quaternion_frames(
    frames: list[tuple[int, tuple[float, ...]]],
) -> list[tuple[int, tuple[float, ...]]]:
    canonical = canonicalize_quaternion_frames_wxyz(
        [(float(frame), value) for frame, value in frames],
    )
    return [(int(round(frame)), tuple(float(component) for component in value)) for frame, value in canonical]


def reconstruct_track_samples(
    *,
    bone_id: int,
    usage: int,
    frames,
    authored_frames: tuple[int, ...] | None = None,
    authored_frame_end: int | None = None,
    tolerance: float = DEFAULT_RECONSTRUCTION_TOLERANCE,
) -> LmtReconstructedTrack:
    normalized = _normalized_frames(frames)
    if not normalized:
        return LmtReconstructedTrack(bone_id=bone_id, usage=usage, basis_value=())

    usage_info = get_usage_semantics(usage)
    if usage_info.is_quaternion:
        normalized = _canonicalize_quaternion_frames(normalized)
    sparse = _sparsify_frames_with_authored_anchors(
        normalized,
        authored_frames,
        tolerance,
        quaternion=usage_info.is_quaternion,
    )
    basis_value = sparse[0][1]
    has_tail_semantics = usage_info.scope == "root" and usage_info.transform != "scale"
    if not has_tail_semantics and not authored_frames and _all_values_match_basis(normalized, basis_value, tolerance):
        sparse = [sparse[0]]
    if not has_tail_semantics and not authored_frames and authored_frame_end is not None:
        while (
            len(sparse) >= 2
            and sparse[-1][0] > int(authored_frame_end)
            and _values_match(sparse[-1][1], sparse[-2][1], tolerance)
        ):
            sparse.pop()

    tail_frame = None
    tail_value = None
    keyframe_frames = sparse[1:]
    if has_tail_semantics and len(sparse) >= 2:
        tail_frame, tail_value = sparse[-1]
        keyframe_frames = sparse[1:-1]

    return LmtReconstructedTrack(
        bone_id=int(bone_id),
        usage=int(usage),
        basis_value=tuple(float(component) for component in basis_value),
        keyframes=tuple(
            LmtReconstructedKeyframe(frame=int(frame), value=tuple(float(component) for component in value))
            for frame, value in keyframe_frames
        ),
        tail_frame=int(tail_frame) if tail_frame is not None else None,
        tail_value=tuple(float(component) for component in tail_value) if tail_value is not None else None,
    )


def _reconstruct_source_raw_quaternion_track(track) -> LmtReconstructedTrack | None:
    raw_frames = getattr(track, "raw_frames", ())
    authored_frames = getattr(track, "authored_frames", ())
    if not raw_frames or not authored_frames or not getattr(track, "all_authored_keys_linear", True):
        return None
    sparse = _raw_quaternion_keyframes_from_authored_frames(raw_frames, authored_frames)
    if not sparse:
        return None
    usage_info = get_usage_semantics(track.usage)
    basis_value = sparse[0][1]
    has_tail_semantics = usage_info.scope == "root" and usage_info.transform != "scale"
    tail_frame = None
    tail_value = None
    keyframe_frames = sparse[1:]
    if has_tail_semantics and len(sparse) >= 2:
        tail_frame, tail_value = sparse[-1]
        keyframe_frames = sparse[1:-1]
    return LmtReconstructedTrack(
        bone_id=int(track.bone_id),
        usage=int(track.usage),
        basis_value=tuple(float(component) for component in basis_value),
        keyframes=tuple(
            LmtReconstructedKeyframe(frame=int(frame), value=tuple(float(component) for component in value))
            for frame, value in keyframe_frames
        ),
        tail_frame=int(tail_frame) if tail_frame is not None else None,
        tail_value=tuple(float(component) for component in tail_value) if tail_value is not None else None,
        source_track_index=getattr(track, "source_track_index", None),
        preserve_raw_quaternion_values=bool(getattr(track, "preserve_raw_quaternion_values", False)),
    )


def _raw_quaternion_frames_are_source_sensitive(
    track,
    *,
    tolerance: float = RAW_SOURCE_QUATERNION_TOLERANCE,
) -> bool:
    raw_frames = getattr(track, "raw_frames", ())
    if not raw_frames:
        return False
    lower_bound = (1.0 - float(tolerance)) ** 2
    upper_bound = (1.0 + float(tolerance)) ** 2
    for sample in raw_frames:
        norm_squared = quaternion_norm_squared_wxyz(tuple(float(component) for component in sample.value))
        if norm_squared <= QUATERNION_EPSILON:
            continue
        if norm_squared < lower_bound or norm_squared > upper_bound:
            return True
    return False


def reconstruct_sampled_action(
    *,
    action_name: str,
    frame_start: int,
    frame_end: int,
    sampled_tracks,
    tolerance: float = DEFAULT_RECONSTRUCTION_TOLERANCE,
    raw_quaternion_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] | None = None,
) -> LmtReconstructedAction:
    raw_quaternion_source_identities = frozenset(raw_quaternion_source_identities or ())
    reconstructed_tracks = []
    for track in sampled_tracks:
        identity = (int(track.bone_id), int(track.usage))
        preserve_raw_quaternion_values = bool(getattr(track, "preserve_raw_quaternion_values", False))
        raw_source_sensitive = preserve_raw_quaternion_values or (
            identity in raw_quaternion_source_identities and _raw_quaternion_frames_are_source_sensitive(track)
        )
        if raw_source_sensitive:
            raw_track = _reconstruct_source_raw_quaternion_track(track)
            if raw_track is not None:
                reconstructed_tracks.append(raw_track)
                continue
        reconstructed_track = reconstruct_track_samples(
            bone_id=track.bone_id,
            usage=track.usage,
            frames=track.frames,
            authored_frames=getattr(track, "authored_frames", ()),
            authored_frame_end=getattr(track, "authored_frame_end", None),
            tolerance=tolerance,
        )
        reconstructed_tracks.append(
            LmtReconstructedTrack(
                bone_id=int(reconstructed_track.bone_id),
                usage=int(reconstructed_track.usage),
                basis_value=tuple(float(component) for component in reconstructed_track.basis_value),
                keyframes=tuple(reconstructed_track.keyframes),
                tail_frame=reconstructed_track.tail_frame,
                tail_value=reconstructed_track.tail_value,
                source_track_index=getattr(track, "source_track_index", None),
                preserve_raw_quaternion_values=preserve_raw_quaternion_values,
            )
        )
    indexed_tracks = [track for track in reconstructed_tracks if getattr(track, "source_track_index", None) is not None]
    if indexed_tracks and len(indexed_tracks) == len(reconstructed_tracks):
        tracks = tuple(sorted(reconstructed_tracks, key=lambda item: int(item.source_track_index)))
    else:
        tracks = tuple(reconstructed_tracks)
    return LmtReconstructedAction(
        action_name=action_name,
        frame_start=int(frame_start),
        frame_end=int(frame_end),
        tracks=tracks,
    )


def reconstruct_decoded_action(
    decoded_action,
    *,
    action_name: str | None = None,
) -> LmtReconstructedAction:
    """Convert decoded source samples directly into reconstructed export-prep data.

    This path is intentionally loss-minimizing:
    - basis values stay at frame 0
    - decoded sparse keyframes are copied through unchanged
    - root tail semantics are preserved exactly as decoded

    It is useful for read-only readiness scans that want to ask whether the
    current writer stack can represent source LMT actions without involving any
    Blender sampling or editing layers.
    """

    reconstructed_tracks = []
    for track in getattr(decoded_action, "tracks", ()):
        if getattr(track, "decode_error", None):
            continue
        usage_info = get_usage_semantics(track.usage)
        reconstructed_tracks.append(
            LmtReconstructedTrack(
                bone_id=int(track.bone_id),
                usage=int(track.usage),
                basis_value=tuple(float(component) for component in track.basis_value),
                keyframes=tuple(
                    LmtReconstructedKeyframe(
                        frame=int(sample.frame),
                        value=tuple(float(component) for component in sample.value),
                    )
                    for sample in track.keyframes
                ),
                tail_frame=int(track.tail_frame) if track.tail_frame is not None else None,
                tail_value=tuple(float(component) for component in track.tail_value)
                if track.tail_value is not None
                else None,
                source_track_index=int(getattr(track, "track_index", 0)),
                preserve_raw_quaternion_values=bool(
                    usage_info.is_quaternion and int(getattr(track, "buffer_type", 0)) in {7, 11, 12, 13, 14, 15}
                ),
            )
        )

    resolved_name = action_name
    if resolved_name is None:
        resolved_name = f"LMT::{int(getattr(decoded_action, 'action_id', 0))}"

    return LmtReconstructedAction(
        action_name=str(resolved_name),
        frame_start=0,
        frame_end=int(getattr(decoded_action, "frame_count", 0)),
        tracks=tuple(reconstructed_tracks),
    )
