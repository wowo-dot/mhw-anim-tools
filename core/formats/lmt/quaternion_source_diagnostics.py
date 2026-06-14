"""Diagnostics for source quaternion tracks whose raw magnitudes matter.

Some source quaternion lerp buffers decode to non-unit explicit key values.
Blender preserves those raw curve components on import, but generic normalized
reconstruction cannot always recover the same sparse raw-key structure from
motion-equivalent samples alone.
"""

from __future__ import annotations

from ...animation.transforms import quaternion_norm_squared_wxyz
from .semantics import get_usage_semantics


QUATERNION_LERP_BUFFER_TYPES = frozenset({7, 11, 12, 13, 14, 15})


def _track_quaternion_values(decoded_track):
    values = [tuple(float(component) for component in decoded_track.basis_value)]
    values.extend(tuple(float(component) for component in sample.value) for sample in decoded_track.keyframes)
    if decoded_track.tail_value is not None:
        values.append(tuple(float(component) for component in decoded_track.tail_value))
    return tuple(values)


def identify_raw_sensitive_quaternion_identities(
    decoded_action,
    *,
    tolerance: float = 1e-3,
) -> frozenset[tuple[int, int]]:
    identities: set[tuple[int, int]] = set()
    lower_bound = (1.0 - float(tolerance)) ** 2
    upper_bound = (1.0 + float(tolerance)) ** 2
    for track in decoded_action.tracks:
        usage = get_usage_semantics(track.usage)
        if not usage.is_quaternion:
            continue
        if int(track.buffer_type) not in QUATERNION_LERP_BUFFER_TYPES:
            continue
        if track.decode_error:
            continue
        for value in _track_quaternion_values(track):
            norm_squared = quaternion_norm_squared_wxyz(value)
            if norm_squared < lower_bound or norm_squared > upper_bound:
                identities.add((int(track.bone_id), int(track.usage)))
                break
    return frozenset(identities)
