"""Sample Blender Actions back into normalized MHW-oriented track values.

This is the reverse-path companion to the import adapter:
- the core decoder stays engine-oriented
- Blender actions/fcurves are sampled here
- MHW_Model_Editor-specific pose/object basis conversion happens only at this boundary
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re

try:
    from ..core.animation.transforms import canonicalize_quaternion_frames_wxyz
    from ..core.animation.transforms import normalize_quaternion_wxyz
    from ..core.animation.transforms import quaternion_norm_squared_wxyz
    from ..core.animation.transforms import QUATERNION_EPSILON
    from ..core.formats.lmt.semantics import get_usage_semantics
    from ..integration.mhw_bones import bone_index_from_name
    from ..integration.mhw_bones import bonefunction_index_from_name
    from ..integration.mhw_bones import is_bonefunction_name
    from ..integration.mhw_bones import is_mhbone_name
    from .armature import find_root_bone_name
    from .space import TrackSpaceTarget
    from .space import adapt_track_frames_for_export_space
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.animation.transforms import canonicalize_quaternion_frames_wxyz
    from core.animation.transforms import normalize_quaternion_wxyz
    from core.animation.transforms import quaternion_norm_squared_wxyz
    from core.animation.transforms import QUATERNION_EPSILON
    from core.formats.lmt.semantics import get_usage_semantics
    from integration.mhw_bones import bone_index_from_name
    from integration.mhw_bones import bonefunction_index_from_name
    from integration.mhw_bones import is_bonefunction_name
    from integration.mhw_bones import is_mhbone_name
    from blender_adapter.armature import find_root_bone_name
    from blender_adapter.space import TrackSpaceTarget
    from blender_adapter.space import adapt_track_frames_for_export_space


POSE_BONE_PATH = re.compile(r'^pose\.bones\["(?P<name>.+)"\]\.(?P<transform>rotation_quaternion|location|scale)$')
OBJECT_TRANSFORMS = {"rotation_quaternion": 4, "location": 3, "scale": 3}
USAGE_BY_SCOPE_AND_TRANSFORM = {
    ("local", "rotation_quaternion"): 0,
    ("local", "location"): 1,
    ("local", "scale"): 2,
    ("root", "rotation_quaternion"): 3,
    ("root", "location"): 4,
    ("root", "scale"): 5,
}
CHANNEL_COUNT_BY_TRANSFORM = {"rotation_quaternion": 4, "location": 3, "scale": 3}


@dataclass(frozen=True)
class ExportDiagnostic:
    level: str
    source: str
    message: str


@dataclass(frozen=True)
class SampledActionFrame:
    frame: int
    value: tuple[float, ...]


@dataclass(frozen=True)
class SampledActionTrack:
    bone_id: int
    usage: int
    source_kind: str
    source_name: str
    transform: str
    channel_count: int
    frames: tuple[SampledActionFrame, ...]
    raw_frames: tuple[SampledActionFrame, ...] = ()
    authored_frames: tuple[int, ...] = ()
    all_authored_keys_linear: bool = True
    authored_frame_end: int | None = None

    @property
    def basis_value(self) -> tuple[float, ...]:
        return self.frames[0].value if self.frames else ()


@dataclass
class ExportSamplingResult:
    action_name: str = ""
    frame_start: int = 0
    frame_end: int = 0
    sampled_track_count: int = 0
    skipped_track_count: int = 0
    sampled_tracks: tuple[SampledActionTrack, ...] = ()
    diagnostics: list[ExportDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(ExportDiagnostic(level=level, source=source, message=message))

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")


def _default_sample_frames(action) -> tuple[int, ...]:
    frame_range = getattr(action, "frame_range", (0.0, 0.0))
    frame_end = max(0, int(math.ceil(float(frame_range[1]))))
    return tuple(range(0, frame_end + 1))


def _normalized_sample_frames(sample_frames) -> tuple[int, ...]:
    if sample_frames is None:
        return ()
    normalized = sorted({max(0, int(frame)) for frame in sample_frames})
    if 0 not in normalized:
        normalized.insert(0, 0)
    return tuple(normalized)


def _parse_fcurve_path(data_path: str):
    if data_path in OBJECT_TRANSFORMS:
        return ("object", "", data_path)
    match = POSE_BONE_PATH.match(data_path or "")
    if not match:
        return None
    return ("bone", match.group("name"), match.group("transform"))


def _collect_supported_groups(action):
    groups: dict[tuple[str, str, str], dict[int, object]] = {}
    unsupported_paths: list[str] = []
    for fcurve in getattr(action, "fcurves", ()):
        parsed = _parse_fcurve_path(getattr(fcurve, "data_path", ""))
        if parsed is None:
            unsupported_paths.append(getattr(fcurve, "data_path", ""))
            continue
        source_kind, source_name, transform = parsed
        group_key = (source_kind, source_name, transform)
        channel_map = groups.setdefault(group_key, {})
        channel_map[int(fcurve.array_index)] = fcurve
    return groups, tuple(sorted(set(filter(None, unsupported_paths))))


def _infer_track_identity(armature_object, source_kind: str, source_name: str, transform: str):
    if source_kind == "object":
        return -1, USAGE_BY_SCOPE_AND_TRANSFORM[("root", transform)], None

    root_bone_name = find_root_bone_name(armature_object)
    if root_bone_name is not None and source_name == root_bone_name:
        return -1, USAGE_BY_SCOPE_AND_TRANSFORM[("root", transform)], None

    if is_mhbone_name(source_name):
        bone_id = bone_index_from_name(source_name)
        return bone_id, USAGE_BY_SCOPE_AND_TRANSFORM[("local", transform)], None
    if is_bonefunction_name(source_name):
        bone_id = bonefunction_index_from_name(source_name)
        return bone_id, USAGE_BY_SCOPE_AND_TRANSFORM[("local", transform)], None
    return None, None, f"Unsupported export source bone '{source_name}'."


def _sample_channel_group(channel_map, frame_numbers: tuple[int, ...], channel_count: int):
    sampled_frames = []
    for frame in frame_numbers:
        value = tuple(float(channel_map[index].evaluate(frame)) for index in range(channel_count))
        sampled_frames.append((float(frame), value))
    return sampled_frames


def _authored_frames(channel_map) -> tuple[int, ...]:
    authored_frames: list[int] = []
    for fcurve in channel_map.values():
        for point in getattr(fcurve, "keyframe_points", ()):
            co = getattr(point, "co", None)
            if co is None:
                continue
            try:
                authored_frames.append(max(0, int(round(float(co[0])))))
            except (TypeError, ValueError, IndexError):
                continue
    if not authored_frames:
        return ()
    normalized = sorted(set(authored_frames))
    if 0 not in normalized:
        normalized.insert(0, 0)
    return tuple(normalized)


def _authored_frame_end(authored_frames: tuple[int, ...]) -> int | None:
    if not authored_frames:
        return None
    return int(authored_frames[-1])


def _all_keyframes_linear(channel_map) -> bool:
    for fcurve in channel_map.values():
        for point in getattr(fcurve, "keyframe_points", ()):
            if getattr(point, "interpolation", "LINEAR") != "LINEAR":
                return False
    return True


def _normalize_quaternion_frames(
    frame_values,
    *,
    source_label: str,
    result: ExportSamplingResult,
):
    normalized = []
    for frame, value in frame_values:
        quaternion = tuple(float(component) for component in value)
        if quaternion_norm_squared_wxyz(quaternion) <= QUATERNION_EPSILON:
            result.add(
                "ERROR",
                source_label,
                f"Skipped quaternion track at frame {int(frame)} because it evaluated to a zero-length quaternion.",
            )
            return None
        normalized.append((float(frame), normalize_quaternion_wxyz(quaternion)))
    return canonicalize_quaternion_frames_wxyz(normalized, normalize=True)


def sample_action_for_lmt_export(action, armature_object, *, sample_frames=None) -> ExportSamplingResult:
    result = ExportSamplingResult()
    if action is None:
        result.add("ERROR", "action", "Choose a Blender Action before sampling export data.")
        return result
    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        result.add("ERROR", "armature", "Choose a target armature before sampling export data.")
        return result

    frame_numbers = _normalized_sample_frames(sample_frames) or _default_sample_frames(action)
    result.action_name = getattr(action, "name", "")
    result.frame_start = frame_numbers[0] if frame_numbers else 0
    result.frame_end = frame_numbers[-1] if frame_numbers else 0

    grouped_fcurves, unsupported_paths = _collect_supported_groups(action)
    for path in unsupported_paths:
        result.add("WARNING", "fcurve", f"Skipped unsupported data path '{path}'.")

    sampled_tracks: list[SampledActionTrack] = []
    for (source_kind, source_name, transform), channel_map in sorted(grouped_fcurves.items()):
        channel_count = CHANNEL_COUNT_BY_TRANSFORM[transform]
        source_label = source_name or "Armature Object"
        if set(channel_map) != set(range(channel_count)):
            result.skipped_track_count += 1
            result.add(
                "WARNING",
                source_label,
                f"Skipped incomplete {transform} channels; expected {channel_count}, found {len(channel_map)}.",
            )
            continue

        bone_id, usage, error = _infer_track_identity(armature_object, source_kind, source_name, transform)
        if error:
            result.skipped_track_count += 1
            result.add("WARNING", source_label, error)
            continue

        usage_info = get_usage_semantics(usage)
        sampled_frame_values = _sample_channel_group(channel_map, frame_numbers, channel_count)
        target = TrackSpaceTarget(kind=source_kind, name=source_name)
        sampled_frame_values = adapt_track_frames_for_export_space(
            armature_object,
            target,
            usage_info,
            sampled_frame_values,
        )
        raw_sampled_frame_values = sampled_frame_values
        if usage_info.is_quaternion:
            sampled_frame_values = _normalize_quaternion_frames(
                sampled_frame_values,
                source_label=source_label,
                result=result,
            )
            if sampled_frame_values is None:
                result.skipped_track_count += 1
                continue
        authored_frames = _authored_frames(channel_map)

        sampled_tracks.append(
            SampledActionTrack(
                bone_id=int(bone_id),
                usage=int(usage),
                source_kind=source_kind,
                source_name=source_name,
                transform=transform,
                channel_count=channel_count,
                frames=tuple(
                    SampledActionFrame(frame=int(frame), value=tuple(float(component) for component in value))
                    for frame, value in sampled_frame_values
                ),
                raw_frames=tuple(
                    SampledActionFrame(frame=int(frame), value=tuple(float(component) for component in value))
                    for frame, value in raw_sampled_frame_values
                ) if usage_info.is_quaternion else (),
                authored_frames=authored_frames,
                all_authored_keys_linear=_all_keyframes_linear(channel_map),
                authored_frame_end=_authored_frame_end(authored_frames),
            )
        )

    result.sampled_track_count = len(sampled_tracks)
    result.sampled_tracks = tuple(sampled_tracks)
    if result.sampled_track_count == 0 and not result.error_count:
        result.add("ERROR", "export", "No supported tracks were sampled from the selected action.")
    return result
