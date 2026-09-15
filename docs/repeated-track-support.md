# Repeated-track support — v1.1.0

This build adds **Build Evaluated Helper** to the LMT Inspector. It creates a
separate source armature using the verified native skeletal binding rule.
Existing Import Selected/Import All actions remain the source-authoring path.
No installation, production bake, pinned snapshot, native extract or game
package was changed while producing this build.

## Supported behavior

The implementation follows the three native binding routines documented in
[the instruction investigation](repeated-track-native-binding.md). In source
file order, each applicable record replaces the binding for its resolved
destination. Sampling uses that complete final record. There is no clip list,
two-record assumption, additive composition or cross-record interpolation.

| Record | Skeletal destination |
| --- | --- |
| Usage 0/1/2, nonnegative bone ID | Model lookup of `bone_id & 511`, then joint rotation/translation/scale |
| Usage 3/4 | Dedicated root rotation/translation, independent of raw bone ID |
| Unmapped/negative ordinary IDs, usage 5 and unknown usages | Unbound in this path; original records retained |

The plan retains every source slot index, its order and the selected index.
It reports identical groups separately from conflicts and resolves aliases
before grouping. Source records remain immutable. The game's separate
first-match `251/translation` control readers still need the original record
list. Their game logic is not implemented as Blender bone animation.

The CPU sampler supports static codecs 1/2, vector codecs 3/4/5 and quaternion
codecs 6/7/11/12/13/14/15 with corresponding usages. It was checked against the
saved native sampler at `0x142234010` and its dispatch table:

- Quantized lerp codecs use `(raw - 8) / (2**bits - 16)` before their stored
  multiplier/addend. Decode operations reproduce float32 rounding.
- Q14 uses a signed 14-bit integer divided by 4096.
- Animated quaternions use shortest-hemisphere linear interpolation of the
  **unnormalized endpoints**, followed by normalization. Static codec 2 copies
  its reference quaternion. Blender converts quaternion values into rotations.
- The first zero-duration key terminates traversal. Random access does not
  depend on the prior frame. Malformed/unsupported winners fail explicitly;
  the implementation never falls back to an earlier record.

These numerical rules differ from the legacy authoring decoder. They apply
only to the evaluated-helper API. The existing decoder, encoder and retargeting
solver retain their behavior and deterministic reference outputs.

## Blender and native time

One copied source hierarchy receives resolved component curves. The template's
bones, hierarchy, constraints, action and mesh modifiers are unchanged. The
helper does not copy rig constraints/drivers. It supplies source motion for
the existing retargeting step; it does not bind character meshes or implement
a new retargeter.

Quaternion FCurves retain key-vector lengths and a continuous hemisphere after
space conversion, reproducing native NLERP at fractional frames through ordinary
Blender evaluation. There are no custom drivers, handlers or Python playback
callbacks. Saved helpers can play without the add-on installed; their raw source
file is required for source-backed exports.

A clip with native count **N** is sampled at **0 through N−1**. Action-header
root vectors are not appended as a synthetic key at N. Native count and loop
frame are recorded separately and preserved by source export. `set_frame`
rejects out-of-range/non-finite times and intentionally changes scene time.
Wrapping, time scales and scene FPS remain caller/context decisions. Blender's
scene end has a minimum of 1; use the recorded native count for one-frame clips.

Missing components require an explicit choice:

- **REST** fills absent components with the copied skeleton's rest pose. It
  does not inherit the template's current pose or a previous clip.
- **ACTION** copies a complete compatible base action for absent components.
  Partial clips such as evc0014:14 need their intended base/context; tests use
  native idle 0:1. The base is a snapshot, not a live NLA dependency. Missing
  channels, modifiers and unsupported interpolation are rejected; bake such a
  base first. The caller must choose the same skeleton/pose space.

A base choice is not proof of the game's cinematic layering recipe. Changed
base/source records, model mapping or rest pose require rebuilding the helper.
Normal reimports now create distinct Actions instead of clearing a same-named
action.

## Export ownership

1. **Exact source snapshot:** `export_source_slots(bank)` returns original bytes.
   Records, events, TIML pointers/payloads, holes, other entries and padding stay
   byte identical.
2. **Explicit raw slot edits:** `export_source_slots(bank, {entry: {slot: track}})`
   replaces named slots, preserving identities, opaque runtime metadata,
   timing/count/order and other records. Edited header/lerp floats use float32.
   The writer relocates TIML, reads back the bank, and compares every ordered
   record and correctly rebased event payload. Address equality alone is never
   proof of event preservation. This API accepts encoded `LmtTrack` records;
   it is not a curve-to-native encoder.
3. **Retargeted animation:** bake onto a separately owned target action using
   the qualified pipeline and its export/readback checks. Normal LMT export
   explicitly rejects evaluated helper actions. Flattening an edited helper
   over duplicate/control records is not an automatic supported operation.

The optional raw authoring action uses the existing importer and exposes its
supported raw channels. Unsupported payloads remain in the immutable bank.
Editing raw authoring curves does not silently update an evaluated snapshot.
Export explicit edits and rebuild from the resulting source when intended.
Missing raw components are export errors. Preservation comparisons now match
each duplicate slot and preserve an entire identity only if all its slots match;
an edited earlier slot cannot disappear behind an unchanged later one.
The legacy UI workflow still disables automatic whole-identity reuse for
duplicate-bearing actions. Exact bytes or explicit per-slot preservation use
the source snapshot/slot APIs above, not an implicit guarantee for raw UI edits.

## Evidence and limits

The portable pre-publication qualification report is
[duplicate-pose-implementation-2026-09-15.json](benchmarks/duplicate-pose-implementation-2026-09-15.json).
The suite passes **318 tests** in Python 3.10 and Blender's Python 3.11. Headless
Blender 4.5.10 checks unique actions, template isolation, subframes/random order,
base inheritance, source replacement, export guards, disposal and exact sampled
matrices after save/reopen.

The implemented plan matches **2,583 saved native binding-loop results**: all
**773 duplicate actions plus 88 ordinary controls**, across 114 banks. It
identifies winners even when downstream context is unsupported. **149 mirrored
monster entries** are blocked pending mirroring/joint-remapping support. This
is a pose-context limit, not a different duplicate-selection rule.

Native instruction sampling comparisons cover ten supplied entries, forward/
backward seek and subframes. Synthetic golden samples cover all ten animated
codecs without requiring game files or research dependencies in the unit suite.
Headless qualification covers those ten entries plus ordinary walk/run/gesture/
bow at every quarter frame. Maximum rotation-matrix component discrepancy is
below 7.5e-7. Largest translation discrepancy is 0.0001172 Blender units (about
0.1172 mm at the MHW meter conversion), on the large translated partial fixture;
it reflects Blender float32 representation. All fourteen exact source round
trips and edited-slot audits pass, including determinism and TIML relocation.

Nonzero joint modes, non-unit winning weights, mirroring, unsupported winning
codecs/usages and malformed samples are diagnosed. Layer weighting, specialized
control consumers, parent placement, SDL visibility, IK and procedural effects
are outside this helper's pose rule. Eorzea arm residuals remain about
**1.62–1.74 degrees RMS** with captured poses and fitted times held fixed. Native
sampling qualification does not qualify those complete cinematic poses or all
retargeted outputs. No tolerance was widened to call them solved.

## Performance and dependencies

Runtime requires Blender/Python only: **no NVIDIA, CUDA, PyTorch, NumPy,
RenderDoc, IDA or Unicorn dependency**. Research-only verification tools use
separate local environments.

The prior complete G8F+Lara benchmark measured 50.030 s baseline versus 37.730 s
with CPU add-on/caller integration (three-run medians, 24.6% reduction).
[bake-throughput.md](bake-throughput.md) gives boundaries and required caller
changes. The implementation report records a fresh complete-operation reference
regression for this build using the unchanged authoring/retargeting path. These
are not GPU kernel timings or a new duplicate-driven G8F/Lara production bake.
Fixture timings include exhaustive comparisons and are not throughput estimates.

Fresh complete-operation check on this build (one sequential sweep, four clips
for G8F then Lara, 932 paired source frames):

| Path | Combined worker time |
| --- | ---: |
| Baseline add-on and caller | 62.963 s |
| Candidate add-on, original caller | 60.376 s |
| Candidate plus CPU caller integration | 47.912 s |

All 24 clip/body reference comparisons in this sweep pass with exact LMT and
motion-array equality. Worker times include setup/import/solve/export/assembly/
readback/validation/storage, excluding process startup, Python bootstrap and
post-run reference comparison. A prior sweep that day measured 65.126/54.042/
39.270 s respectively. The variation makes a precise add-on-only speedup claim
inappropriate. The earlier three-run medians remain the repeated benchmark.

Use [the integration note](duplicate-track-baking-integration.md) and
[worker example](../tools/duplicate_pose_bake_integration.py). Bulk baking remains
paused. The new source path requires explicit caller adoption and existing
quality checks before production use.
