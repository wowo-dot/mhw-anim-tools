"""Scan embedded TIML payloads referenced by LMT actions.

This is a read-only corpus tool focused on the real workflow path for MHW:
most TIML data lives inside `.lmt` containers, sometimes shared by multiple
actions through the same embedded offset.

The scan answers:
- how many LMT actions reference embedded TIML payloads
- how many unique embedded TIML payloads exist after deduplicating shared offsets
- how common advanced source interpolation/easing is
- how much of the embedded TIML corpus falls into current supported data types
- which payloads/actions are likely "rebuild friendly" vs "patch/preserve only"
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
import time


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core.formats.lmt.reader import read_lmt_file
from core.formats.timl.reader import read_timl_data_bytes
from core.formats.timl.semantics import get_data_type_semantics
from core.formats.timl.semantics import get_interpolation_label


SUPPORTED_TIML_DATA_TYPES = {0, 1, 2, 3, 4}


def iter_lmt_files(root: Path, limit: int | None):
    count = 0
    for path in sorted(root.rglob("*.lmt")):
        yield path
        count += 1
        if limit is not None and count >= limit:
            return


def _collect_lmt_files(root: Path, limit: int | None) -> list[Path]:
    return list(iter_lmt_files(root, limit))


def _append_capped(items: list, item, *, limit: int = 20) -> None:
    if len(items) < int(limit):
        items.append(item)


def _increment(counter: dict[str, int], key: str, amount: int = 1) -> None:
    counter[str(key)] = int(counter.get(str(key), 0)) + int(amount)


def _sorted_counter(counter: dict[str, int], *, numeric: bool = False, topn: int | None = None) -> dict[str, int]:
    items = list(counter.items())
    if numeric:
        items.sort(key=lambda item: int(item[0]))
    else:
        items.sort(key=lambda item: (-int(item[1]), str(item[0])))
    if topn is not None:
        items = items[: int(topn)]
    return {str(key): int(value) for key, value in items}


def _is_integral_frame(value: float) -> bool:
    rounded = round(float(value))
    return math.isclose(float(value), float(rounded), rel_tol=0.0, abs_tol=1e-6)


def _new_state(asset_root: Path, total_files: int, limit: int | None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "asset_root": str(asset_root.resolve()),
        "limit": limit,
        "total_files": int(total_files),
        "next_index": 0,
        "processed_files": 0,
        "checked_files": 0,
        "lmt_parse_error_count": 0,
        "embedded_timl_parse_error_count": 0,
        "action_reference_count": 0,
        "actions_with_timl": 0,
        "unique_payload_count": 0,
        "shared_payload_group_count": 0,
        "shared_payload_reference_count": 0,
        "supported_transform_count": 0,
        "unsupported_data_type_transform_count": 0,
        "simple_source_transform_count": 0,
        "advanced_source_transform_count": 0,
        "payloads_with_advanced_source_count": 0,
        "data_entry_count": 0,
        "type_count": 0,
        "transform_count": 0,
        "keyframe_count": 0,
        "fractional_keyframe_count": 0,
        "max_frame_timing": 0.0,
        "loop_control_counts": {},
        "data_type_counts": {},
        "interpolation_counts": {},
        "easing_counts": {},
        "top_parse_errors": [],
        "advanced_payload_examples": [],
        "unsupported_type_examples": [],
        "complete": False,
        "last_path": "",
    }


def _load_state(state_path: Path, *, asset_root: Path, total_files: int, limit: int | None) -> dict[str, object]:
    data = json.loads(state_path.read_text(encoding="utf-8"))
    expected_root = str(asset_root.resolve())
    if data.get("asset_root") != expected_root:
        raise SystemExit(
            f"State file '{state_path}' belongs to asset root '{data.get('asset_root')}', not '{expected_root}'."
        )
    if data.get("limit") != limit:
        raise SystemExit(
            f"State file '{state_path}' was created with limit={data.get('limit')}, not limit={limit}."
        )
    if int(data.get("total_files", -1)) != int(total_files):
        raise SystemExit(
            f"State file '{state_path}' expects {data.get('total_files')} files, but this run found {total_files}."
        )
    return data


def _summary_from_state(state: dict[str, object]) -> dict[str, object]:
    transform_count = int(state["transform_count"])
    supported_transform_count = int(state["supported_transform_count"])
    return {
        "asset_root": str(state["asset_root"]),
        "limit": state["limit"],
        "total_files": int(state["total_files"]),
        "processed_files": int(state["processed_files"]),
        "remaining_files": max(0, int(state["total_files"]) - int(state["next_index"])),
        "complete": bool(state["complete"]),
        "last_path": str(state.get("last_path", "") or ""),
        "checked_files": int(state["checked_files"]),
        "lmt_parse_error_count": int(state["lmt_parse_error_count"]),
        "embedded_timl_parse_error_count": int(state["embedded_timl_parse_error_count"]),
        "action_reference_count": int(state["action_reference_count"]),
        "actions_with_timl": int(state["actions_with_timl"]),
        "unique_payload_count": int(state["unique_payload_count"]),
        "shared_payload_group_count": int(state["shared_payload_group_count"]),
        "shared_payload_reference_count": int(state["shared_payload_reference_count"]),
        "data_entry_count": int(state["data_entry_count"]),
        "type_count": int(state["type_count"]),
        "transform_count": transform_count,
        "supported_transform_count": supported_transform_count,
        "unsupported_data_type_transform_count": int(state["unsupported_data_type_transform_count"]),
        "simple_source_transform_count": int(state["simple_source_transform_count"]),
        "advanced_source_transform_count": int(state["advanced_source_transform_count"]),
        "payloads_with_advanced_source_count": int(state["payloads_with_advanced_source_count"]),
        "keyframe_count": int(state["keyframe_count"]),
        "fractional_keyframe_count": int(state["fractional_keyframe_count"]),
        "max_frame_timing": float(state["max_frame_timing"]),
        "loop_control_counts": _sorted_counter(dict(state["loop_control_counts"]), numeric=True),
        "data_type_counts": _sorted_counter(dict(state["data_type_counts"])),
        "interpolation_counts": _sorted_counter(dict(state["interpolation_counts"])),
        "easing_counts": _sorted_counter(dict(state["easing_counts"]), numeric=True),
        "top_parse_errors": list(state["top_parse_errors"])[:20],
        "advanced_payload_examples": list(state["advanced_payload_examples"])[:20],
        "unsupported_type_examples": list(state["unsupported_type_examples"])[:20],
        "supported_transform_ratio": (float(supported_transform_count) / float(transform_count)) if transform_count else 0.0,
    }


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _write_checkpoint(state: dict[str, object], *, state_path: Path | None, output_path: Path | None) -> None:
    if state_path is not None:
        _write_json_atomic(state_path, state)
    if output_path is not None:
        _write_json_atomic(output_path, _summary_from_state(state))


def _progress_message(state: dict[str, object]) -> str:
    return (
        f"[embedded-timl] files {int(state['processed_files'])}/{int(state['total_files'])} | "
        f"payloads {int(state['unique_payload_count'])} | "
        f"actions_with_timl {int(state['actions_with_timl'])} | "
        f"last={state.get('last_path', '')}"
    )


def _process_payload(state: dict[str, object], *, lmt_path: Path, payload_offset: int, payload_action_ids: list[int], source_bytes: bytes) -> None:
    try:
        data_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=int(payload_offset),
            source_name=f"{lmt_path}#timl",
            entry_id=int(payload_action_ids[0]),
        )
    except Exception as exc:  # pragma: no cover - debug harness
        state["embedded_timl_parse_error_count"] = int(state["embedded_timl_parse_error_count"]) + 1
        _append_capped(
            state["top_parse_errors"],
            {
                "path": str(lmt_path),
                "payload_offset": int(payload_offset),
                "action_ids": [int(action_id) for action_id in payload_action_ids],
                "error": str(exc),
            },
        )
        return

    state["unique_payload_count"] = int(state["unique_payload_count"]) + 1
    state["data_entry_count"] = int(state["data_entry_count"]) + 1
    state["type_count"] = int(state["type_count"]) + len(data_entry.types)
    state["transform_count"] = int(state["transform_count"]) + sum(len(type_entry.transforms) for type_entry in data_entry.types)
    state["keyframe_count"] = int(state["keyframe_count"]) + sum(
        len(transform.keyframes)
        for type_entry in data_entry.types
        for transform in type_entry.transforms
    )
    _increment(state["loop_control_counts"], str(int(data_entry.loop_control)))

    payload_has_advanced_source = False
    payload_unsupported_types: list[int] = []
    for type_index, type_entry in enumerate(data_entry.types):
        for transform_index, transform in enumerate(type_entry.transforms):
            semantics = get_data_type_semantics(transform.data_type)
            _increment(state["data_type_counts"], semantics.name)
            if int(transform.data_type) in SUPPORTED_TIML_DATA_TYPES:
                state["supported_transform_count"] = int(state["supported_transform_count"]) + 1
            else:
                state["unsupported_data_type_transform_count"] = int(state["unsupported_data_type_transform_count"]) + 1
                payload_unsupported_types.append(int(transform.data_type))

            transform_has_advanced_source = False
            for keyframe in transform.keyframes:
                _increment(state["interpolation_counts"], get_interpolation_label(int(keyframe.interpolation)))
                _increment(state["easing_counts"], str(int(keyframe.easing)))
                frame_timing = float(keyframe.frame_timing)
                state["max_frame_timing"] = max(float(state["max_frame_timing"]), frame_timing)
                if not _is_integral_frame(frame_timing):
                    state["fractional_keyframe_count"] = int(state["fractional_keyframe_count"]) + 1
                if int(keyframe.interpolation) not in {0, 1} or int(keyframe.easing) != 0:
                    transform_has_advanced_source = True
            if transform_has_advanced_source:
                payload_has_advanced_source = True
                state["advanced_source_transform_count"] = int(state["advanced_source_transform_count"]) + 1
            else:
                state["simple_source_transform_count"] = int(state["simple_source_transform_count"]) + 1

    if payload_has_advanced_source:
        state["payloads_with_advanced_source_count"] = int(state["payloads_with_advanced_source_count"]) + 1
        _append_capped(
            state["advanced_payload_examples"],
            {
                "path": str(lmt_path),
                "payload_offset": int(payload_offset),
                "action_ids": [int(action_id) for action_id in payload_action_ids],
                "transform_count": sum(len(type_entry.transforms) for type_entry in data_entry.types),
            },
        )
    if payload_unsupported_types:
        _append_capped(
            state["unsupported_type_examples"],
            {
                "path": str(lmt_path),
                "payload_offset": int(payload_offset),
                "action_ids": [int(action_id) for action_id in payload_action_ids],
                "data_types": sorted(set(int(value) for value in payload_unsupported_types)),
            },
        )


def _process_file(path: Path, state: dict[str, object]) -> None:
    try:
        lmt = read_lmt_file(path)
    except Exception as exc:  # pragma: no cover - debug harness
        state["lmt_parse_error_count"] = int(state["lmt_parse_error_count"]) + 1
        _append_capped(
            state["top_parse_errors"],
            {"path": str(path), "error": str(exc)},
        )
        return

    state["checked_files"] = int(state["checked_files"]) + 1
    source_bytes = path.read_bytes()
    actions_with_timl = [action for action in lmt.actions if bool(action.has_timl) and int(action.header.timl_offset) > 0]
    state["action_reference_count"] = int(state["action_reference_count"]) + len(lmt.actions)
    state["actions_with_timl"] = int(state["actions_with_timl"]) + len(actions_with_timl)
    if not actions_with_timl:
        return

    payload_groups: dict[int, list[int]] = {}
    for action in actions_with_timl:
        payload_groups.setdefault(int(action.header.timl_offset), []).append(int(action.id))

    for action_ids in payload_groups.values():
        if len(action_ids) > 1:
            state["shared_payload_group_count"] = int(state["shared_payload_group_count"]) + 1
            state["shared_payload_reference_count"] = int(state["shared_payload_reference_count"]) + len(action_ids)

    for payload_offset, payload_action_ids in sorted(payload_groups.items()):
        _process_payload(
            state,
            lmt_path=path,
            payload_offset=int(payload_offset),
            payload_action_ids=payload_action_ids,
            source_bytes=source_bytes,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_root", type=Path)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-files-per-run", type=int, default=None)
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    args = parser.parse_args(argv)
    if args.resume and args.state is None:
        raise SystemExit("--resume requires --state <path>.")

    all_files = _collect_lmt_files(args.asset_root, args.limit)
    if args.resume:
        if args.state is None or not args.state.is_file():
            raise SystemExit(f"Could not resume because state file '{args.state}' does not exist.")
        state = _load_state(
            args.state,
            asset_root=args.asset_root,
            total_files=len(all_files),
            limit=args.limit,
        )
    else:
        state = _new_state(args.asset_root, len(all_files), args.limit)

    if bool(state["complete"]):
        summary = _summary_from_state(state)
        text = json.dumps(summary, indent=2)
        if args.output is not None:
            _write_json_atomic(args.output, summary)
        print(text)
        return

    start_time = time.perf_counter()
    processed_this_run = 0
    max_files_per_run = int(args.max_files_per_run) if args.max_files_per_run is not None else None
    progress_every = int(args.progress_every) if args.progress_every is not None else 0
    checkpoint_every = int(args.checkpoint_every) if args.checkpoint_every is not None else 0

    while int(state["next_index"]) < len(all_files):
        if max_files_per_run is not None and processed_this_run >= max_files_per_run:
            break
        if args.max_seconds is not None and processed_this_run > 0:
            if (time.perf_counter() - start_time) >= float(args.max_seconds):
                break

        index = int(state["next_index"])
        path = all_files[index]
        _process_file(path, state)
        state["next_index"] = index + 1
        state["processed_files"] = int(state["processed_files"]) + 1
        state["last_path"] = str(path)
        processed_this_run += 1

        if progress_every > 0 and (processed_this_run % progress_every) == 0:
            print(_progress_message(state), file=sys.stderr)
        if checkpoint_every > 0 and (processed_this_run % checkpoint_every) == 0:
            _write_checkpoint(state, state_path=args.state, output_path=args.output)

    state["complete"] = int(state["next_index"]) >= len(all_files)
    _write_checkpoint(state, state_path=args.state, output_path=args.output)
    print(json.dumps(_summary_from_state(state), indent=2))


if __name__ == "__main__":
    main()
