"""Scan real LMT assets for source-backed writer readiness.

This is a core-only, read-only harness. It answers a narrower but more useful
question than standalone-export safety:

- If we decode a source LMT action and convert it straight into reconstructed
  export-prep data, can the current planner represent it again with source
  metadata?

That gives us a practical whole-corpus signal for current writer-family
coverage without requiring Blender or live armatures.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core.formats.lmt.decoder import decode_action_tracks
from core.formats.lmt.export_context import build_source_action_export_context
from core.formats.lmt.export_plan import plan_reconstructed_action_export
from core.formats.lmt.quaternion_source_diagnostics import identify_raw_sensitive_quaternion_identities
from core.formats.lmt.reader import read_lmt_file
from core.formats.lmt.reconstruction import reconstruct_decoded_action


def iter_lmt_files(root: Path, limit: int | None):
    count = 0
    for path in sorted(root.rglob("*.lmt")):
        yield path
        count += 1
        if limit is not None and count >= limit:
            return


def _collect_lmt_files(root: Path, limit: int | None) -> list[Path]:
    return list(iter_lmt_files(root, limit))


def _error_key(diagnostic) -> str:
    source = str(getattr(diagnostic, "source", "") or "")
    message = str(getattr(diagnostic, "message", "") or "")
    return f"{source}: {message}"


def _increment_counter(mapping: dict[str, int], key: str, amount: int = 1) -> None:
    mapping[str(key)] = int(mapping.get(str(key), 0)) + int(amount)


def _append_capped(items: list, item, *, limit: int = 20) -> None:
    if len(items) < int(limit):
        items.append(item)


def _new_state(asset_root: Path, total_files: int, limit: int | None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "asset_root": str(asset_root.resolve()),
        "limit": limit,
        "total_files": int(total_files),
        "next_index": 0,
        "processed_files": 0,
        "checked_files": 0,
        "checked_actions": 0,
        "fully_supported_actions": 0,
        "actions_with_decode_errors": 0,
        "raw_sensitive_action_count": 0,
        "raw_sensitive_track_count": 0,
        "total_track_count": 0,
        "supported_track_count": 0,
        "version_counts": {},
        "buffer_counts": {},
        "plan_error_counts": {},
        "error_count": 0,
        "first_errors": [],
        "unsupported_examples": [],
        "complete": False,
        "last_path": "",
    }


def _load_state(state_path: Path, *, asset_root: Path, total_files: int, limit: int | None) -> dict[str, object]:
    data = json.loads(state_path.read_text(encoding="utf-8"))
    expected_root = str(asset_root.resolve())
    if data.get("asset_root") != expected_root:
        raise SystemExit(
            f"State file '{state_path}' belongs to asset root '{data.get('asset_root')}', "
            f"not '{expected_root}'."
        )
    if data.get("limit") != limit:
        raise SystemExit(
            f"State file '{state_path}' was created with limit={data.get('limit')}, not limit={limit}."
        )
    if int(data.get("total_files", -1)) != int(total_files):
        raise SystemExit(
            f"State file '{state_path}' expects {data.get('total_files')} files, but this run found {total_files}. "
            "Refresh or delete the state file if the asset tree changed."
        )

    data.setdefault("schema_version", 1)
    data.setdefault("next_index", 0)
    data.setdefault("processed_files", 0)
    data.setdefault("checked_files", 0)
    data.setdefault("checked_actions", 0)
    data.setdefault("fully_supported_actions", 0)
    data.setdefault("actions_with_decode_errors", 0)
    data.setdefault("raw_sensitive_action_count", 0)
    data.setdefault("raw_sensitive_track_count", 0)
    data.setdefault("total_track_count", 0)
    data.setdefault("supported_track_count", 0)
    data.setdefault("version_counts", {})
    data.setdefault("buffer_counts", {})
    data.setdefault("plan_error_counts", {})
    data.setdefault("error_count", 0)
    data.setdefault("first_errors", [])
    data.setdefault("unsupported_examples", [])
    data.setdefault("complete", False)
    data.setdefault("last_path", "")
    return data


def _sorted_numeric_key_dict(mapping: dict[str, int]) -> dict[str, int]:
    return {str(key): int(value) for key, value in sorted(mapping.items(), key=lambda item: int(item[0]))}


def _summary_from_state(state: dict[str, object]) -> dict[str, object]:
    checked_actions = int(state["checked_actions"])
    fully_supported_actions = int(state["fully_supported_actions"])
    processed_files = int(state["processed_files"])
    total_files = int(state["total_files"])
    total_track_count = int(state["total_track_count"])
    supported_track_count = int(state["supported_track_count"])
    return {
        "asset_root": str(state["asset_root"]),
        "limit": state["limit"],
        "total_files": total_files,
        "processed_files": processed_files,
        "remaining_files": max(0, total_files - int(state["next_index"])),
        "complete": bool(state["complete"]),
        "last_path": str(state.get("last_path", "") or ""),
        "checked_files": int(state["checked_files"]),
        "checked_actions": checked_actions,
        "fully_supported_actions": fully_supported_actions,
        "unsupported_action_count": checked_actions - fully_supported_actions,
        "actions_with_decode_errors": int(state["actions_with_decode_errors"]),
        "raw_sensitive_action_count": int(state["raw_sensitive_action_count"]),
        "raw_sensitive_track_count": int(state["raw_sensitive_track_count"]),
        "total_track_count": total_track_count,
        "supported_track_count": supported_track_count,
        "unsupported_track_count": total_track_count - supported_track_count,
        "version_counts": _sorted_numeric_key_dict(dict(state["version_counts"])),
        "buffer_counts": _sorted_numeric_key_dict(dict(state["buffer_counts"])),
        "plan_error_counts": dict(
            sorted(
                ((str(key), int(value)) for key, value in dict(state["plan_error_counts"]).items()),
                key=lambda item: (-item[1], item[0]),
            )[:20]
        ),
        "error_count": int(state["error_count"]),
        "first_errors": list(state["first_errors"])[:20],
        "unsupported_examples": list(state["unsupported_examples"])[:20],
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
    total_files = int(state["total_files"])
    processed_files = int(state["processed_files"])
    checked_actions = int(state["checked_actions"])
    fully_supported_actions = int(state["fully_supported_actions"])
    return (
        f"[writer-readiness] files {processed_files}/{total_files} | "
        f"actions {fully_supported_actions}/{checked_actions} fully supported | "
        f"last={state.get('last_path', '')}"
    )


def _process_file(path: Path, state: dict[str, object]) -> None:
    try:
        lmt = read_lmt_file(path)
    except Exception as exc:  # pragma: no cover - debug harness
        state["error_count"] = int(state["error_count"]) + 1
        _append_capped(
            state["first_errors"],
            {"path": str(path), "error": str(exc)},
        )
        return

    state["checked_files"] = int(state["checked_files"]) + 1
    _increment_counter(state["version_counts"], str(int(lmt.header.version)))
    for action in lmt.actions:
        state["checked_actions"] = int(state["checked_actions"]) + 1
        for track in action.tracks:
            _increment_counter(state["buffer_counts"], str(int(track.header.buffer_type)))

        decoded_action = decode_action_tracks(action, strict=False)
        decode_error_tracks = [track for track in decoded_action.tracks if track.decode_error]
        if decode_error_tracks:
            state["actions_with_decode_errors"] = int(state["actions_with_decode_errors"]) + 1

        source_context = build_source_action_export_context(lmt, action.id)
        raw_quaternion_source_identities = identify_raw_sensitive_quaternion_identities(decoded_action)
        if raw_quaternion_source_identities:
            state["raw_sensitive_action_count"] = int(state["raw_sensitive_action_count"]) + 1
            state["raw_sensitive_track_count"] = int(state["raw_sensitive_track_count"]) + len(raw_quaternion_source_identities)

        reconstructed_action = reconstruct_decoded_action(
            decoded_action,
            action_name=f"{path.stem}::{int(action.id)}",
        )
        plan = plan_reconstructed_action_export(
            reconstructed_action,
            track_metadata_by_identity=source_context.track_metadata_by_identity,
            raw_quaternion_source_identities=raw_quaternion_source_identities,
        )

        state["total_track_count"] = int(state["total_track_count"]) + int(plan.track_count)
        state["supported_track_count"] = int(state["supported_track_count"]) + int(plan.supported_track_count)

        if not decode_error_tracks and plan.error_count == 0 and plan.supported_track_count == plan.track_count:
            state["fully_supported_actions"] = int(state["fully_supported_actions"]) + 1
        else:
            for diagnostic in plan.diagnostics:
                if diagnostic.level == "ERROR":
                    _increment_counter(state["plan_error_counts"], _error_key(diagnostic))
            _append_capped(
                state["unsupported_examples"],
                {
                    "path": str(path),
                    "action_id": int(action.id),
                    "decode_error_count": len(decode_error_tracks),
                    "plan_error_count": int(plan.error_count),
                    "supported_track_count": int(plan.supported_track_count),
                    "track_count": int(plan.track_count),
                    "first_plan_errors": [
                        {
                            "source": item.source,
                            "message": item.message,
                        }
                        for item in plan.diagnostics
                        if item.level == "ERROR"
                    ][:5],
                },
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
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--checkpoint-every", type=int, default=25)
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

    summary = _summary_from_state(state)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
