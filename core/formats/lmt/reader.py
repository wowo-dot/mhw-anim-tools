"""Read-only parser for Monster Hunter World LMT files."""

from __future__ import annotations

import struct
from pathlib import Path

from ...binary.reader import BinaryReader
from ...diagnostics.errors import BinaryFormatError
from .model import LmtAction
from .model import LmtActionHeader
from .model import LmtFile
from .model import LmtHeader
from .model import LmtInterpolationBasis
from .model import LmtTrack
from .model import LmtTrackHeader


HEADER_STRUCT = struct.Struct("<4shh8s")
ENTRY_OFFSET_STRUCT = struct.Struct("<Q")
ACTION_STRUCT = struct.Struct("<QIIi3i4f4fB2sB5iQ")
TRACK_STRUCT = struct.Struct("<BBBBif iq4fq")
LERP_BASIS_STRUCT = struct.Struct("<4f4f")

EXPECTED_SIGNATURE = b"LMT\x00"


def _read_header(reader: BinaryReader) -> LmtHeader:
    signature, version, entry_count, unknown = reader.read_struct(HEADER_STRUCT)
    if signature != EXPECTED_SIGNATURE:
        raise BinaryFormatError(
            "Unsupported LMT signature",
            source_name=reader.source_name,
            signature=signature,
        )
    if entry_count < 0:
        raise BinaryFormatError(
            "Negative LMT entry count",
            source_name=reader.source_name,
            entry_count=entry_count,
        )
    return LmtHeader(
        signature=signature,
        version=version,
        entry_count=entry_count,
        unknown=unknown,
    )


def _read_offsets(reader: BinaryReader, entry_count: int) -> tuple[int, ...]:
    offsets: list[int] = []
    for _ in range(entry_count):
        (offset,) = reader.read_struct(ENTRY_OFFSET_STRUCT)
        offsets.append(offset)
    return tuple(offsets)


def _read_action_header(reader: BinaryReader, action_id: int, offset: int) -> LmtActionHeader:
    (
        fcurve_offset,
        fcurve_count,
        frame_count,
        loop_frame,
        null0_a,
        null0_b,
        null0_c,
        trans_x,
        trans_y,
        trans_z,
        trans_w,
        rot_x,
        rot_y,
        rot_z,
        rot_w,
        flags,
        null2,
        flags2,
        null3_a,
        null3_b,
        null3_c,
        null3_d,
        null3_e,
        timl_offset,
    ) = reader.read_struct_at(offset, ACTION_STRUCT)
    return LmtActionHeader(
        id=action_id,
        fcurve_offset=fcurve_offset,
        fcurve_count=fcurve_count,
        frame_count=frame_count,
        loop_frame=loop_frame,
        null0=(null0_a, null0_b, null0_c),
        translation=(trans_x, trans_y, trans_z, trans_w),
        rotation_lerp=(rot_x, rot_y, rot_z, rot_w),
        flags=flags,
        null2=null2,
        flags2=flags2,
        null3=(null3_a, null3_b, null3_c, null3_d, null3_e),
        timl_offset=timl_offset,
    )


def _read_lerp_basis(reader: BinaryReader, offset: int) -> LmtInterpolationBasis:
    values = reader.read_struct_at(offset, LERP_BASIS_STRUCT)
    mult = tuple(values[:4])
    add = tuple(values[4:])
    return LmtInterpolationBasis(mult=mult, add=add)


def _read_track(reader: BinaryReader, offset: int) -> LmtTrack:
    (
        buffer_type,
        usage,
        joint_type,
        unknown_tag,
        bone_id,
        weight,
        buffer_size,
        buffer_offset,
        basis_x,
        basis_y,
        basis_z,
        basis_w,
        lerp_offset,
    ) = reader.read_struct_at(offset, TRACK_STRUCT)
    raw_buffer = b""
    if buffer_offset and buffer_size:
        raw_buffer = reader.slice(buffer_offset, buffer_size)
    lerp_basis = None
    if lerp_offset:
        lerp_basis = _read_lerp_basis(reader, lerp_offset)
    header = LmtTrackHeader(
        buffer_type=buffer_type,
        usage=usage,
        joint_type=joint_type,
        unknown_tag=unknown_tag,
        bone_id=bone_id,
        weight=weight,
        buffer_size=buffer_size,
        buffer_offset=buffer_offset,
        basis=(basis_x, basis_y, basis_z, basis_w),
        lerp_offset=lerp_offset,
    )
    return LmtTrack(header=header, raw_buffer=raw_buffer, lerp_basis=lerp_basis)


def read_lmt_bytes(data: bytes, source_name: str = "<memory>") -> LmtFile:
    reader = BinaryReader(data, source_name=source_name)
    header = _read_header(reader)
    entry_offsets = _read_offsets(reader, header.entry_count)
    actions: list[LmtAction] = []
    for action_id, action_offset in enumerate(entry_offsets):
        if action_offset == 0:
            continue
        action_header = _read_action_header(reader, action_id, action_offset)
        tracks: list[LmtTrack] = []
        if action_header.fcurve_offset and action_header.fcurve_count:
            for track_index in range(action_header.fcurve_count):
                track_offset = action_header.fcurve_offset + (track_index * TRACK_STRUCT.size)
                tracks.append(_read_track(reader, track_offset))
        actions.append(LmtAction(header=action_header, tracks=tuple(tracks)))
    return LmtFile(
        source_name=source_name,
        file_size=len(data),
        header=header,
        entry_offsets=entry_offsets,
        actions=tuple(actions),
    )


def read_lmt_file(path: str | Path) -> LmtFile:
    file_path = Path(path)
    data = file_path.read_bytes()
    return read_lmt_bytes(data, source_name=str(file_path))
