"""Validation rules for parsed TIML data."""

from __future__ import annotations

from ...diagnostics.reports import Report
from .model import EXPECTED_LAYOUT_SIGNATURE
from .model import TimlFile


def _validate_entry_offsets(report: Report, timl: TimlFile) -> None:
    for index, offset in enumerate(timl.entry_offsets):
        if offset != 0 and offset >= timl.file_size:
            report.add_error("timl.data_offset", f"Data entry offset {index} points outside the file.")


def _validate_transform(report: Report, timl: TimlFile, *, entry_id: int, type_index: int, transform_index: int, transform) -> None:
    if len(transform.keyframes) != transform.keyframe_count:
        report.add_error(
            "timl.keyframe_count",
            f"Data entry {entry_id} type {type_index} transform {transform_index} expected "
            f"{transform.keyframe_count} keyframes but parsed {len(transform.keyframes)}.",
        )
    if transform.keyframe_table_offset >= timl.file_size and transform.keyframe_count:
        report.add_error(
            "timl.keyframe_table_offset",
            f"Data entry {entry_id} type {type_index} transform {transform_index} keyframe table points outside the file.",
        )


def _validate_type(report: Report, timl: TimlFile, *, entry_id: int, type_index: int, type_entry) -> None:
    if len(type_entry.transforms) != type_entry.transform_count:
        report.add_error(
            "timl.transform_count",
            f"Data entry {entry_id} type {type_index} expected {type_entry.transform_count} transforms but parsed {len(type_entry.transforms)}.",
        )
    if type_entry.transform_table_offset >= timl.file_size and type_entry.transform_count:
        report.add_error(
            "timl.transform_table_offset",
            f"Data entry {entry_id} type {type_index} transform table points outside the file.",
        )
    for transform_index, transform in enumerate(type_entry.transforms):
        _validate_transform(
            report,
            timl,
            entry_id=entry_id,
            type_index=type_index,
            transform_index=transform_index,
            transform=transform,
        )


def _validate_entry(report: Report, timl: TimlFile, entry) -> None:
    if len(entry.types) != entry.type_count:
        report.add_error(
            "timl.type_count",
            f"Data entry {entry.id} expected {entry.type_count} types but parsed {len(entry.types)}.",
        )
    if entry.type_table_offset >= timl.file_size and entry.type_count:
        report.add_error("timl.type_table_offset", f"Data entry {entry.id} type table points outside the file.")
    for type_index, type_entry in enumerate(entry.types):
        _validate_type(report, timl, entry_id=entry.id, type_index=type_index, type_entry=type_entry)


def validate_timl(timl: TimlFile) -> Report:
    report = Report()

    if timl.header.signature != b"timl":
        report.add_error("timl.signature", "File signature is not timl.")

    if timl.header.layout_signature != EXPECTED_LAYOUT_SIGNATURE:
        report.add_warning("timl.layout_signature", "TIML layout signature differs from the common MHW pattern.")

    if len(timl.entry_offsets) != timl.header.entry_count:
        report.add_error("timl.entry_count", "Entry offset table does not match header entry count.")

    if timl.header.entry_table_offset >= timl.file_size and timl.header.entry_count:
        report.add_error("timl.entry_table_offset", "Entry offset table points outside the file.")

    _validate_entry_offsets(report, timl)

    for entry in timl.data_entries:
        _validate_entry(report, timl, entry)

    return report
