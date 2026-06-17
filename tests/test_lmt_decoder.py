from __future__ import annotations

import struct
import unittest
from unittest.mock import patch

from core.formats.lmt.decoder import decode_action_tracks
from core.formats.lmt.reader import read_lmt_bytes


HEADER_STRUCT = struct.Struct("<4shh8s")
ACTION_STRUCT = struct.Struct("<QIIi3i4f4fB2sB5iQ")
TRACK_STRUCT = struct.Struct("<BBBBifiq4fq")
LERP_BASIS_STRUCT = struct.Struct("<4f4f")


def _pack_bits(fields: list[tuple[int, int]]) -> bytes:
    value = 0
    shift = 0
    total_bits = 0
    for field_value, bit_count in fields:
        total_bits += bit_count
        if bit_count == 0:
            continue
        value |= (field_value & ((1 << bit_count) - 1)) << shift
        shift += bit_count
    return value.to_bytes(total_bits // 8, "little")


def _pack_quantized_units(fields: list[tuple[int, int]], unit_bits: int) -> bytes:
    units: list[int] = []
    remaining_bits = 0

    def ensure_unit():
        nonlocal remaining_bits
        if remaining_bits > 0:
            return
        units.append(0)
        remaining_bits = unit_bits

    for field_value, bit_count in fields:
        if bit_count <= 0:
            continue
        raw_value = int(field_value) & ((1 << bit_count) - 1)
        bits_left = int(bit_count)
        while bits_left > 0:
            ensure_unit()
            chunk_bits = min(bits_left, remaining_bits)
            shift = bits_left - chunk_bits
            chunk = (raw_value >> shift) & ((1 << chunk_bits) - 1)
            used_bits = unit_bits - remaining_bits
            units[-1] |= chunk << used_bits
            remaining_bits -= chunk_bits
            bits_left -= chunk_bits

    unit_bytes = unit_bits // 8
    return b"".join(int(unit).to_bytes(unit_bytes, "little") for unit in units)


def _encode_unsigned(value: float, bits: int) -> int:
    denominator = (1 << bits) - 1
    return round(value * denominator)


def _encode_q14(value: float) -> int:
    half_value = value / 2.0
    if half_value < 0:
        magnitude = round(abs(half_value) * ((1 << 13) - 1))
        return magnitude ^ ((1 << 14) - 1)
    return round(half_value * ((1 << 13) - 1))


def build_lmt_with_track(
    *,
    buffer_type: int,
    usage: int,
    basis: tuple[float, float, float, float],
    raw_buffer: bytes = b"",
    translation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    rotation: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
    lerp_mult: tuple[float, float, float, float] | None = None,
    lerp_add: tuple[float, float, float, float] | None = None,
    bone_id: int = 3,
    frame_count: int = 40,
) -> bytes:
    header = HEADER_STRUCT.pack(b"LMT\x00", 95, 1, b"\x00" * 8)
    entry_offsets = struct.pack("<Q", 32)
    header_padding = b"\x00" * 8

    action_offset = 32
    fcurve_offset = action_offset + ACTION_STRUCT.size
    buffer_offset = fcurve_offset + TRACK_STRUCT.size if raw_buffer else 0
    lerp_offset = buffer_offset + len(raw_buffer) if lerp_mult is not None and lerp_add is not None else 0

    action = ACTION_STRUCT.pack(
        fcurve_offset,
        1,
        frame_count,
        -1,
        0,
        0,
        0,
        *translation,
        *rotation,
        0,
        b"\x00\x00",
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    track = TRACK_STRUCT.pack(
        buffer_type,
        usage,
        0,
        205,
        bone_id,
        1.0,
        len(raw_buffer),
        buffer_offset,
        *basis,
        lerp_offset,
    )
    lerp_bytes = (
        LERP_BASIS_STRUCT.pack(*lerp_mult, *lerp_add)
        if lerp_mult is not None and lerp_add is not None
        else b""
    )
    return header + entry_offsets + header_padding + action + track + raw_buffer + lerp_bytes


class LmtDecoderTests(unittest.TestCase):
    def test_decode_float_vector_keyframes(self):
        raw_buffer = struct.pack("<3fI3fI", 1.25, 2.5, -3.75, 5, 4.0, 5.0, 6.0, 7)
        lmt = read_lmt_bytes(
            build_lmt_with_track(
                buffer_type=3,
                usage=1,
                basis=(0.5, 1.0, 1.5, 0.0),
                raw_buffer=raw_buffer,
                translation=(9.0, 8.0, 7.0, 0.0),
            ),
            source_name="float-vector.lmt",
        )
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]
        self.assertEqual(track.basis_value, (0.5, 1.0, 1.5))
        self.assertIsNone(track.tail_value)
        self.assertIsNone(track.tail_frame)
        self.assertEqual([sample.frame for sample in track.keyframes], [0, 5])
        self.assertEqual(track.keyframes[0].value, (1.25, 2.5, -3.75))
        self.assertEqual(track.keyframes[1].value, (4.0, 5.0, 6.0))

    def test_decode_root_translation_tail_uses_action_header(self):
        lmt = read_lmt_bytes(
            build_lmt_with_track(
                buffer_type=1,
                usage=4,
                basis=(0.5, 1.0, 1.5, 0.0),
                translation=(9.0, 8.0, 7.0, 0.0),
                bone_id=-1,
                frame_count=40,
            ),
            source_name="root-translation-tail.lmt",
        )
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]
        self.assertEqual(track.basis_value, (0.5, 1.0, 1.5))
        self.assertEqual(track.tail_value, (9.0, 8.0, 7.0))
        self.assertEqual(track.tail_frame, 40)
        self.assertEqual(track.keyframes, ())

    def test_decode_vector_lerp_keyframes(self):
        raw_buffer = struct.pack(
            "<4B4B",
            0,
            _encode_unsigned(0.5, 8),
            _encode_unsigned(1.0, 8),
            3,
            _encode_unsigned(1.0, 8),
            _encode_unsigned(0.0, 8),
            _encode_unsigned(0.25, 8),
            4,
        )
        lmt = read_lmt_bytes(
            build_lmt_with_track(
                buffer_type=5,
                usage=4,
                basis=(0.0, 0.0, 0.0, 0.0),
                raw_buffer=raw_buffer,
                translation=(3.0, 4.0, 5.0, 0.0),
                lerp_mult=(2.0, 4.0, 6.0, 1.0),
                lerp_add=(-1.0, 10.0, 100.0, 0.0),
            ),
            source_name="vector-lerp.lmt",
        )
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]
        self.assertEqual([sample.frame for sample in track.keyframes], [0, 3])
        self.assertAlmostEqual(track.keyframes[0].value[0], -1.0, places=5)
        self.assertAlmostEqual(track.keyframes[0].value[1], 12.007843137254902, places=6)
        self.assertAlmostEqual(track.keyframes[0].value[2], 106.0, places=5)
        self.assertAlmostEqual(track.keyframes[1].value[0], 1.0, places=5)
        self.assertAlmostEqual(track.keyframes[1].value[1], 10.0, places=5)
        self.assertAlmostEqual(track.keyframes[1].value[2], 101.50588235294117, places=6)

    def test_decode_q14_quaternion_keyframes(self):
        raw_buffer = _pack_bits(
            [
                (_encode_q14(1.0), 14),
                (_encode_q14(-0.25), 14),
                (_encode_q14(0.0), 14),
                (_encode_q14(0.5), 14),
                (9, 8),
            ]
        )
        lmt = read_lmt_bytes(
            build_lmt_with_track(
                buffer_type=6,
                usage=0,
                basis=(0.0, 0.0, 0.0, 1.0),
                raw_buffer=raw_buffer,
                rotation=(0.0, 0.0, 0.0, 1.0),
            ),
            source_name="q14.lmt",
        )
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]
        self.assertEqual(track.basis_value, (1.0, 0.0, 0.0, 0.0))
        self.assertIsNone(track.tail_value)
        self.assertIsNone(track.tail_frame)
        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertAlmostEqual(track.keyframes[0].value[0], 1.0, delta=2e-4)
        self.assertAlmostEqual(track.keyframes[0].value[1], 0.50006, places=4)
        self.assertAlmostEqual(track.keyframes[0].value[2], 0.0, places=5)
        self.assertAlmostEqual(track.keyframes[0].value[3], -0.25003, delta=3e-4)

    def test_decode_quaternion_union_lerp_keeps_missing_axes_zero(self):
        raw_buffer = _pack_bits(
            [
                (_encode_unsigned(0.5, 14), 14),
                (_encode_unsigned(1.0, 14), 14),
                (2, 4),
            ]
        )
        lmt = read_lmt_bytes(
            build_lmt_with_track(
                buffer_type=11,
                usage=3,
                basis=(0.0, 0.0, 0.0, 1.0),
                raw_buffer=raw_buffer,
                rotation=(0.0, 0.0, 0.0, 1.0),
                lerp_mult=(1.0, 1.0, 1.0, 1.0),
                lerp_add=(0.0, 0.0, 0.0, 0.0),
                bone_id=-1,
            ),
            source_name="q-union.lmt",
        )
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]
        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertEqual(track.tail_value, (1.0, 0.0, 0.0, 0.0))
        self.assertEqual(track.tail_frame, 40)
        self.assertAlmostEqual(track.keyframes[0].value[0], 1.0, places=4)
        self.assertAlmostEqual(track.keyframes[0].value[1], 0.5, places=4)
        self.assertAlmostEqual(track.keyframes[0].value[2], 0.0, places=5)
        self.assertAlmostEqual(track.keyframes[0].value[3], 0.0, places=5)

    def test_decode_q9_quaternion_lerp_respects_byte_boundary_order(self):
        raw_buffer = _pack_quantized_units(
            [
                (_encode_unsigned(393.0 / 511.0, 9), 9),
                (_encode_unsigned(96.0 / 511.0, 9), 9),
                (_encode_unsigned(301.0 / 511.0, 9), 9),
                (_encode_unsigned(150.0 / 511.0, 9), 9),
                (1, 4),
            ],
            8,
        )
        lmt = read_lmt_bytes(
            build_lmt_with_track(
                buffer_type=15,
                usage=0,
                basis=(0.0, 0.0, 0.0, 1.0),
                raw_buffer=raw_buffer,
                lerp_mult=(1.0, 1.0, 1.0, 1.0),
                lerp_add=(0.0, 0.0, 0.0, 0.0),
            ),
            source_name="q9-byte-boundary.lmt",
        )

        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertAlmostEqual(track.keyframes[0].value[0], 150.0 / 511.0, places=6)
        self.assertAlmostEqual(track.keyframes[0].value[1], 393.0 / 511.0, places=6)
        self.assertAlmostEqual(track.keyframes[0].value[2], 96.0 / 511.0, places=6)
        self.assertAlmostEqual(track.keyframes[0].value[3], 301.0 / 511.0, places=6)

    def test_non_strict_decode_records_error_for_bad_stride(self):
        raw_buffer = b"\x00" * 7
        lmt = read_lmt_bytes(
            build_lmt_with_track(
                buffer_type=4,
                usage=1,
                basis=(0.0, 0.0, 0.0, 0.0),
                raw_buffer=raw_buffer,
                lerp_mult=(1.0, 1.0, 1.0, 1.0),
                lerp_add=(0.0, 0.0, 0.0, 0.0),
            ),
            source_name="bad-stride.lmt",
        )
        decoded = decode_action_tracks(lmt.actions[0], strict=False)
        track = decoded.tracks[0]
        self.assertIsNotNone(track.decode_error)
        with self.assertRaises(Exception):
            decode_action_tracks(lmt.actions[0], strict=True)

    def test_non_strict_decode_does_not_hide_programmer_type_errors(self):
        lmt = read_lmt_bytes(
            build_lmt_with_track(
                buffer_type=3,
                usage=1,
                basis=(0.0, 0.0, 0.0, 0.0),
                raw_buffer=struct.pack("<3fI", 1.0, 2.0, 3.0, 1),
            ),
            source_name="type-error.lmt",
        )
        with patch("core.formats.lmt.decoder._decode_supported_track", side_effect=TypeError("boom")):
            with self.assertRaises(TypeError):
                decode_action_tracks(lmt.actions[0], strict=False)


if __name__ == "__main__":
    unittest.main()
