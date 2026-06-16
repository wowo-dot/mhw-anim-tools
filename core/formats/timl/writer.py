"""Write standalone TIML files from sampled TIML controller data."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ...diagnostics.errors import ValidationError
from .embedded_writer import build_embedded_timl_data_payload_from_sampled
from .model import EXPECTED_LAYOUT_SIGNATURE
from .reader import DATA_STRUCT
from .reader import ENTRY_OFFSET_STRUCT
from .reader import EXPECTED_SIGNATURE
from .reader import HEADER_STRUCT


def _align(offset: int, alignment: int) -> int:
    return (offset + (alignment - 1)) & ~(alignment - 1)


@dataclass(frozen=True)
class TimlEntryWriteRequest:
    entry_id: int
    sampled_transforms: tuple[object, ...] = ()
    data_index_a: int = 0
    data_index_b: int = 0
    animation_length: float = 0.0
    loop_start_point: float = 0.0
    loop_control: int = 0
    label_hash: int = 0


def _empty_timl_data_payload(
    *,
    data_index_a: int,
    data_index_b: int,
    animation_length: float,
    loop_start_point: float,
    loop_control: int,
    label_hash: int,
) -> bytes:
    payload = bytearray(DATA_STRUCT.size)
    DATA_STRUCT.pack_into(
        payload,
        0,
        0,
        0,
        int(data_index_a),
        int(data_index_b),
        float(animation_length),
        float(loop_start_point),
        int(loop_control),
        int(label_hash) & 0xFFFFFFFF,
    )
    return bytes(payload)


def _payload_for_entry(entry: TimlEntryWriteRequest, *, base_offset: int) -> bytes:
    sampled_transforms = tuple(entry.sampled_transforms or ())
    if not sampled_transforms:
        return _empty_timl_data_payload(
            data_index_a=int(entry.data_index_a),
            data_index_b=int(entry.data_index_b),
            animation_length=float(entry.animation_length),
            loop_start_point=float(entry.loop_start_point),
            loop_control=int(entry.loop_control),
            label_hash=int(entry.label_hash),
        )
    payload, _rebase_offsets = build_embedded_timl_data_payload_from_sampled(
        sampled_transforms,
        base_offset=int(base_offset),
        data_index_a=int(entry.data_index_a),
        data_index_b=int(entry.data_index_b),
        animation_length=float(entry.animation_length),
        loop_start_point=float(entry.loop_start_point),
        loop_control=int(entry.loop_control),
        label_hash=int(entry.label_hash),
    )
    return payload


def _normalize_entries(entries) -> list[TimlEntryWriteRequest]:
    return [
        entry if isinstance(entry, TimlEntryWriteRequest) else TimlEntryWriteRequest(**entry)
        for entry in entries
    ]


def _resolve_entry_count(normalized_entries, *, entry_count: int | None = None) -> int:
    normalized_entries = [
        entry if isinstance(entry, TimlEntryWriteRequest) else TimlEntryWriteRequest(**entry)
        for entry in normalized_entries
    ]
    seen_entry_ids: set[int] = set()
    highest_entry_id = -1
    for entry in normalized_entries:
        entry_id = int(entry.entry_id)
        if entry_id < 0:
            raise ValidationError(f"TIML entry ids must be non-negative, got {entry_id}.")
        if entry_id in seen_entry_ids:
            raise ValidationError(f"Duplicate standalone TIML entry id {entry_id}.")
        seen_entry_ids.add(entry_id)
        highest_entry_id = max(highest_entry_id, entry_id)

    resolved_entry_count = int(entry_count) if entry_count is not None else (highest_entry_id + 1 if highest_entry_id >= 0 else 0)
    if resolved_entry_count < 0:
        raise ValidationError(f"TIML entry count must be non-negative, got {resolved_entry_count}.")
    if highest_entry_id >= resolved_entry_count:
        raise ValidationError(
            f"Standalone TIML entry id {highest_entry_id} falls outside the requested entry count {resolved_entry_count}."
        )
    return resolved_entry_count


def resolve_timl_payload_layout(payloads_by_entry, *, entry_count: int) -> tuple[int, tuple[int, ...], int]:
    resolved_entry_count = int(entry_count)
    if resolved_entry_count < 0:
        raise ValidationError(f"TIML entry count must be non-negative, got {resolved_entry_count}.")

    entry_table_offset = _align(HEADER_STRUCT.size, 16)
    entry_table_size = ENTRY_OFFSET_STRUCT.size * resolved_entry_count
    current_offset = _align(entry_table_offset + entry_table_size, 16)

    entry_offsets = [0] * resolved_entry_count
    for entry_id, payload in sorted(
        ((int(key), bytes(value)) for key, value in dict(payloads_by_entry).items()),
        key=lambda item: item[0],
    ):
        if entry_id < 0:
            raise ValidationError(f"TIML entry ids must be non-negative, got {entry_id}.")
        if entry_id >= resolved_entry_count:
            raise ValidationError(
                f"Standalone TIML entry id {entry_id} falls outside the requested entry count {resolved_entry_count}."
            )
        if entry_offsets[entry_id]:
            raise ValidationError(f"Duplicate standalone TIML entry id {entry_id}.")
        if not payload:
            continue
        entry_offsets[entry_id] = current_offset
        current_offset = _align(current_offset + len(payload), 16)
    return entry_table_offset, tuple(entry_offsets), current_offset


def write_timl_payload_map(
    payloads_by_entry,
    *,
    entry_count: int,
    reserved: int = 0,
    layout_signature: bytes = EXPECTED_LAYOUT_SIGNATURE,
) -> bytes:
    resolved_entry_count = int(entry_count)
    entry_table_offset, entry_offsets, blob_size = resolve_timl_payload_layout(
        payloads_by_entry,
        entry_count=resolved_entry_count,
    )

    blob = bytearray(blob_size)
    HEADER_STRUCT.pack_into(
        blob,
        0,
        EXPECTED_SIGNATURE,
        bytes(layout_signature),
        int(reserved),
        int(entry_table_offset),
        resolved_entry_count,
    )
    for entry_id, entry_offset in enumerate(entry_offsets):
        ENTRY_OFFSET_STRUCT.pack_into(
            blob,
            entry_table_offset + (entry_id * ENTRY_OFFSET_STRUCT.size),
            int(entry_offset),
        )
    for entry_id, payload in sorted(
        ((int(key), bytes(value)) for key, value in dict(payloads_by_entry).items()),
        key=lambda item: item[0],
    ):
        entry_offset = int(entry_offsets[entry_id])
        if not entry_offset or not payload:
            continue
        blob[entry_offset : entry_offset + len(payload)] = payload
    return bytes(blob)


def write_timl_bytes(
    entries,
    *,
    entry_count: int | None = None,
    reserved: int = 0,
    layout_signature: bytes = EXPECTED_LAYOUT_SIGNATURE,
) -> bytes:
    normalized_entries = _normalize_entries(entries)
    resolved_entry_count = _resolve_entry_count(normalized_entries, entry_count=entry_count)

    first_pass_payloads = {
        int(entry.entry_id): _payload_for_entry(entry, base_offset=0)
        for entry in sorted(normalized_entries, key=lambda item: int(item.entry_id))
    }
    _entry_table_offset, entry_offsets, _blob_size = resolve_timl_payload_layout(
        first_pass_payloads,
        entry_count=resolved_entry_count,
    )
    final_payloads = {
        int(entry.entry_id): _payload_for_entry(
            entry,
            base_offset=int(entry_offsets[int(entry.entry_id)]),
        )
        for entry in sorted(normalized_entries, key=lambda item: int(item.entry_id))
    }
    return write_timl_payload_map(
        final_payloads,
        entry_count=resolved_entry_count,
        reserved=reserved,
        layout_signature=layout_signature,
    )
