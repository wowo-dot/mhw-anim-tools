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
from collections import Counter
from pathlib import Path
import sys


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


def _error_key(diagnostic) -> str:
    source = str(getattr(diagnostic, "source", "") or "")
    message = str(getattr(diagnostic, "message", "") or "")
    return f"{source}: {message}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_root", type=Path)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    args = parser.parse_args(argv)

    file_count = 0
    action_count = 0
    fully_supported_actions = 0
    actions_with_decode_errors = 0
    raw_sensitive_action_count = 0
    raw_sensitive_track_count = 0
    total_track_count = 0
    supported_track_count = 0
    version_counts = Counter()
    buffer_counts = Counter()
    plan_error_counts = Counter()
    errors = []
    unsupported_examples = []

    for path in iter_lmt_files(args.asset_root, args.limit):
        try:
            lmt = read_lmt_file(path)
        except Exception as exc:  # pragma: no cover - debug harness
            errors.append({"path": str(path), "error": str(exc)})
            continue

        file_count += 1
        version_counts[int(lmt.header.version)] += 1
        for action in lmt.actions:
            action_count += 1
            for track in action.tracks:
                buffer_counts[int(track.header.buffer_type)] += 1

            decoded_action = decode_action_tracks(action, strict=False)
            decode_error_tracks = [track for track in decoded_action.tracks if track.decode_error]
            if decode_error_tracks:
                actions_with_decode_errors += 1

            source_context = build_source_action_export_context(lmt, action.id)
            raw_quaternion_source_identities = identify_raw_sensitive_quaternion_identities(decoded_action)
            if raw_quaternion_source_identities:
                raw_sensitive_action_count += 1
                raw_sensitive_track_count += len(raw_quaternion_source_identities)

            reconstructed_action = reconstruct_decoded_action(
                decoded_action,
                action_name=f"{path.stem}::{int(action.id)}",
            )
            plan = plan_reconstructed_action_export(
                reconstructed_action,
                track_metadata_by_identity=source_context.track_metadata_by_identity,
                raw_quaternion_source_identities=raw_quaternion_source_identities,
            )

            total_track_count += int(plan.track_count)
            supported_track_count += int(plan.supported_track_count)

            if not decode_error_tracks and plan.error_count == 0 and plan.supported_track_count == plan.track_count:
                fully_supported_actions += 1
            else:
                for diagnostic in plan.diagnostics:
                    if diagnostic.level == "ERROR":
                        plan_error_counts[_error_key(diagnostic)] += 1
                if len(unsupported_examples) < 20:
                    unsupported_examples.append(
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
                        }
                    )

    summary = {
        "asset_root": str(args.asset_root),
        "checked_files": file_count,
        "checked_actions": action_count,
        "fully_supported_actions": fully_supported_actions,
        "actions_with_decode_errors": actions_with_decode_errors,
        "raw_sensitive_action_count": raw_sensitive_action_count,
        "raw_sensitive_track_count": raw_sensitive_track_count,
        "total_track_count": total_track_count,
        "supported_track_count": supported_track_count,
        "unsupported_action_count": action_count - fully_supported_actions,
        "version_counts": dict(sorted(version_counts.items())),
        "buffer_counts": dict(sorted(buffer_counts.items())),
        "plan_error_counts": dict(plan_error_counts.most_common(20)),
        "error_count": len(errors),
        "first_errors": errors[:20],
        "unsupported_examples": unsupported_examples,
    }
    text = json.dumps(summary, indent=2)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
