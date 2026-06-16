"""Optional comparison tool for checking the new reader against a legacy reference.

Run this with Blender's Python or another Python environment that has
`mathutils` available, because the legacy reference package depends on it.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core.formats.lmt.reader import read_lmt_file


def load_legacy_package(legacy_root: Path, alias: str = "legacy_reference"):
    init_path = legacy_root / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        alias,
        init_path,
        submodule_search_locations=[str(legacy_root)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not build import spec for {legacy_root}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return importlib.import_module(f"{alias}.struct.Lmt")


def summarize_new_parser(path: Path):
    lmt = read_lmt_file(path)
    return {
        "entry_count": lmt.header.entry_count,
        "action_ids": [action.id for action in lmt.actions],
        "frame_counts": [action.header.frame_count for action in lmt.actions],
        "track_counts": [len(action.tracks) for action in lmt.actions],
        "timl_flags": [action.has_timl for action in lmt.actions],
    }


def summarize_legacy_parser(legacy_module, path: Path):
    legacy_lmt = legacy_module.parseLMT(path)
    return {
        "entry_count": legacy_lmt.Header.entryCount,
        "action_ids": [action.id for action in legacy_lmt.ActionHeaders],
        "frame_counts": [action.frameCount for action in legacy_lmt.ActionHeaders],
        "track_counts": [len(action.bones) for action in legacy_lmt.ActionHeaders],
        "timl_flags": [bool(action.timlOffset) for action in legacy_lmt.ActionHeaders],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("lmt_path", type=Path)
    parser.add_argument("--legacy-root", type=Path, default=None)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    args = parser.parse_args(argv)
    legacy_root = args.legacy_root
    if legacy_root is None:
        env_value = os.environ.get("MHW_ANIM_TOOLS_LEGACY_ROOT", "").strip()
        if env_value:
            legacy_root = Path(env_value)
    if legacy_root is None:
        parser.error("Provide --legacy-root or set MHW_ANIM_TOOLS_LEGACY_ROOT.")

    legacy_module = load_legacy_package(legacy_root)
    result = {
        "new": summarize_new_parser(args.lmt_path),
        "legacy": summarize_legacy_parser(legacy_module, args.lmt_path),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
