"""Scan a directory of LMT files and compare summary counts to Old Base.

This is intended to run with Blender's Python because the legacy package uses
Blender-facing dependencies such as ``mathutils``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compare_legacy_lmt import load_legacy_package
from compare_legacy_lmt import summarize_legacy_parser
from compare_legacy_lmt import summarize_new_parser


def compare_one(legacy_module, lmt_path: Path):
    new_summary = summarize_new_parser(lmt_path)
    legacy_summary = summarize_legacy_parser(legacy_module, lmt_path)
    return {
        "path": str(lmt_path),
        "match": new_summary == legacy_summary,
        "new": new_summary,
        "legacy": legacy_summary,
    }


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
    parser.add_argument(
        "--legacy-root",
        type=Path,
        default=Path(r"D:\Freehkwowo\Old Base"),
    )
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output", type=Path, default=None)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    args = parser.parse_args(argv)

    legacy_module = load_legacy_package(args.legacy_root)
    results = []
    for lmt_path in iter_lmt_files(args.asset_root, args.limit):
        try:
            results.append(compare_one(legacy_module, lmt_path))
        except Exception as exc:  # pragma: no cover - debug harness
            results.append(
                {
                    "path": str(lmt_path),
                    "match": False,
                    "error": str(exc),
                }
            )

    summary = {
        "asset_root": str(args.asset_root),
        "legacy_root": str(args.legacy_root),
        "checked": len(results),
        "matches": sum(1 for item in results if item.get("match")),
        "mismatches": sum(1 for item in results if not item.get("match")),
        "results": results,
    }
    text = json.dumps(summary, indent=2)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
