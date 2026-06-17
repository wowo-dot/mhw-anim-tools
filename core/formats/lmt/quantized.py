"""Helpers for LMT's chunked packed-bit quaternion encodings.

These formats are not stored as one normal little-endian bitstream. The legacy
tools read them chunk-by-chunk from 8/16/32/64-bit elements, consuming low bits
from each element while assembling the field value from earlier chunks as the
more-significant bits. We mirror that behavior here so decode/encode stays
compatible with existing MT Framework tooling.
"""

from __future__ import annotations


class QuantizedFieldReader:
    def __init__(self, units: list[int], *, unit_bits: int):
        self._units = list(int(unit) for unit in units)
        self._unit_bits = int(unit_bits)
        self._remaining_bits_in_first_unit = int(unit_bits)

    def _skip(self, bit_count: int) -> None:
        remaining = int(bit_count)
        while remaining > 0:
            consumed = min(remaining, self._remaining_bits_in_first_unit)
            self._remaining_bits_in_first_unit -= consumed
            remaining -= consumed
            if self._remaining_bits_in_first_unit == 0:
                self._units = self._units[1:]
                self._remaining_bits_in_first_unit = self._unit_bits
            else:
                self._units[0] >>= consumed

    def take(self, bit_count: int) -> int:
        value = 0
        bits_left = int(bit_count)
        unit_index = 0
        chunk_bits = min(self._remaining_bits_in_first_unit, bits_left)
        while bits_left > 0:
            value <<= chunk_bits
            value |= self._units[unit_index] & ((1 << chunk_bits) - 1)
            bits_left -= chunk_bits
            unit_index += 1
            chunk_bits = min(self._unit_bits, bits_left)
        self._skip(bit_count)
        return int(value)


class QuantizedFieldWriter:
    def __init__(self, *, unit_bits: int):
        self._unit_bits = int(unit_bits)
        self._units: list[int] = []
        self._remaining_bits_in_current_unit = 0

    def _ensure_current_unit(self) -> None:
        if self._remaining_bits_in_current_unit > 0:
            return
        self._units.append(0)
        self._remaining_bits_in_current_unit = self._unit_bits

    def put(self, value: int, bit_count: int) -> None:
        if bit_count <= 0:
            return
        raw_value = int(value) & ((1 << bit_count) - 1)
        bits_left = int(bit_count)
        while bits_left > 0:
            self._ensure_current_unit()
            chunk_bits = min(bits_left, self._remaining_bits_in_current_unit)
            shift = bits_left - chunk_bits
            chunk = (raw_value >> shift) & ((1 << chunk_bits) - 1)
            used_bits = self._unit_bits - self._remaining_bits_in_current_unit
            self._units[-1] |= chunk << used_bits
            self._remaining_bits_in_current_unit -= chunk_bits
            bits_left -= chunk_bits

    def to_bytes(self, *, unit_bytes: int) -> bytes:
        return b"".join(int(unit).to_bytes(unit_bytes, "little") for unit in self._units)


def _quantized_units_from_bytes(data: bytes, *, unit_bytes: int) -> list[int]:
    if unit_bytes <= 0:
        raise ValueError("unit_bytes must be positive")
    if len(data) % unit_bytes != 0:
        raise ValueError("quantized buffer length must be a multiple of unit_bytes")
    return [
        int.from_bytes(data[offset : offset + unit_bytes], "little")
        for offset in range(0, len(data), unit_bytes)
    ]


def unpack_quantized_fields(
    data: bytes,
    *,
    unit_bytes: int,
    fields: tuple[tuple[str, int], ...],
) -> dict[str, int]:
    reader = QuantizedFieldReader(
        _quantized_units_from_bytes(data, unit_bytes=unit_bytes),
        unit_bits=unit_bytes * 8,
    )
    values: dict[str, int] = {}
    for name, bit_count in fields:
        values[name] = 0 if bit_count == 0 else reader.take(bit_count)
    return values


def pack_quantized_fields(
    fields: list[tuple[int, int]],
    *,
    unit_bytes: int,
) -> bytes:
    writer = QuantizedFieldWriter(unit_bits=unit_bytes * 8)
    for field_value, bit_count in fields:
        writer.put(field_value, bit_count)
    return writer.to_bytes(unit_bytes=unit_bytes)
