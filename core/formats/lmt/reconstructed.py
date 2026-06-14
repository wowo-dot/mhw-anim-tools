"""Sparse reconstructed LMT track models for export-prep work.

These dataclasses sit between dense Blender Action sampling and future binary
buffer packing. They preserve LMT-specific semantics without depending on
Blender:

- `basis_value` is always the frame-0 value
- `keyframes` are sparse interior samples that must be serialized into a track
  buffer
- `tail_frame` / `tail_value` are used only for root rotation/translation
  tracks, mirroring decoded LMT semantics
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LmtReconstructedKeyframe:
    frame: int
    value: tuple[float, ...]


@dataclass(frozen=True)
class LmtReconstructedTrack:
    bone_id: int
    usage: int
    basis_value: tuple[float, ...]
    keyframes: tuple[LmtReconstructedKeyframe, ...] = field(default_factory=tuple)
    tail_frame: int | None = None
    tail_value: tuple[float, ...] | None = None

    @property
    def sparse_key_count(self) -> int:
        return len(self.keyframes)


@dataclass(frozen=True)
class LmtReconstructedAction:
    action_name: str
    frame_start: int
    frame_end: int
    tracks: tuple[LmtReconstructedTrack, ...] = field(default_factory=tuple)

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def sparse_key_count(self) -> int:
        return sum(track.sparse_key_count for track in self.tracks)
