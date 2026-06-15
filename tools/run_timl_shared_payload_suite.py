"""Run the shared-payload TIML value-edit smoke across multiple real assets."""

from __future__ import annotations

import argparse
import json
from json import JSONDecoder
from pathlib import Path
import subprocess
import sys
import time


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core.formats.lmt.reader import read_lmt_file


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_examples(summary_paths: list[Path]) -> tuple[list[dict[str, object]], list[str]]:
    examples: list[dict[str, object]] = []
    missing_example_key_summaries: list[str] = []
    for summary_path in summary_paths:
        payload = _load_json(summary_path)
        if "shared_payload_examples" not in payload:
            missing_example_key_summaries.append(str(summary_path))
            continue
        for example in payload.get("shared_payload_examples", ()):
            if not isinstance(example, dict):
                continue
            cloned = dict(example)
            cloned["_summary_path"] = str(summary_path)
            examples.append(cloned)
    return examples, missing_example_key_summaries


def _expand_examples_by_entry(raw_examples: list[dict[str, object]]) -> list[dict[str, object]]:
    expanded: list[dict[str, object]] = []
    for example in raw_examples:
        entry_indices = [int(value) for value in example.get("entry_indices", ()) if int(value) >= 0]
        action_ids = [int(value) for value in example.get("action_ids", ())]
        if not entry_indices:
            expanded.append(dict(example))
            continue
        for index, entry_index in enumerate(entry_indices):
            variant = dict(example)
            variant["selected_entry_index"] = int(entry_index)
            if index < len(action_ids):
                variant["selected_action_id"] = int(action_ids[index])
            expanded.append(variant)
    return expanded


def _choose_mod3_path(example: dict[str, object]) -> str:
    primary = str(example.get("mod3_path", "") or "")
    if primary and Path(primary).is_file():
        return primary
    for candidate in example.get("mod3_candidates", ()):
        candidate_path = str(candidate or "")
        if candidate_path and Path(candidate_path).is_file():
            return candidate_path
    return ""


def _resolve_entry_index(example: dict[str, object]) -> int:
    selected = int(example.get("selected_entry_index", -1) or -1)
    if selected >= 0:
        return selected
    entry_indices = [int(value) for value in example.get("entry_indices", ()) if int(value) >= 0]
    if entry_indices:
        return entry_indices[0]

    lmt_path = Path(str(example.get("path", "") or ""))
    if not lmt_path.is_file():
        return -1
    action_ids = [int(value) for value in example.get("action_ids", ())] or [-1]
    payload_offset = int(example.get("payload_offset", 0) or 0)
    lmt = read_lmt_file(lmt_path)
    target_action_id = int(action_ids[0])
    for entry_index, action in enumerate(lmt.actions):
        if int(action.id) != target_action_id:
            continue
        if payload_offset > 0 and int(action.header.timl_offset) != payload_offset:
            continue
        return int(entry_index)
    return -1


def _select_examples(raw_examples: list[dict[str, object]], *, limit: int | None, unique_lmt: bool) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    seen_lmt_paths: set[str] = set()
    sortable: list[dict[str, object]] = []
    for example in raw_examples:
        lmt_path = str(example.get("path", "") or "")
        mod3_path = _choose_mod3_path(example)
        entry_index = _resolve_entry_index(example)
        if not lmt_path or not Path(lmt_path).is_file():
            continue
        if not mod3_path:
            continue
        if entry_index < 0:
            continue
        prepared = dict(example)
        prepared["mod3_path"] = mod3_path
        prepared["selected_entry_index"] = int(entry_index)
        sortable.append(prepared)

    sortable.sort(
        key=lambda item: (
            -int(item.get("shared_action_count", 0) or 0),
            -int(item.get("transform_count", 0) or 0),
            -int(item.get("supported_transform_count", 0) or 0),
            str(item.get("path", "") or "").lower(),
            int(item.get("selected_entry_index", -1) or -1),
        )
    )
    for example in sortable:
        lmt_path = str(example.get("path", "") or "")
        if unique_lmt and lmt_path in seen_lmt_paths:
            continue
        seen_lmt_paths.add(lmt_path)
        filtered.append(example)
        if limit is not None and len(filtered) >= int(limit):
            break
    return filtered


def _extract_last_json_blob(text: str):
    decoder = JSONDecoder()
    best = None
    best_span = -1
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            candidate, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and end > best_span:
            best = candidate
            best_span = end
    return best


def _tail(text: str, *, lines: int = 40) -> str:
    chunks = [line for line in text.splitlines() if line.strip()]
    return "\n".join(chunks[-lines:])


def _run_case(*, blender_path: Path, smoke_script: Path, example: dict[str, object]) -> dict[str, object]:
    lmt_path = str(example["path"])
    mod3_path = str(example["mod3_path"])
    entry_index = int(example["selected_entry_index"])
    command = [
        str(blender_path),
        "--factory-startup",
        "--background",
        "--python",
        str(smoke_script),
        "--",
        "--lmt",
        lmt_path,
        "--mod3",
        mod3_path,
        "--entry-index",
        str(entry_index),
    ]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    duration_seconds = time.perf_counter() - started
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    parsed_payload = _extract_last_json_blob(stdout)
    return {
        "path": lmt_path,
        "mod3_path": mod3_path,
        "selected_entry_index": entry_index,
        "action_ids": [int(value) for value in example.get("action_ids", ())],
        "entry_indices": [int(value) for value in example.get("entry_indices", ())],
        "selected_action_id": int(example.get("selected_action_id", -1) or -1),
        "shared_action_count": int(example.get("shared_action_count", 0) or 0),
        "transform_count": int(example.get("transform_count", 0) or 0),
        "supported_transform_count": int(example.get("supported_transform_count", 0) or 0),
        "simple_source_transform_count": int(example.get("simple_source_transform_count", 0) or 0),
        "advanced_source_transform_count": int(example.get("advanced_source_transform_count", 0) or 0),
        "summary_path": str(example.get("_summary_path", "") or ""),
        "returncode": int(completed.returncode),
        "ok": int(completed.returncode) == 0,
        "duration_seconds": round(duration_seconds, 3),
        "payload": parsed_payload,
        "stdout_tail": _tail(stdout),
        "stderr_tail": _tail(stderr),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--scan-summary", dest="scan_summaries", action="append", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--allow-same-lmt", action="store_true")
    parser.add_argument("--expand-shared-entries", action="store_true")
    parser.add_argument("--smoke-script", type=Path, default=SCRIPT_DIR / "smoke_merge_export_with_shared_timl_value_edit.py")
    args = parser.parse_args()

    if not args.blender.is_file():
        raise SystemExit(f"Blender executable does not exist: {args.blender}")
    if not args.smoke_script.is_file():
        raise SystemExit(f"Smoke script does not exist: {args.smoke_script}")
    missing_summaries = [str(path) for path in args.scan_summaries if not path.is_file()]
    if missing_summaries:
        raise SystemExit(f"Missing scan summary file(s): {', '.join(missing_summaries)}")

    raw_examples, missing_example_key_summaries = _collect_examples(args.scan_summaries)
    if args.expand_shared_entries:
        raw_examples = _expand_examples_by_entry(raw_examples)
    selected_examples = _select_examples(
        raw_examples,
        limit=args.limit,
        unique_lmt=not bool(args.allow_same_lmt),
    )
    if not selected_examples:
        if missing_example_key_summaries:
            joined = ", ".join(missing_example_key_summaries)
            raise SystemExit(
                "Provided embedded TIML scan summary file(s) do not contain "
                "'shared_payload_examples'. Regenerate them with the current "
                f"scan tool before running this suite: {joined}"
            )
        raise SystemExit("No runnable shared TIML payload examples were found in the provided scan summaries.")

    print(
        json.dumps(
            {
                "selected_case_count": len(selected_examples),
                "selected_cases": [
                    {
                        "path": str(example["path"]),
                        "mod3_path": str(example["mod3_path"]),
                        "selected_entry_index": int(example["selected_entry_index"]),
                        "selected_action_id": int(example.get("selected_action_id", -1) or -1),
                        "action_ids": [int(value) for value in example.get("action_ids", ())],
                        "shared_action_count": int(example.get("shared_action_count", 0) or 0),
                        "transform_count": int(example.get("transform_count", 0) or 0),
                        "advanced_source_transform_count": int(example.get("advanced_source_transform_count", 0) or 0),
                    }
                    for example in selected_examples
                ],
            },
            indent=2,
        )
    )

    results = []
    for index, example in enumerate(selected_examples, start=1):
        print(
            f"[timl-shared-suite] {index}/{len(selected_examples)} "
            f"action={int(example.get('selected_action_id', -1) or -1):03d} "
            f"entry={int(example['selected_entry_index'])} "
            f"path={example['path']}"
        )
        result = _run_case(
            blender_path=args.blender,
            smoke_script=args.smoke_script,
            example=example,
        )
        results.append(result)
        status = "PASS" if result["ok"] else "FAIL"
        print(
            f"[timl-shared-suite] {status} "
            f"duration={result['duration_seconds']}s "
            f"path={result['path']}"
        )

    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    summary = {
        "selected_case_count": len(selected_examples),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    text = json.dumps(summary, indent=2)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    if failed:
        raise SystemExit(f"TIML shared-payload suite failed on {failed} / {len(results)} case(s).")


if __name__ == "__main__":
    main()
