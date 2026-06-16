"""Small transform helpers shared by the decoder and Blender adapter.

Quaternion convention:
- Raw LMT float tuples are interpreted as XYZW when read from file structures.
- Decoded quaternions exposed by `core/` are always WXYZ.
- Blender-facing code should consume only the decoded WXYZ convention.
"""

from __future__ import annotations

import math


QUATERNION_EPSILON = 1e-12
MHW_UNIT_SCALE = 0.01
MHW_OBJECT_ROTATION_WXYZ = (
    math.sqrt(0.5),
    math.sqrt(0.5),
    0.0,
    0.0,
)


def xyzw_to_wxyz(values: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x, y, z, w = values
    return (float(w), float(x), float(y), float(z))


def wxyz_to_xyzw(values: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    w, x, y, z = values
    return (float(x), float(y), float(z), float(w))


def quaternion_dot_wxyz(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    return sum(float(l_component) * float(r_component) for l_component, r_component in zip(left, right))


def quaternion_norm_squared_wxyz(values: tuple[float, float, float, float]) -> float:
    return quaternion_dot_wxyz(values, values)


def normalize_quaternion_wxyz(values: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    norm_squared = quaternion_norm_squared_wxyz(values)
    if norm_squared <= QUATERNION_EPSILON:
        return tuple(float(component) for component in values)
    norm = math.sqrt(norm_squared)
    return tuple(float(component) / norm for component in values)


def flip_quaternion_wxyz(values: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return tuple(-float(component) for component in values)


def nlerp_quaternion_wxyz(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    blend: float,
) -> tuple[float, float, float, float]:
    current_left = normalize_quaternion_wxyz(left)
    current_right = normalize_quaternion_wxyz(right)
    if quaternion_dot_wxyz(current_left, current_right) < 0.0:
        current_right = flip_quaternion_wxyz(current_right)
    mixed = tuple(
        ((1.0 - float(blend)) * float(left_component)) + (float(blend) * float(right_component))
        for left_component, right_component in zip(current_left, current_right)
    )
    return normalize_quaternion_wxyz(mixed)


def quaternion_conjugate_wxyz(values: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    w, x, y, z = values
    return (float(w), -float(x), -float(y), -float(z))


def quaternion_inverse_wxyz(values: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    norm_squared = quaternion_norm_squared_wxyz(values)
    if norm_squared <= QUATERNION_EPSILON:
        return quaternion_conjugate_wxyz(values)
    conjugate = quaternion_conjugate_wxyz(values)
    return tuple(float(component) / norm_squared for component in conjugate)


def quaternion_multiply_wxyz(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return (
        (lw * rw) - (lx * rx) - (ly * ry) - (lz * rz),
        (lw * rx) + (lx * rw) + (ly * rz) - (lz * ry),
        (lw * ry) - (lx * rz) + (ly * rw) + (lz * rx),
        (lw * rz) + (lx * ry) - (ly * rx) + (lz * rw),
    )


def rotate_vector_by_quaternion_wxyz(
    vector: tuple[float, float, float],
    rotation: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    pure = (0.0, float(vector[0]), float(vector[1]), float(vector[2]))
    inverse = quaternion_inverse_wxyz(rotation)
    rotated = quaternion_multiply_wxyz(quaternion_multiply_wxyz(rotation, pure), inverse)
    return (float(rotated[1]), float(rotated[2]), float(rotated[3]))


def scale_vector_xyz(values: tuple[float, float, float], factor: float) -> tuple[float, float, float]:
    return tuple(float(component) * float(factor) for component in values)


def subtract_vector_xyz(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple(float(l_component) - float(r_component) for l_component, r_component in zip(left, right))


def transform_mhw_object_translation(values: tuple[float, float, float]) -> tuple[float, float, float]:
    scaled = scale_vector_xyz(values, MHW_UNIT_SCALE)
    return rotate_vector_by_quaternion_wxyz(scaled, MHW_OBJECT_ROTATION_WXYZ)


def transform_blender_object_translation_to_mhw(values: tuple[float, float, float]) -> tuple[float, float, float]:
    rotated = rotate_vector_by_quaternion_wxyz(values, quaternion_inverse_wxyz(MHW_OBJECT_ROTATION_WXYZ))
    inverse_scale = 1.0 / MHW_UNIT_SCALE
    return scale_vector_xyz(rotated, inverse_scale)


def transform_mhw_pose_translation_to_delta(
    values: tuple[float, float, float],
    rest_local_translation: tuple[float, float, float],
) -> tuple[float, float, float]:
    scaled = scale_vector_xyz(values, MHW_UNIT_SCALE)
    return subtract_vector_xyz(scaled, rest_local_translation)


def transform_blender_pose_translation_delta_to_mhw(
    values: tuple[float, float, float],
    rest_local_translation: tuple[float, float, float],
) -> tuple[float, float, float]:
    absolute = tuple(float(value) + float(baseline) for value, baseline in zip(values, rest_local_translation))
    inverse_scale = 1.0 / MHW_UNIT_SCALE
    return scale_vector_xyz(absolute, inverse_scale)


def transform_mhw_object_quaternion_wxyz(
    values: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    current = normalize_quaternion_wxyz(values)
    transformed = quaternion_multiply_wxyz(
        quaternion_multiply_wxyz(MHW_OBJECT_ROTATION_WXYZ, current),
        quaternion_inverse_wxyz(MHW_OBJECT_ROTATION_WXYZ),
    )
    return normalize_quaternion_wxyz(transformed)


def transform_blender_object_quaternion_to_mhw_wxyz(
    values: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    current = normalize_quaternion_wxyz(values)
    inverse_basis = quaternion_inverse_wxyz(MHW_OBJECT_ROTATION_WXYZ)
    transformed = quaternion_multiply_wxyz(
        quaternion_multiply_wxyz(inverse_basis, current),
        MHW_OBJECT_ROTATION_WXYZ,
    )
    return normalize_quaternion_wxyz(transformed)


def canonicalize_quaternion_frames_wxyz(
    frames: list[tuple[float, tuple[float, float, float, float]]],
    *,
    normalize: bool = False,
) -> list[tuple[float, tuple[float, float, float, float]]]:
    """Pick a consistent q/-q representative for neighboring WXYZ keys."""

    canonical_frames: list[tuple[float, tuple[float, float, float, float]]] = []
    previous: tuple[float, float, float, float] | None = None
    for timing, quaternion in frames:
        current = tuple(float(component) for component in quaternion)
        compare = normalize_quaternion_wxyz(current)
        if quaternion_norm_squared_wxyz(compare) > QUATERNION_EPSILON:
            if previous is not None and quaternion_dot_wxyz(previous, compare) < 0:
                current = flip_quaternion_wxyz(current)
                compare = flip_quaternion_wxyz(compare)
            previous = compare
            if normalize:
                current = compare
        canonical_frames.append((timing, current))
    return canonical_frames
