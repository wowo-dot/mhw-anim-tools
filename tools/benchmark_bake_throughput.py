"""Run the four-clip Rig44 bake in an isolated directory, inside Blender.

External rigs, samples and reviewed outputs are read only. Every Python write
is confined to --output, including CompactStore and contact calibration output.
See docs/bake-throughput.md for invocation and timing boundaries.
"""

from pathlib import Path
import argparse
import cProfile
import functools
import importlib.util
import json
import os
import pstats
import sys
import tempfile
import time


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-root", type=Path, required=True)
    parser.add_argument("--rig44", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("G8F", "Lara"), required=True)
    parser.add_argument("--mode", choices=("original", "integrated"), default="original")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--cprofile", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    root = args.output.resolve()
    if (root / args.profile).exists():
        raise RuntimeError("Use a fresh output directory; checkpoints would measure resume.")
    root.mkdir(parents=True, exist_ok=True)
    (root / "tmp").mkdir(exist_ok=True)
    tempfile.tempdir = str(root / "tmp")
    sys.dont_write_bytecode = True

    def check_write(path):
        if isinstance(path, (str, bytes, os.PathLike)):
            resolved = Path(os.fsdecode(path)).resolve()
            if not resolved.is_relative_to(root):
                raise RuntimeError(f"Benchmark attempted a write outside its output: {resolved}")

    def audit(event, values):
        if event == "open":
            path, mode, flags = values
            if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                check_write(path)
        elif event in {"os.remove", "os.rmdir", "os.mkdir"}:
            check_write(values[0])
        elif event in {"os.rename", "os.link", "os.symlink"}:
            check_write(values[0])
            check_write(values[1])

    sys.addaudithook(audit)
    spec = importlib.util.spec_from_file_location("mhw_anim_tools", args.addon_root / "__init__.py")
    addon = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = addon
    spec.loader.exec_module(addon)
    sys.path.insert(0, str(args.rig44))
    import bake_common as common
    import locomotion_solver as solver
    import contact_reference
    import numpy as np
    import bpy

    contact_reference.dump = lambda path, value: common.dump(root / args.profile / "contact_reference.json", value)
    integration = None
    if args.mode == "integrated":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from bake_throughput_integration import install
        integration = install(common)

    stats = {}

    def wrap(obj, name, label):
        original = getattr(obj, name)

        @functools.wraps(original)
        def timed(*a, **kw):
            start = time.perf_counter()
            try:
                return original(*a, **kw)
            finally:
                stat = stats.setdefault(label, dict(calls=0, seconds=0.0))
                stat["calls"] += 1
                stat["seconds"] += time.perf_counter() - start

        setattr(obj, name, timed)

    for obj, name, label in (
        (common, "setup", "setup"), (common, "encode", "encode"),
        (common, "replace_entries", "merge_and_preservation"),
        (common, "load_action", "import"), (solver, "solve_sequence", "solve_sequence"),
        (common.Skin, "evaluate", "skin_evaluate"),
    ):
        wrap(obj, name, label)

    rows = json.loads((args.rig44 / "native_source_inspection.json").read_text(encoding="utf-8"))["clips"]
    selected = [{**row, "new_in_Rig44": True} for row in rows if row["full_id"] in {363, 12438, 12439, 8259}]
    assert len(selected) == 4 and sum(row["frames"] for row in selected) == 466
    (root / "sources.json").write_text(json.dumps(dict(clips=selected), indent=2), encoding="utf-8")
    worker = (args.rig44 / "bake_shard.py").read_text(encoding="utf-8")

    def replace(old, new):
        nonlocal worker
        if worker.count(old) != 1:
            raise RuntimeError(f"Caller has changed; review benchmark adaptation: {old}")
        worker = worker.replace(old, new, 1)

    replace("sys.path.insert(0,str(Path(__file__).resolve().parent))", f"sys.path.insert(0,{str(args.rig44)!r})")
    replace("workroot=O/'canary' if args.canary else O", f"workroot=Path({str(root)!r})")
    replace("store=CompactStore(ROOT/'animation_bake/store')", "store=CompactStore(workroot/'store')")
    replace("rows=json.loads((O/('canary_sources.json' if args.canary else 'native_source_inspection.json')).read_text())['clips']",
            "rows=json.loads((workroot/'sources.json').read_text(encoding='utf-8'))['clips']")
    worker_path = root / (args.profile + "_worker.py")
    worker_path.write_text(worker, encoding="utf-8")
    sys.argv = [str(worker_path), "--", "--profile", args.profile, "--shards", "1"]
    profiler = cProfile.Profile() if args.cprofile else None
    wall_start = time.perf_counter()
    if profiler:
        profiler.enable()
    namespace = dict(__name__="__main__", __file__=str(worker_path))
    exec(compile(worker, str(worker_path), "exec"), namespace)
    wall_seconds = time.perf_counter() - wall_start
    bootstrap_and_bake_seconds = time.perf_counter() - started
    if profiler:
        profiler.disable()
        profiler.dump_stats(str(root / (args.profile + ".prof")))
        with (root / (args.profile + "_profile.txt")).open("w", encoding="utf-8") as stream:
            pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(65)

    validation = json.loads((root / args.profile / "validation_shard0.json").read_text())
    if validation["failures"] or len(validation["clips"]) != 4:
        raise RuntimeError(f"Bake validation failed: {validation['failures']}")
    checks = []
    from compact_store import CompactStore
    store = CompactStore(root / "store")
    for row in selected:
        label = f"bank{row['bank']}_entry{row['entry']:03d}"
        raw = store.reconstruct(root / args.profile / "clips" / (label + ".lmtpatch"))
        check = dict(clip=label, output_sha256=common.hashlib.sha256(raw).hexdigest())
        if args.reference:
            ref_archive = args.reference / args.profile / "clips" / (label + ".lmtpatch")
            check["full_lmt_bytes_identical"] = raw == store.reconstruct(ref_archive)
            with np.load(root / args.profile / "readback" / (label + ".npz")) as actual, np.load(args.reference / args.profile / "readback" / (label + ".npz")) as reference:
                # Provenance paths differ between isolated runs; every motion and
                # rest array, identity and verified flag must still match exactly.
                keys = ("names", "poses", "rest", "g8_names", "g8_poses", "source_sha256", "verified")
                check["all_pose_arrays_identical"] = all(np.array_equal(actual[key], reference[key]) for key in keys)
            if not check["full_lmt_bytes_identical"] or not check["all_pose_arrays_identical"]:
                raise RuntimeError(f"Reference mismatch: {check}")
        checks.append(check)
    report = dict(profile=args.profile, mode=args.mode, wall_seconds=wall_seconds,
                  bootstrap_and_bake_seconds=bootstrap_and_bake_seconds,
                  stages=stats, reference_checks=checks, blender=bpy.app.version_string,
                  python=sys.version, addon_root=str(args.addon_root), profiled=bool(profiler),
                  note="Complete four-clip worker, including setup, solve, import, export, readback, validation and compact storage. Stage timers overlap. Excludes process startup and post-run reference comparison.")
    if integration:
        report["cache"] = integration.stats()
    (root / (args.profile + "_stages.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("THROUGHPUT_RESULT", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
