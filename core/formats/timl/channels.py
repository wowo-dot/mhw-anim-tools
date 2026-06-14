"""Normalize parsed TIML transforms into typed sample channels."""

from __future__ import annotations

from dataclasses import dataclass

from .model import TimlData
from .semantics import get_data_type_semantics


@dataclass(frozen=True)
class TimlKeyframeSample:
    frame: float
    value: tuple[float, ...]
    interpolation: int
    easing: int


@dataclass(frozen=True)
class TimlTransformSamples:
    type_index: int
    transform_index: int
    timeline_parameter_hash: int
    datatype_hash: int
    data_type: int
    data_type_name: str
    value_kind: str
    control_kind: str
    component_labels: tuple[str, ...]
    keyframes: tuple[TimlKeyframeSample, ...]

    @property
    def component_count(self) -> int:
        return len(self.component_labels)


def _default_component_labels(value_kind: str, dimension: int) -> tuple[str, ...]:
    if dimension <= 0:
        return tuple()
    if dimension == 1:
        return ("value",)
    if value_kind == "color" and dimension == 4:
        return ("r", "g", "b", "a")
    if dimension == 2:
        return ("x", "y")
    if dimension == 3:
        return ("x", "y", "z")
    if dimension == 4:
        return ("x", "y", "z", "w")
    return tuple(f"c{index}" for index in range(dimension))


def _coerce_value_tuple(value) -> tuple[float, ...]:
    if isinstance(value, tuple):
        return tuple(float(component) for component in value)
    return (float(value),)


def build_timl_transform_samples(entry: TimlData) -> tuple[TimlTransformSamples, ...]:
    """Return a flat list of typed TIML transform samples for adapters.

    The output stays format-native:
    - scalar integer/float/bool values remain single-component samples
    - color_rgba8 values remain 4 raw 0..255 components
    - frame timings stay as floats
    """

    transforms: list[TimlTransformSamples] = []
    for type_index, type_entry in enumerate(entry.types):
        for transform_index, transform in enumerate(type_entry.transforms):
            semantics = get_data_type_semantics(transform.data_type)
            component_labels = _default_component_labels(semantics.value_kind, semantics.value_dimension)
            keyframes: list[TimlKeyframeSample] = []
            for keyframe in transform.keyframes:
                value = _coerce_value_tuple(keyframe.value)
                if component_labels and len(value) != len(component_labels):
                    raise ValueError(
                        f"TIML transform {type_index}:{transform_index} value dimension mismatch: "
                        f"expected {len(component_labels)}, got {len(value)}"
                    )
                if not component_labels:
                    component_labels = _default_component_labels(semantics.value_kind, len(value))
                keyframes.append(
                    TimlKeyframeSample(
                        frame=float(keyframe.frame_timing),
                        value=value,
                        interpolation=int(keyframe.interpolation),
                        easing=int(keyframe.easing),
                    )
                )
            transforms.append(
                TimlTransformSamples(
                    type_index=type_index,
                    transform_index=transform_index,
                    timeline_parameter_hash=int(type_entry.timeline_parameter_hash),
                    datatype_hash=int(transform.datatype_hash),
                    data_type=int(transform.data_type),
                    data_type_name=semantics.name,
                    value_kind=semantics.value_kind,
                    control_kind=semantics.control_kind,
                    component_labels=tuple(component_labels),
                    keyframes=tuple(keyframes),
                )
            )
    return tuple(transforms)
