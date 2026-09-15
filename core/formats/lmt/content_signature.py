"""Compare raw LMT content without deep-copying metadata or comparing addresses.

These signatures are for preservation audits, not tolerant motion comparison.
They retain every non-address header field, raw track bytes and lerp basis.
"""

from dataclasses import fields
from operator import attrgetter
import struct

from ...diagnostics.errors import ValidationError
from .model import LmtActionHeader, LmtTrackHeader
from .merge_writer import _rebase_timl_payload


_track_header = attrgetter(*(field.name for field in fields(LmtTrackHeader)
                             if field.name not in {"buffer_offset", "lerp_offset"}))
_action_header = attrgetter(*(field.name for field in fields(LmtActionHeader)
                              if field.name not in {"fcurve_offset", "fcurve_count", "timl_offset"}))


def track_content_signature(track):
    return _track_header(track.header), track.raw_buffer, track.lerp_basis


def action_header_content_signature(action):
    """Header semantics; callers must separately audit track count/order and TIML."""
    return _action_header(action.header)


def timl_payload_content_signature(payload, *, source_offset: int):
    """Normalize a validated raw payload's addresses for relocation-aware equality.

    Use RawTimlPayload from extract_raw_timl_payload_layouts. This retains raw
    layout, padding, values, easing and interpolation, allowing only relocation.
    Never compare TIML pointers alone when the containing bytes have changed.
    """
    for offset in payload.rebase_offsets:
        if offset < 0 or offset + 8 > len(payload.payload):
            raise ValidationError("TIML signature has an out-of-bounds pointer field.")
        pointer, = struct.unpack_from("<Q", payload.payload, offset)
        if pointer and not source_offset <= pointer <= source_offset + len(payload.payload):
            raise ValidationError("TIML signature has a pointer outside its payload; verify its source address.")
    return (tuple(payload.rebase_offsets),
            _rebase_timl_payload(payload, source_offset=source_offset, target_offset=16))
