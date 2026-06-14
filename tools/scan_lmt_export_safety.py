"""Scan real LMT assets for standalone-export safety and format coverage.

This script is intentionally read-only. It helps answer:
- how common TIML-backed actions are
- how often a single-action standalone export would be safe today
- which buffer families appear in the scanned assets
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

from core.formats.lmt.export_context import assess_standalone_export_context
from core.formats.lmt.export_context import build_source_action_export_context
from core.formats.lmt.reader import read_lmt_file


def iter_lmt_files(root: Path, limit: int | None):
    count = 0
    for path in sorted(root.rglob("*.lmt")):
        yield path
        count += 1
        if limit is not None and count >= limit:
            return


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

    buffer_counts = Counter()
    version_counts = Counter()
    blocked_code_counts = Counter()
    file_count = 0
    action_count = 0
    standalone_safe_actions = 0
    errors = []

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
            context = build_source_action_export_context(lmt, action.id)
            report = assess_standalone_export_context(context)
            if report.error_count == 0:
                standalone_safe_actions += 1
            for diagnostic in report.diagnostics:
                if diagnostic.level == "error":
                    blocked_code_counts[diagnostic.code] += 1

    summary = {
        "asset_root": str(args.asset_root),
        "checked_files": file_count,
        "checked_actions": action_count,
        "standalone_safe_actions": standalone_safe_actions,
        "blocked_error_counts": dict(sorted(blocked_code_counts.items())),
        "version_counts": dict(sorted(version_counts.items())),
        "buffer_counts": dict(sorted(buffer_counts.items())),
        "error_count": len(errors),
        "first_errors": errors[:20],
    }
    text = json.dumps(summary, indent=2)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
