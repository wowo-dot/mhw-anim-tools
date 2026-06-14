"""Immutable-ish data models for parsed LMT files."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LmtHeader:
    signature: bytes
    version: int
    entry_count: int
    unknown: bytes


@dataclass(frozen=True)
class LmtInterpolationBasis:
    mult: tuple[float, float, float, float]
    add: tuple[float, float, float, float]


@dataclass(frozen=True)
class LmtActionHeader:
    id: int
    fcurve_offset: int
    fcurve_count: int
    frame_count: int
    loop_frame: int
    null0: tuple[int, int, int]
    translation: tuple[float, float, float, float]
    rotation_lerp: tuple[float, float, float, float]
    flags: int
    null2: bytes
    flags2: int
    null3: tuple[int, int, int, int, int]
    timl_offset: int


@dataclass(frozen=True)
class LmtTrackHeader:
    buffer_type: int
    usage: int
    joint_type: int
    unknown_tag: int
    bone_id: int
    weight: float
    buffer_size: int
    buffer_offset: int
    basis: tuple[float, float, float, float]
    lerp_offset: int


@dataclass(frozen=True)
class LmtTrack:
    header: LmtTrackHeader
    raw_buffer: bytes
    lerp_basis: LmtInterpolationBasis | None = None


@dataclass(frozen=True)
class LmtAction:
    header: LmtActionHeader
    tracks: tuple[LmtTrack, ...] = field(default_factory=tuple)

    @property
    def id(self) -> int:
        return self.header.id

    @property
    def has_timl(self) -> bool:
        return self.header.timl_offset != 0


@dataclass(frozen=True)
class LmtFile:
    source_name: str
    file_size: int
    header: LmtHeader
    entry_offsets: tuple[int, ...]
    actions: tuple[LmtAction, ...]

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def track_count(self) -> int:
        return sum(len(action.tracks) for action in self.actions)
