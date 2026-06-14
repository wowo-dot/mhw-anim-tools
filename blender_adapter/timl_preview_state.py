"""Track imported TIML preview state so export can preserve untouched source data.

Imported TIML controller actions are sometimes only an approximation of the
source payload, especially when the original TIML used interpolation/easing
semantics Blender cannot represent directly on the preview curves. We therefore
store the imported preview state and later compare the current controller action
against that preview, so untouched transforms can keep their original binary
representation during merge export.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math


TIML_TO_BLENDER_INTERPOLATION = {
    0: "CONSTANT",
    1: "LINEAR",
}
FLOAT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class TimlPreviewDiff:
    available: bool
    changed_identities: tuple[tuple[int, int], ...] = ()
    missing_identities: tuple[tuple[int, int], ...] = ()
    extra_identities: tuple[tuple[int, int], ...] = ()

    @property
    def edited_identities(self) -> tuple[tuple[int, int], ...]:
        return tuple(self.changed_identities) + tuple(self.extra_identities)

    @property
    def is_exact_match(self) -> bool:
        return self.available and not self.changed_identities and not self.missing_identities and not self.extra_identities


def _timl_interpolation_preview_name(code: int) -> str:
    return TIML_TO_BLENDER_INTERPOLATION.get(int(code), "LINEAR")


def _normalize_value_tuple(value) -> tuple[float, ...]:
    if isinstance(value, tuple):
        return tuple(float(component) for component in value)
    return (float(value),)


def _imported_signature_entry(transform) -> dict[str, object]:
    return {
        "type_index": int(transform.type_index),
        "transform_index": int(transform.transform_index),
        "data_type": int(transform.data_type),
        "keyframes": [
            {
                "frame": float(keyframe.frame),
                "value": [float(component) for component in _normalize_value_tuple(keyframe.value)],
                "interpolation": _timl_interpolation_preview_name(int(keyframe.interpolation)),
            }
            for keyframe in transform.keyframes
        ],
    }


def _sampled_signature_entry(transform) -> dict[str, object]:
    return {
        "type_index": int(transform.type_index),
        "transform_index": int(transform.transform_index),
        "data_type": int(transform.data_type),
        "keyframes": [
            {
                "frame": float(keyframe.frame),
                "value": [float(component) for component in keyframe.value],
                "interpolation": str(keyframe.interpolation).upper(),
            }
            for keyframe in transform.keyframes
        ],
    }


def imported_preview_signature_json(imported_transforms) -> str:
    payload = {
        "transforms": [_imported_signature_entry(transform) for transform in imported_transforms],
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _parse_signature(raw_signature) -> dict[tuple[int, int], dict[str, object]] | None:
    if not isinstance(raw_signature, str) or not raw_signature:
        return None
    try:
        decoded = json.loads(raw_signature)
    except json.JSONDecodeError:
        return None
    transforms = decoded.get("transforms")
    if not isinstance(transforms, list):
        return None
    parsed: dict[tuple[int, int], dict[str, object]] = {}
    try:
        for entry in transforms:
            if not isinstance(entry, dict):
                return None
            identity = (int(entry["type_index"]), int(entry["transform_index"]))
            parsed[identity] = entry
    except (KeyError, TypeError, ValueError):
        return None
    return parsed


def _floats_close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=FLOAT_TOLERANCE)


def _signature_entries_equal(left: dict[str, object], right: dict[str, object]) -> bool:
    if int(left.get("data_type", -1)) != int(right.get("data_type", -2)):
        return False
    left_keys = left.get("keyframes")
    right_keys = right.get("keyframes")
    if not isinstance(left_keys, list) or not isinstance(right_keys, list):
        return False
    if len(left_keys) != len(right_keys):
        return False
    for left_key, right_key in zip(left_keys, right_keys):
        if not isinstance(left_key, dict) or not isinstance(right_key, dict):
            return False
        if str(left_key.get("interpolation", "")).upper() != str(right_key.get("interpolation", "")).upper():
            return False
        if not _floats_close(float(left_key.get("frame", 0.0)), float(right_key.get("frame", 0.0))):
            return False
        left_value = left_key.get("value")
        right_value = right_key.get("value")
        if not isinstance(left_value, list) or not isinstance(right_value, list):
            return False
        if len(left_value) != len(right_value):
            return False
        for left_component, right_component in zip(left_value, right_value):
            if not _floats_close(float(left_component), float(right_component)):
                return False
    return True


def diff_sampled_transforms_from_imported_signature(raw_signature, sampled_transforms) -> TimlPreviewDiff:
    stored = _parse_signature(raw_signature)
    if stored is None:
        return TimlPreviewDiff(available=False)

    sampled_map = {
        (int(transform.type_index), int(transform.transform_index)): _sampled_signature_entry(transform)
        for transform in sampled_transforms
    }
    stored_identities = set(stored)
    sampled_identities = set(sampled_map)
    missing = tuple(sorted(stored_identities - sampled_identities))
    extra = tuple(sorted(sampled_identities - stored_identities))
    changed = tuple(
        sorted(
            identity
            for identity in sorted(stored_identities & sampled_identities)
            if not _signature_entries_equal(stored[identity], sampled_map[identity])
        )
    )
    return TimlPreviewDiff(
        available=True,
        changed_identities=changed,
        missing_identities=missing,
        extra_identities=extra,
    )
