"""Scan real TIML assets for structural and semantic coverage clues."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core.formats.timl.reader import read_timl_file
from core.formats.timl.semantics import format_hash_label
from core.formats.timl.semantics import get_data_type_semantics
from core.formats.timl.semantics import get_interpolation_label
from core.formats.timl.validation import validate_timl


def iter_timl_files(root: Path, limit: int | None):
    count = 0
    for path in sorted(root.rglob("*.timl")):
        yield path
        count += 1
        if limit is not None and count >= limit:
            return


def _load_hash_name_map(path: Path | None) -> dict[int, str]:
    if path is None:
        return {}
    mapping: dict[int, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            hash_value = int(parts[0])
        except ValueError:
            continue
        mapping[hash_value & 0xFFFFFFFF] = parts[1]
    return mapping


def _increment(counter: Counter, key, amount: int = 1) -> None:
    counter[key] += int(amount)


def _append_capped(items: list, item: object, *, limit: int = 20) -> None:
    if len(items) < int(limit):
        items.append(item)


def _is_integral_frame(value: float) -> bool:
    rounded = round(float(value))
    return math.isclose(float(value), float(rounded), rel_tol=0.0, abs_tol=1e-6)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_root", type=Path)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--timeline-reference", type=Path, default=None)
    parser.add_argument("--datatype-reference", type=Path, default=None)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    args = parser.parse_args(argv)

    timeline_names = _load_hash_name_map(args.timeline_reference)
    datatype_names = _load_hash_name_map(args.datatype_reference)

    file_count = 0
    parsed_file_count = 0
    validation_error_file_count = 0
    validation_warning_file_count = 0
    total_data_entries = 0
    total_types = 0
    total_transforms = 0
    total_keyframes = 0
    total_fractional_keyframes = 0
    max_frame_timing = 0.0
    loop_control_counts: Counter[int] = Counter()
    data_type_counts: Counter[str] = Counter()
    interpolation_counts: Counter[str] = Counter()
    easing_counts: Counter[int] = Counter()
    timeline_hash_counts: Counter[int] = Counter()
    datatype_hash_counts: Counter[int] = Counter()
    datatype_hash_data_types: dict[int, set[int]] = {}
    errors: list[dict[str, object]] = []
    validation_examples: list[dict[str, object]] = []
    datatype_mismatch_examples: list[dict[str, object]] = []

    for path in iter_timl_files(args.asset_root, args.limit):
        file_count += 1
        try:
            timl = read_timl_file(path)
        except Exception as exc:  # pragma: no cover - debug harness
            _append_capped(errors, {"path": str(path), "error": str(exc)})
            continue

        parsed_file_count += 1
        report = validate_timl(timl)
        if report.error_count:
            validation_error_file_count += 1
        if report.warning_count:
            validation_warning_file_count += 1
        if report.error_count or report.warning_count:
            _append_capped(
                validation_examples,
                {
                    "path": str(path),
                    "error_count": report.error_count,
                    "warning_count": report.warning_count,
                    "diagnostics": [
                        {
                            "level": diagnostic.level,
                            "code": diagnostic.code,
                            "message": diagnostic.message,
                        }
                        for diagnostic in report.diagnostics[:5]
                    ],
                },
            )

        total_data_entries += timl.data_count
        total_types += timl.type_count
        total_transforms += timl.transform_count
        total_keyframes += timl.keyframe_count

        for entry in timl.data_entries:
            _increment(loop_control_counts, int(entry.loop_control))
            for type_entry in entry.types:
                _increment(timeline_hash_counts, int(type_entry.timeline_parameter_hash) & 0xFFFFFFFF)
                for transform in type_entry.transforms:
                    semantics = get_data_type_semantics(transform.data_type)
                    _increment(data_type_counts, semantics.name)
                    _increment(datatype_hash_counts, int(transform.datatype_hash) & 0xFFFFFFFF)
                    datatype_hash_data_types.setdefault(int(transform.datatype_hash) & 0xFFFFFFFF, set()).add(int(transform.data_type))
                    for keyframe in transform.keyframes:
                        _increment(interpolation_counts, get_interpolation_label(int(keyframe.interpolation)))
                        _increment(easing_counts, int(keyframe.easing))
                        max_frame_timing = max(max_frame_timing, float(keyframe.frame_timing))
                        if not _is_integral_frame(float(keyframe.frame_timing)):
                            total_fractional_keyframes += 1

    for datatype_hash, data_types in sorted(datatype_hash_data_types.items()):
        if len(data_types) > 1:
            _append_capped(
                datatype_mismatch_examples,
                {
                    "datatype_hash": datatype_hash,
                    "datatype_label": format_hash_label(datatype_hash, datatype_names),
                    "data_types": sorted(int(value) for value in data_types),
                },
            )

    summary = {
        "asset_root": str(args.asset_root),
        "checked_files": int(file_count),
        "parsed_files": int(parsed_file_count),
        "parse_error_count": len(errors),
        "validation_error_file_count": int(validation_error_file_count),
        "validation_warning_file_count": int(validation_warning_file_count),
        "data_entry_count": int(total_data_entries),
        "type_count": int(total_types),
        "transform_count": int(total_transforms),
        "keyframe_count": int(total_keyframes),
        "fractional_keyframe_count": int(total_fractional_keyframes),
        "max_frame_timing": float(max_frame_timing),
        "loop_control_counts": {str(key): int(value) for key, value in sorted(loop_control_counts.items())},
        "data_type_counts": {str(key): int(value) for key, value in sorted(data_type_counts.items(), key=lambda item: (-item[1], item[0]))},
        "interpolation_counts": {str(key): int(value) for key, value in sorted(interpolation_counts.items(), key=lambda item: (-item[1], item[0]))},
        "easing_counts": {str(key): int(value) for key, value in sorted(easing_counts.items(), key=lambda item: (-item[1], int(item[0])))},
        "top_timeline_hashes": [
            {
                "hash": int(hash_value),
                "label": format_hash_label(hash_value, timeline_names),
                "count": int(count),
            }
            for hash_value, count in timeline_hash_counts.most_common(30)
        ],
        "top_datatype_hashes": [
            {
                "hash": int(hash_value),
                "label": format_hash_label(hash_value, datatype_names),
                "count": int(count),
                "data_types": sorted(int(value) for value in datatype_hash_data_types.get(hash_value, set())),
            }
            for hash_value, count in datatype_hash_counts.most_common(40)
        ],
        "datatype_hash_multi_type_count": sum(1 for values in datatype_hash_data_types.values() if len(values) > 1),
        "datatype_hash_multi_type_examples": datatype_mismatch_examples,
        "validation_examples": validation_examples,
        "first_errors": errors[:20],
    }
    text = json.dumps(summary, indent=2)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
