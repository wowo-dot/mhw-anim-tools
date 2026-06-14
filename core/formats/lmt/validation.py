"""Validation rules for parsed LMT data."""

from __future__ import annotations

from ...diagnostics.reports import Report
from .model import LmtFile


def validate_lmt(lmt: LmtFile) -> Report:
    report = Report()

    if lmt.header.signature != b"LMT\x00":
        report.add_error("lmt.signature", "File signature is not LMT\\x00.")

    if len(lmt.entry_offsets) != lmt.header.entry_count:
        report.add_error("lmt.entry_count", "Entry offset table does not match header entry count.")

    for index, offset in enumerate(lmt.entry_offsets):
        if offset != 0 and offset >= lmt.file_size:
            report.add_error("lmt.action_offset", f"Action offset {index} points outside the file.")

    for action in lmt.actions:
        if action.header.fcurve_count != len(action.tracks):
            report.add_error(
                "lmt.track_count",
                f"Action {action.id} expected {action.header.fcurve_count} tracks but parsed {len(action.tracks)}.",
            )
        if action.header.fcurve_offset and action.header.fcurve_offset >= lmt.file_size:
            report.add_error(
                "lmt.fcurve_offset",
                f"Action {action.id} track table offset points outside the file.",
            )
        if action.header.timl_offset and action.header.timl_offset >= lmt.file_size:
            report.add_warning(
                "lmt.timl_offset",
                f"Action {action.id} TIML offset points outside the file; TIML parsing is not implemented yet.",
            )
        for track_index, track in enumerate(action.tracks):
            header = track.header
            if header.buffer_offset and header.buffer_offset >= lmt.file_size:
                report.add_error(
                    "lmt.buffer_offset",
                    f"Action {action.id} track {track_index} buffer offset points outside the file.",
                )
            if header.buffer_size != len(track.raw_buffer):
                report.add_error(
                    "lmt.buffer_size",
                    f"Action {action.id} track {track_index} buffer size mismatch.",
                )
            if header.lerp_offset and header.lerp_offset >= lmt.file_size:
                report.add_error(
                    "lmt.lerp_offset",
                    f"Action {action.id} track {track_index} lerp offset points outside the file.",
                )

    return report
