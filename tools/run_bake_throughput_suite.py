"""Run sequential baseline/add-on/caller comparisons in fresh Blender workers."""

from pathlib import Path
import argparse
import hashlib
import json
import statistics
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--rig44", type=Path, required=True)
    parser.add_argument("--baseline-addon", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    repo = Path(__file__).resolve().parent.parent
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    worker = repo / "tools/benchmark_bake_throughput.py"
    manifest = dict(arguments={k: str(v) for k, v in vars(args).items()},
                    implementation_hashes={str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                                           for folder in ("core", "blender_adapter", "tools")
                                           for path in sorted((repo / folder).rglob("*.py"))},
                    caller_hashes={name: hashlib.sha256((args.rig44 / name).read_bytes()).hexdigest()
                                   for name in ("bake_common.py", "bake_shard.py")})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    variants = ("baseline", "addon_only", "integrated")
    results = {name: [] for name in variants}
    for repeat in range(args.repeats):
        # Rotate pair order between repetitions; G8F must precede Lara, which
        # consumes that run's canonical readback. Workers never run concurrently.
        for variant in variants[repeat % 3:] + variants[:repeat % 3]:
            run = root / f"{variant}_{repeat + 1}"
            run.mkdir()
            pair = {}
            for profile in ("G8F", "Lara"):
                command = [str(args.blender), "--background", "--factory-startup", "--disable-autoexec",
                           "--python-exit-code", "1", "--python", str(worker), "--",
                           "--addon-root", str(args.baseline_addon if variant == "baseline" else repo),
                           "--rig44", str(args.rig44), "--output", str(run), "--profile", profile,
                           "--mode", "integrated" if variant == "integrated" else "original",
                           "--reference", str(args.reference)]
                start = time.perf_counter()
                with (run / (profile + ".log")).open("w", encoding="utf-8") as stream:
                    subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                pair[profile] = json.loads((run / (profile + "_stages.json")).read_text(encoding="utf-8"))
                pair[profile]["process_seconds_including_postrun_comparison"] = time.perf_counter() - start
                print(f"{variant} repeat {repeat + 1} {profile}: {pair[profile]['wall_seconds']:.3f}s; reference checks passed", flush=True)
            results[variant].append(pair)
            (root / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    summary = {}
    for variant, repeats in results.items():
        seconds = [sum(pair[p]["wall_seconds"] for p in ("G8F", "Lara")) for pair in repeats]
        summary[variant] = dict(combined_seconds=seconds, median_seconds=statistics.median(seconds),
                                minimum_seconds=min(seconds), maximum_seconds=max(seconds))
    baseline = summary["baseline"]["median_seconds"]
    for variant in variants:
        summary[variant]["speedup_vs_baseline"] = baseline / summary[variant]["median_seconds"]
        summary[variant]["reduction_percent"] = 100 * (1 - summary[variant]["median_seconds"] / baseline)
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
