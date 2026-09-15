"""Explicit source-slot editing; evaluated poses never implicitly own raw slots."""
from dataclasses import replace
import struct

from .content_signature import action_header_content_signature, track_content_signature, timl_payload_content_signature
from .export_context import extract_raw_timl_payload_layouts
from .merge_writer import write_multi_merged_lmt_bytes
from .reader import read_lmt_bytes
from .validation import validate_lmt


def export_source_slots(bank, replacements=None) -> bytes:
    """Return an exact snapshot, or replace explicit {entry_id: {slot: LmtTrack}}.

    No-op is byte identical, including layout/padding/TIML. Edits keep source
    count/order/identities, header timing, unknown fields and all other records;
    serialization rebases valid TIML payloads. Every edited export is read back
    and audited without relaxing validation. This operates on a pinned immutable
    bank, not on potentially replaced files or Blender's evaluated helper curves.
    """
    replacements = dict(replacements or {})
    if not any(replacements.values()):
        return bank.data
    known = {a.id for a in bank.lmt.actions}
    if any(type(entry) is not int or entry not in known for entry in replacements):
        raise ValueError("Replacement entry is not in the source bank")
    actions = []
    for action in bank.lmt.actions:
        edits = dict(replacements.get(action.id, {}))
        tracks = list(action.tracks)
        for slot, replacement in edits.items():
            if type(slot) is not int or not 0 <= slot < len(tracks):
                raise ValueError(f"Invalid source slot {slot} in entry {action.id}")
            old, new = tracks[slot].header, replacement.header
            # Timing, channel ownership and opaque runtime metadata are not an
            # implicit side effect of a pose edit. Change those through separate
            # existing structural authoring APIs if that is the intended task.
            for field in ('bone_id', 'usage', 'joint_type', 'unknown_tag', 'weight'):
                if getattr(new, field) != getattr(old, field):
                    raise ValueError(f"Slot replacement changed preserved {field}")
            if new.buffer_size != len(replacement.raw_buffer):
                raise ValueError("Replacement buffer length disagrees with its header")
            # Header and lerp values are IEEE float32 in LMT. Canonicalize the
            # explicitly edited values once so the exact audit compares what the
            # format can represent, while untouched records retain source bytes.
            f32 = lambda values: struct.unpack('<4f', struct.pack('<4f', *values))
            lerp = replacement.lerp_basis
            if lerp is not None:
                lerp = replace(lerp, mult=f32(lerp.mult), add=f32(lerp.add))
            tracks[slot] = replace(replacement, header=replace(new, basis=f32(new.basis)), lerp_basis=lerp)
        actions.append(replace(action, tracks=tuple(tracks)))
    edited = replace(bank.lmt, actions=tuple(actions))
    result = write_multi_merged_lmt_bytes(edited, bank.data, {})
    readback = read_lmt_bytes(result, source_name="source-slot readback")
    if validate_lmt(readback).error_count:
        raise ValueError("Edited source bank failed readback validation")
    audit_source_slots(edited, bank.data, readback, result)
    return result


def audit_source_slots(expected, expected_bytes, actual, actual_bytes):
    """Exact content audit allowing address relocation, including TIML targets."""
    if expected.header != actual.header or len(expected.actions) != len(actual.actions):
        raise ValueError("Bank header/action membership changed")
    expected_timl = extract_raw_timl_payload_layouts(expected, expected_bytes)
    actual_timl = extract_raw_timl_payload_layouts(actual, actual_bytes)
    for left, right in zip(expected.actions, actual.actions):
        if left.id != right.id or action_header_content_signature(left) != action_header_content_signature(right):
            raise ValueError("Action header semantics changed")
        if len(left.tracks) != len(right.tracks):
            raise ValueError("Track count changed")
        for index, (lt, rt) in enumerate(zip(left.tracks, right.tracks)):
            if track_content_signature(lt) != track_content_signature(rt):
                raise ValueError(f"Ordered track contents changed at entry {left.id}, slot {index}")
        lo, ro = left.header.timl_offset, right.header.timl_offset
        if bool(lo) != bool(ro) or (lo and timl_payload_content_signature(expected_timl[lo], source_offset=lo)
                                  != timl_payload_content_signature(actual_timl[ro], source_offset=ro)):
            raise ValueError("TIML payload semantics changed")
