"""Conservative export planning for reconstructed LMT actions.

This layer intentionally stops short of binary writing. It answers:
- which LMT buffer family each reconstructed track would target
- whether the current sparse action shape is plannable
- what writer-side caveats still need to be handled explicitly
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import math

from .encoding import analyze_quaternion_lerp_track
from .encoding import analyze_vector_lerp_track
from .encoding import coerce_lerp_basis
from .encoding import quaternion_lerp_promotion_candidates
from .encoding import QUATERNION_LERP_DEFAULT_TOLERANCE
from .encoding import VECTOR_LERP_DEFAULT_TOLERANCE
from .semantics import get_buffer_semantics
from .semantics import get_usage_semantics


@dataclass(frozen=True)
class LmtExportPlanDiagnostic:
    level: str
    source: str
    message: str


@dataclass(frozen=True)
class LmtExportPlannedTrack:
    bone_id: int
    usage: int
    buffer_type: int | None
    buffer_code: str
    buffer_label: str
    keyframe_count: int
    tail_in_action_header: bool
    inject_leading_basis_keyframe: bool
    supported: bool
    preserve_source_raw: bool = False
    notes: tuple[str, ...] = ()
    lerp_mult: tuple[float, float, float, float] | None = None
    lerp_add: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class LmtExportPlan:
    action_name: str
    frame_start: int
    frame_end: int
    tracks: tuple[LmtExportPlannedTrack, ...] = ()
    diagnostics: tuple[LmtExportPlanDiagnostic, ...] = ()

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def supported_track_count(self) -> int:
        return sum(1 for track in self.tracks if track.supported)

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")

    @property
    def buffer_breakdown(self) -> str:
        counts = Counter(track.buffer_code for track in self.tracks if track.supported and track.buffer_code)
        if not counts:
            return ""
        return ", ".join(f"{count} {code}" for code, count in sorted(counts.items()))


def _track_source_label(track) -> str:
    source_track_index = getattr(track, "source_track_index", None)
    usage = get_usage_semantics(track.usage)
    if usage.scope == "root":
        label = f"root {usage.transform}"
    else:
        label = f"bone {track.bone_id} {usage.transform}"
    if source_track_index is None:
        return label
    return f"track {int(source_track_index):02d} / {label}"


def _all_values(track) -> list[tuple[float, ...]]:
    values = [tuple(float(component) for component in track.basis_value)]
    values.extend(tuple(float(component) for component in key.value) for key in track.keyframes)
    if track.tail_value is not None:
        values.append(tuple(float(component) for component in track.tail_value))
    return values


def _has_only_finite_values(track) -> bool:
    for value in _all_values(track):
        for component in value:
            if not math.isfinite(float(component)):
                return False
    return True


def _has_expected_value_dimensions(track, usage_info) -> bool:
    expected_size = 4 if usage_info.is_quaternion else 3
    if len(track.basis_value) != expected_size:
        return False
    for key in track.keyframes:
        if len(key.value) != expected_size:
            return False
    if track.tail_value is not None and len(track.tail_value) != expected_size:
        return False
    return True


def _has_normalized_quaternion_values(track, tolerance: float) -> bool:
    for value in _all_values(track):
        norm_squared = sum(float(component) * float(component) for component in value)
        if norm_squared <= 0.0:
            return False
        if abs(1.0 - math.sqrt(norm_squared)) > tolerance:
            return False
    return True


def _choose_buffer_type(track, usage_info) -> int | None:
    if usage_info.transform in {"translation", "scale"}:
        return 3 if track.keyframes else 1
    if usage_info.is_quaternion:
        return 6 if track.keyframes else 2
    return None


def _source_track_metadata(track, track_metadata_by_identity, track_metadata_by_index):
    source_track_index = getattr(track, "source_track_index", None)
    if source_track_index is not None and track_metadata_by_index:
        metadata = track_metadata_by_index.get(int(source_track_index))
        if metadata is not None:
            return metadata
    if not track_metadata_by_identity:
        return None
    return track_metadata_by_identity.get((int(track.bone_id), int(track.usage)))


def _resolve_vector_lerp_preference(
    track,
    *,
    source_label: str,
    action_frame_count: int,
    track_metadata,
    tolerance: float,
) -> tuple[int, tuple[float, float, float, float] | None, tuple[float, float, float, float] | None, tuple[str, ...], tuple[LmtExportPlanDiagnostic, ...]]:
    if not track.keyframes or not track_metadata:
        return 3, None, None, (), ()

    try:
        preferred_buffer_type = int(track_metadata.get("buffer_type"))
    except (AttributeError, TypeError, ValueError):
        preferred_buffer_type = None
    if preferred_buffer_type not in {4, 5}:
        return 3, None, None, (), ()

    lerp_mult = coerce_lerp_basis(track_metadata.get("lerp_mult"))
    lerp_add = coerce_lerp_basis(track_metadata.get("lerp_add"))
    if lerp_mult is None or lerp_add is None:
        return (
            3,
            None,
            None,
            (),
            (
                LmtExportPlanDiagnostic(
                    "WARNING",
                    source_label,
                    "Source vector lerp metadata was incomplete; falling back to float vector keys.",
                ),
            ),
        )

    fit, _max_error, reason = analyze_vector_lerp_track(
        track,
        buffer_type=preferred_buffer_type,
        lerp_mult=lerp_mult,
        lerp_add=lerp_add,
        terminal_frame=action_frame_count + 1,
        tolerance=tolerance,
    )
    if fit:
        return (
            preferred_buffer_type,
            lerp_mult,
            lerp_add,
            ("Using source vector lerp basis.",),
            (),
        )

    if preferred_buffer_type == 5:
        fit_16, _max_error_16, reason_16 = analyze_vector_lerp_track(
            track,
            buffer_type=4,
            lerp_mult=lerp_mult,
            lerp_add=lerp_add,
            terminal_frame=action_frame_count + 1,
            tolerance=tolerance,
        )
        if fit_16:
            return (
                4,
                lerp_mult,
                lerp_add,
                ("Using source vector lerp basis.", "Promoted source 8-bit vector lerp to 16-bit lerp."),
                (
                    LmtExportPlanDiagnostic(
                        "WARNING",
                        source_label,
                        f"Source 8-bit vector lerp no longer fits cleanly ({reason}); exporting as 16-bit vector lerp instead.",
                    ),
                ),
            )
        reason = reason_16 or reason

    return (
        3,
        None,
        None,
        (),
        (
            LmtExportPlanDiagnostic(
                "WARNING",
                source_label,
                f"Source vector lerp basis no longer fits edited values ({reason}); falling back to float vector keys.",
            ),
        ),
    )


def _resolve_quaternion_lerp_preference(
    track,
    *,
    source_label: str,
    action_frame_count: int,
    track_metadata,
    tolerance: float,
) -> tuple[int, tuple[float, float, float, float] | None, tuple[float, float, float, float] | None, tuple[str, ...], tuple[LmtExportPlanDiagnostic, ...]]:
    if not track.keyframes or not track_metadata:
        return 6, None, None, (), ()

    try:
        preferred_buffer_type = int(track_metadata.get("buffer_type"))
    except (AttributeError, TypeError, ValueError):
        preferred_buffer_type = None
    if preferred_buffer_type not in {7, 11, 12, 13, 14, 15}:
        return 6, None, None, (), ()

    lerp_mult = coerce_lerp_basis(track_metadata.get("lerp_mult"))
    lerp_add = coerce_lerp_basis(track_metadata.get("lerp_add"))
    if lerp_mult is None or lerp_add is None:
        return (
            6,
            None,
            None,
            (),
            (
                LmtExportPlanDiagnostic(
                    "WARNING",
                    source_label,
                    "Source quaternion lerp metadata was incomplete; falling back to q14 quaternion keys.",
                ),
            ),
        )

    candidate_types = quaternion_lerp_promotion_candidates(preferred_buffer_type)
    first_reason = None
    for candidate_type in candidate_types:
        fit, _max_error, reason = analyze_quaternion_lerp_track(
            track,
            buffer_type=candidate_type,
            lerp_mult=lerp_mult,
            lerp_add=lerp_add,
            terminal_frame=action_frame_count + 1,
            tolerance=tolerance,
        )
        if fit:
            if candidate_type == preferred_buffer_type:
                return (
                    candidate_type,
                    lerp_mult,
                    lerp_add,
                    ("Using source quaternion lerp basis.",),
                    (),
                )
            promoted_label = get_buffer_semantics(candidate_type).label
            source_label_text = get_buffer_semantics(preferred_buffer_type).label
            return (
                candidate_type,
                lerp_mult,
                lerp_add,
                ("Using source quaternion lerp basis.", f"Promoted source {source_label_text.lower()} to {promoted_label.lower()}."),
                (
                    LmtExportPlanDiagnostic(
                        "WARNING",
                        source_label,
                        f"Source {source_label_text.lower()} no longer fits cleanly ({first_reason or reason}); exporting as {promoted_label.lower()} instead.",
                    ),
                ),
            )
        if first_reason is None:
            first_reason = reason

    return (
        6,
        None,
        None,
        (),
        (
            LmtExportPlanDiagnostic(
                "WARNING",
                source_label,
                f"Source quaternion lerp basis no longer fits edited values ({first_reason}); falling back to q14 quaternion keys.",
            ),
        ),
    )


def _build_track_notes(track, usage_info) -> list[str]:
    notes: list[str] = []
    if track.keyframes and track.keyframes[0].frame > 1:
        notes.append("Writer must inject a leading hold key at frame 1.")
    if usage_info.scope == "root" and usage_info.transform != "scale" and track.tail_frame is not None:
        notes.append("Tail value must be written to the action header.")
    return notes


def resolve_action_frame_count(reconstructed_action) -> int:
    """Match writer duration semantics during analyze/export planning."""
    frame_count = 0
    has_explicit_duration = False
    for track in reconstructed_action.tracks:
        if track.keyframes:
            has_explicit_duration = True
            frame_count = max(frame_count, max(int(key.frame) for key in track.keyframes))
        if track.tail_frame is not None:
            has_explicit_duration = True
            frame_count = max(frame_count, int(track.tail_frame) - 1)
    if not has_explicit_duration:
        frame_count = max(frame_count, int(reconstructed_action.frame_end))
    return frame_count


def _max_encoded_delta(track, terminal_frame: int) -> int:
    frames = [int(key.frame) for key in track.keyframes]
    if not frames:
        return 0
    if frames[0] > 1:
        frames.insert(0, 1)
    max_delta = 0
    for index, frame in enumerate(frames):
        next_frame = frames[index + 1] if index + 1 < len(frames) else int(terminal_frame)
        max_delta = max(max_delta, int(next_frame) - int(frame))
    return max_delta


def plan_reconstructed_action_export(
    reconstructed_action,
    *,
    quaternion_tolerance: float = 1e-3,
    quaternion_lerp_tolerance: float = QUATERNION_LERP_DEFAULT_TOLERANCE,
    vector_lerp_tolerance: float = VECTOR_LERP_DEFAULT_TOLERANCE,
    track_metadata_by_identity: dict[tuple[int, int], dict[str, object]] | None = None,
    track_metadata_by_index: dict[int, dict[str, object]] | None = None,
    preserve_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] | None = None,
    raw_quaternion_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] | None = None,
) -> LmtExportPlan:
    diagnostics: list[LmtExportPlanDiagnostic] = []
    planned_tracks: list[LmtExportPlannedTrack] = []
    action_frame_count = resolve_action_frame_count(reconstructed_action)
    raw_quaternion_source_identities = frozenset(raw_quaternion_source_identities or ())
    duplicate_identities = {
        identity
        for identity, count in Counter((int(track.bone_id), int(track.usage)) for track in reconstructed_action.tracks).items()
        if count > 1
    }
    for track in reconstructed_action.tracks:
        usage_info = get_usage_semantics(track.usage)
        source_label = _track_source_label(track)
        notes = _build_track_notes(track, usage_info)
        supported = True
        preserve_source_raw = False
        lerp_mult = None
        lerp_add = None
        track_identity = (int(track.bone_id), int(track.usage))
        raw_quaternion_source = bool(getattr(track, "preserve_raw_quaternion_values", False)) or (
            track_identity in raw_quaternion_source_identities
        )
        track_metadata = _source_track_metadata(track, track_metadata_by_identity, track_metadata_by_index)

        if usage_info.transform not in {"rotation", "translation", "scale"}:
            supported = False
            diagnostics.append(
                LmtExportPlanDiagnostic("ERROR", source_label, f"Unsupported track usage {track.usage}.")
            )

        if not _has_only_finite_values(track):
            supported = False
            diagnostics.append(
                LmtExportPlanDiagnostic("ERROR", source_label, "Track contains non-finite values.")
            )

        if not _has_expected_value_dimensions(track, usage_info):
            supported = False
            expected_size = 4 if usage_info.is_quaternion else 3
            diagnostics.append(
                LmtExportPlanDiagnostic(
                    "ERROR",
                    source_label,
                    f"Track values must have {expected_size} component(s) for {usage_info.transform} usage.",
                )
            )

        if usage_info.scope == "local" and track.tail_frame is not None:
            supported = False
            diagnostics.append(
                LmtExportPlanDiagnostic("ERROR", source_label, "Local tracks cannot use action-header tail values.")
            )
        if usage_info.transform == "scale" and track.tail_frame is not None:
            supported = False
            diagnostics.append(
                LmtExportPlanDiagnostic("ERROR", source_label, "Scale tracks cannot use action-header tail values.")
            )

        if usage_info.is_quaternion and not _has_normalized_quaternion_values(track, quaternion_tolerance):
            if raw_quaternion_source:
                notes.append("Using raw source-aware quaternion key values.")
            else:
                supported = False
                diagnostics.append(
                    LmtExportPlanDiagnostic(
                        "ERROR",
                        source_label,
                        "Quaternion samples are not normalized closely enough for planning.",
                    )
                )

        if raw_quaternion_source and track_metadata is None:
            supported = False
            diagnostics.append(
                LmtExportPlanDiagnostic(
                    "ERROR",
                    source_label,
                    "Source-aware raw quaternion reconstruction requires source track metadata.",
                )
            )

        for previous, current in zip(track.keyframes, track.keyframes[1:]):
            if int(current.frame) <= int(previous.frame):
                supported = False
                diagnostics.append(
                    LmtExportPlanDiagnostic(
                        "ERROR",
                        source_label,
                        "Track keyframes must be strictly increasing.",
                    )
                )
                break

        if track_identity in duplicate_identities:
            source_track_index = getattr(track, "source_track_index", None)
            if source_track_index is None:
                supported = False
                diagnostics.append(
                    LmtExportPlanDiagnostic(
                        "ERROR",
                        source_label,
                        "Duplicate track identity detected without source track-slot metadata.",
                    )
                )
            elif sum(
                1
                for candidate in reconstructed_action.tracks
                if getattr(candidate, "source_track_index", None) == source_track_index
            ) > 1:
                supported = False
                diagnostics.append(
                    LmtExportPlanDiagnostic(
                        "ERROR",
                        source_label,
                        f"Source track slot {int(source_track_index):02d} was mapped more than once.",
                    )
                )

        buffer_type = _choose_buffer_type(track, usage_info)
        if supported and track_metadata and preserve_source_identities and track_identity in preserve_source_identities:
            preserve_source_raw = True
            try:
                buffer_type = int(track_metadata.get("buffer_type"))
            except (AttributeError, TypeError, ValueError):
                buffer_type = _choose_buffer_type(track, usage_info)
            lerp_mult = coerce_lerp_basis(track_metadata.get("lerp_mult"))
            lerp_add = coerce_lerp_basis(track_metadata.get("lerp_add"))
            notes.append("Preserving raw source track data for an unchanged track.")
        if supported and usage_info.transform in {"translation", "scale"} and track.keyframes:
            if not preserve_source_raw:
                (
                    buffer_type,
                    lerp_mult,
                    lerp_add,
                    vector_notes,
                    vector_diagnostics,
                ) = _resolve_vector_lerp_preference(
                    track,
                    source_label=source_label,
                    action_frame_count=action_frame_count,
                    track_metadata=track_metadata,
                    tolerance=vector_lerp_tolerance,
                )
                notes.extend(vector_notes)
                diagnostics.extend(vector_diagnostics)
        if supported and usage_info.is_quaternion and track.keyframes:
            if not preserve_source_raw:
                (
                    buffer_type,
                    lerp_mult,
                    lerp_add,
                    quaternion_notes,
                    quaternion_diagnostics,
                ) = _resolve_quaternion_lerp_preference(
                    track,
                    source_label=source_label,
                    action_frame_count=action_frame_count,
                    track_metadata=track_metadata,
                    tolerance=quaternion_lerp_tolerance,
                )
                notes.extend(quaternion_notes)
                if raw_quaternion_source and buffer_type == 6:
                    supported = False
                    diagnostics.append(
                        LmtExportPlanDiagnostic(
                            "ERROR",
                            source_label,
                            "Raw source-aware quaternion values no longer fit a source quaternion lerp basis; refusing normalized q14 fallback.",
                        )
                    )
                else:
                    diagnostics.extend(quaternion_diagnostics)
        if supported and not preserve_source_raw and buffer_type == 6:
            required_delta = _max_encoded_delta(track, action_frame_count + 1)
            if required_delta > 255:
                supported = False
                diagnostics.append(
                    LmtExportPlanDiagnostic(
                        "ERROR",
                        source_label,
                        f"q14 quaternion export needs a frame delta of {required_delta}, which exceeds the 255-frame limit.",
                    )
                )
        buffer_info = get_buffer_semantics(buffer_type or -1) if buffer_type is not None else None
        planned_tracks.append(
            LmtExportPlannedTrack(
                bone_id=int(track.bone_id),
                usage=int(track.usage),
                buffer_type=buffer_type,
                buffer_code=buffer_info.code if buffer_info is not None else "",
                buffer_label=buffer_info.label if buffer_info is not None else "Unsupported",
                keyframe_count=len(track.keyframes),
                tail_in_action_header=bool(track.tail_frame is not None and track.tail_value is not None),
                inject_leading_basis_keyframe=bool(track.keyframes and track.keyframes[0].frame > 1),
                supported=supported and buffer_type is not None,
                preserve_source_raw=preserve_source_raw,
                notes=tuple(notes),
                lerp_mult=lerp_mult,
                lerp_add=lerp_add,
            )
        )

    return LmtExportPlan(
        action_name=reconstructed_action.action_name,
        frame_start=int(reconstructed_action.frame_start),
        frame_end=int(reconstructed_action.frame_end),
        tracks=tuple(planned_tracks),
        diagnostics=tuple(diagnostics),
    )
