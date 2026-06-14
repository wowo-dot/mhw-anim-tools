"""Decoded LMT sample models.

These dataclasses represent LMT content after buffer-specific decoding, but
before any Blender-specific action or fcurve creation.

Quaternion convention:
- `basis_value`, `value`, and `tail_value` are always WXYZ for quaternion
  tracks.
- Vector tracks remain XYZ.

Tail semantics:
- `tail_frame` / `tail_value` are only populated for root rotation and root
  translation tracks (`bone_id == -1`).
- Local bone tracks and all scale tracks have no decoded tail sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LmtDecodedSample:
    frame: int
    delta_to_next: int
    value: tuple[float, ...]


@dataclass(frozen=True)
class LmtDecodedTrack:
    track_index: int
    bone_id: int
    usage: int
    buffer_type: int
    basis_value: tuple[float, ...]
    keyframes: tuple[LmtDecodedSample, ...] = field(default_factory=tuple)
    tail_frame: int | None = None
    tail_value: tuple[float, ...] | None = None
    decode_error: str | None = None

    @property
    def decoded_key_count(self) -> int:
        return len(self.keyframes)

    @property
    def first_keyframe(self) -> int | None:
        return self.keyframes[0].frame if self.keyframes else None

    @property
    def last_keyframe(self) -> int | None:
        return self.keyframes[-1].frame if self.keyframes else None


@dataclass(frozen=True)
class LmtDecodedAction:
    action_id: int
    frame_count: int
    loop_frame: int
    tracks: tuple[LmtDecodedTrack, ...] = field(default_factory=tuple)
