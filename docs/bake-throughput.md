# Baking throughput

This CPU optimization work targets the Rig44 four-clip pilot: bank 3 entries
150/151, bank 0 entry 363 and bank 2 entry 67. The 466 native frames are baked
for G8F, then Lara consumes that run's G8F readback. No solver, retargeting,
skinning, sampling, quaternion math or interpolation policy is changed.

## Measured result — 2026-09-13

Three fresh runs per variant, sequential Blender 4.5.10 workers. Times combine
the complete G8F and Lara operations; the table uses the median of paired sums.

| Variant | Median | Range | Reduction versus baseline |
| --- | ---: | ---: | ---: |
| Baseline `5243bfc`, original caller | 50.030 s | 49.895–60.524 s | — |
| Current add-on, original caller | 49.376 s | 49.147–54.003 s | 1.3% |
| Current add-on + caller integration | **37.730 s** | **37.710–37.855 s** | **24.6% / 1.326× throughput** |

The automatic add-on-only difference is small relative to run variability;
these three repetitions do not establish a precise speedup for that change
alone. The larger gain requires the caller integration. The supplied earlier
61.836 s measurement is historical context, not the denominator for this result.
Including initial Python imports gives 50.498 s baseline versus 38.043 s
integrated, before process startup and the post-run reference comparison.

Representative inclusive stage medians, summed across both bodies:

| Stage | Baseline | Integrated |
| --- | ---: | ---: |
| Import, including readback import | 6.956 s | 5.129 s |
| Encode, including its source import and analysis | 13.332 s | 10.154 s |
| Append bank and preservation audit | 9.599 s | 1.875 s |
| Solve sequence | 4.371 s | 4.388 s |
| Mesh deformation, across its callers | 3.205 s | 3.219 s |

These rows overlap. They explain where time moved; they are not an additive
breakdown of the total. The solver and deformation work are unchanged.

All eight reviewed final LMTs and every saved motion/rest/name array match
exactly in all three variants and all three repetitions: 72 clip/body reference
comparisons, including 24 for the optimized path. This includes native timing,
loop/root/control data, events, unrelated entries and deterministic chunk layout
through full-file equality. The original integer-frame and subframe readback
checks also pass. Maximum observed errors are unchanged: 0.827 mm joint,
0.831 mm surface, 0.594 mm half-frame surface, 0.748 mm foot target and
0.000705 mm driver axis. These are the existing codec/retarget readback errors,
not differences introduced by the optimization (those arrays match exactly).

The regression suite passes 306 tests under system Python 3.10 and Blender's
bundled Python 3.11. It covers cache invalidation/limits, reader bounds/cursors,
source identity rejection, deterministic raw quaternion export, selected slot
preservation, validation failures, and advanced/replacement TIML rebasing.
Raw timing/validation records live in `corpus_scans/throughput/suite_20260913/`;
the portable summary is [bake-throughput-2026-09-13.json](benchmarks/bake-throughput-2026-09-13.json).

## Remaining work and CUDA assessment

A separate post-change profile passes the same eight reference comparisons.
Compared with the supplied G8F profile, parser calls fall from 24 to 11 and
track-header reads from 690,354 to 195,530. Deep-copy preservation work disappears
(`asdict`: 231,132 to zero; `deepcopy`: 3,040,068 to zero), and source-track
serialization calls fall from 115,943 to 1,886. These are operation counts, not
kernel speedups or unprofiled timings. Each optimized body reports 13 cache hits
and seven misses over 20 loads; two banks remain retained at roughly 80 MiB of
charged storage at the end.

Remaining prominent work includes FCurve sampling, per-frame space/quaternion
conversion, reconstruction/validation and the caller's recipe hash over large
rig files. In the G8F profile, that single recipe hash still costs about three
seconds; it is outside the new source-bank cache. Any future recipe reuse must
retain the existing dependency identity checks and coordinate immutable inputs.
Do not reuse a previous export analysis after editing Blender data.

The local profiles suggest batched space/quaternion conversion as a numerical
candidate for a later experiment, along with the existing skinning prototype.
This is an inference from the remaining CPU work, not evidence that a CUDA
implementation would improve the complete bake. Blender buffer extraction,
transfer/setup cost, batching and identical codec/readback results must all be
measured. No GPU backend is enabled by this change. A larger corpus and the
intended worker concurrency still need validation before extrapolating these
four-clip timings to production throughput. Bulk baking remains paused.

## What changes

- Binary struct reads unpack directly from the existing buffer, avoiding a
  temporary bytes allocation and seek/restore operations for each track header.
  Bounds errors and cursor behavior are preserved.
- `LmtSourceBankCache` reuses parsed immutable source banks and their SHA256
  identities after checking the complete current file contents.
- `write_source_action_export_file` uses the normal planner/encoder to write
  one source-backed action into an intermediate LMT. Other entry slots are
  holes. TIML is included with its addresses rebased.
- Raw-content signature helpers replace recursive `dataclasses.asdict` and
  `deepcopy` in the caller's preservation audit.

Only the binary reader improvement applies automatically to existing callers.
The larger gains require the explicit caller integration below. The regular
`Write Full LMT` behavior and full-bank writer remain the supported UI export.

## Integration for the baking agent

The tested example is [tools/bake_throughput_integration.py](../tools/bake_throughput_integration.py).
It adapts an isolated worker's imported `bake_common` module. It is not imported
by the add-on and has not been installed into the production bake scripts.
The benchmark invokes `install(common)` before importing the worker's functions.

For a permanent caller change, use these pieces directly:

```python
from mhw_anim_tools.core.formats.lmt.source_bank import LmtSourceBankCache
from mhw_anim_tools.blender_adapter.source_identity import SourceFileIdentity
from mhw_anim_tools.blender_adapter.export_workflow import (
    analyze_action_for_export,
    write_source_action_export_file,
)

# Construct inside each Blender worker, not in a parent process.
source_cache = LmtSourceBankCache(max_banks=2, max_bytes=512 * 1024 * 1024)
bank = source_cache.load(source_path)
identity = SourceFileIdentity(size=len(bank.data), sha256=bank.sha256)
# Pass bank.lmt and identity to import_lmt_action_to_armature as before.

# After the existing key_poses call:
analysis = analyze_action_for_export(
    scene_props, action, actions=bpy.data.actions, objects=bpy.data.objects,
    source_cache=source_cache,
)
write_source_action_export_file(encoded_path, analysis)
```

The intermediate artifact keeps the original slot id and container header.
It is **not a full-bank replacement**. Feed it into the existing Rig44
`replace_entries` assembly, which retains native root/control tracks and source
headers, before final readback and compact storage.

The selected action retains the address it would occupy in a normal full merge.
The intermediate file uses zero padding in place of preceding action records.
This matters because Rig44's append assembler sorts encoded and protected
source chunks using their addresses. Removing the padding changes chunk order
even if the motion is identical. Its length is therefore not proportional only
to the selected clip; preceding records are sized but not serialized or parsed
again. Every nonzero pointer in the intermediate still refers to data present
in that file; old TIML pointers are never copied into an empty prefix.

For `replace_entries`, use `bank.data` and `bank.lmt`, then read the completed
file through the same cache. The subsequent `load_action` can reuse that parsed
readback. Small intermediate artifacts are read without adding them to the LRU.
Use `bank.sha256` for the bytes actually loaded; do not memoize a digest by path
alone. The example also verifies that the written bytes equal the readback bytes.

Replace the caller's deep-copy audit with:

```python
from mhw_anim_tools.core.formats.lmt.content_signature import (
    action_header_content_signature,
    track_content_signature,
    timl_payload_content_signature,
)
```

`track_content_signature` retains all header fields except buffer/lerp addresses,
plus the raw buffer and lerp basis. Compare ordered track lists, preserving
duplicate slots. `action_header_content_signature` excludes track-table address,
track count and TIML address; the caller must separately verify track count/order
and event payloads. The example retains the existing full sibling/protected-track
audit and source-prefix equality check.

For rebuilt containers, compare TIML payloads from
`extract_raw_timl_payload_layouts` with `timl_payload_content_signature`, passing
each payload's own source address. This normalizes pointers while retaining
values, raw layout, easing and interpolation. Equal pointers alone are not proof
of preserved events. Rig44's append path can retain its original pointers only
because the entire original payload prefix remains present and is verified
unchanged; the original embedded-pointer validation is still performed.

## Cache behavior

- Opt-in, no global source cache. Each worker owns its cache. A process change
  resets inherited entries and counters; concurrent threads on one instance
  serialize access. Construct a new instance in spawned workers.
- Every `load(path)` opens and reads the file, comparing all bytes with the
  cached snapshot. Equal contents reuse the parse and digest. Changed contents
  trigger parsing and SHA256 again, including same-size, same-mtime edits and
  atomic replacement. Missing or malformed files invalidate that entry and fail.
- Defaults: two banks, 512 MiB of conservatively charged retained storage.
  The charge includes source/raw bytes plus allowances for parsed Python
  objects. It is not an OS RSS measurement. Oversized banks bypass retention.
  Transient reads and snapshots held by the caller can exceed the retained-cache
  budget. `clear()` releases cache ownership; `stats()` exposes counts and charge.
- Raw parsed models and byte strings are read-only snapshots. Do not mutate
  frozen dataclasses through their internals. A load is a snapshot, not a file
  lock; coordinate concurrent source writers outside the bake worker.
- Mutable export contexts, sampled curves, plans, rig state and encoded payloads
  are not cached. Reanalyze after any action, rig, metadata or TIML edit. The
  small per-action metadata maps are rebuilt, avoiding stale analysis reuse.
- The pre-existing dictionary `source_cache` is an operation-local snapshot
  mechanism, not the persistent cache API. Use `LmtSourceBankCache` across clips.

Dependencies: Python standard library only for the add-on changes. Blender
4.5.10/Python 3.11 is the measured runtime. The existing Rig44 caller continues
to use Blender, NumPy and its own rig/assets. No PyTorch, CUDA, driver changes,
package installation or GPU bridge is required. CPU support is retained.

## Reproducing the measurement

Run `tools/run_bake_throughput_suite.py` with system Python, supplying
`--blender`, `--rig44`, `--baseline-addon`, `--reference`, and a fresh `--output`.
The baseline add-on must be a snapshot of commit `5243bfc`; the reference is
the reviewed four-clip run directory containing G8F/Lara clips and readback.

The suite launches one fresh background Blender worker at a time. For each of
three repetitions it runs baseline, current add-on with unchanged caller, and
current add-on with caller integration. It rotates variant order between
repetitions. G8F always precedes Lara. Each pair uses a fresh local CompactStore
and output directory; existing checkpoints are rejected. Python writes are
restricted to that output directory by an audit hook. Original rig files,
production bake artifacts, the production store and game files are read only.

The reported worker wall time includes setup, import, solving, key creation,
analysis/encoding, bank assembly, readback, the original numerical and
preservation checks, array compression and compact-store validation. It
excludes process startup, initial Python imports and the additional post-run
comparison against reviewed references. Bootstrap-plus-bake and process times
are recorded separately. Inclusive stage timers overlap and must not be added.

Use `tools/benchmark_bake_throughput.py --cprofile` inside Blender for a separate
profiled run. Never mix profiler wall times with the unprofiled throughput result.
All measurements here use the CPU; the earlier CUDA skinning kernel benchmark
is not a complete-operation speedup.
