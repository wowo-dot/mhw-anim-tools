# MHW Anim Tools

`mhw_anim_tools` is a clean-room rewrite of the Monster Hunter World Blender
animation tooling used for `.lmt`, `.timl`, `.efx`, and related workflows.

This repository treats `D:\Freehkwowo\Old Base` as a legacy behavior reference,
not as implementation source to keep extending forever.

## Current milestone

Milestone 1 focuses on:

- a clean Blender 4.5 add-on shell
- an original, Blender-independent read-only LMT parser
- a decoded-sample core for LMT track buffers
- a session browser UI that can inspect `.lmt` actions and tracks with readable diagnostics
- unit tests for the new core
- the first narrow Blender Action importer for a selected LMT entry and selected target armature
- the first narrow reverse-path sampler from a selected Blender Action back into normalized MHW track space

Current importer scope:

- supported decoded rotation / translation / scale tracks only
- MhBone / BoneFunction track binding plus root-track fallback
- object-level root-motion binding on MHW-style armatures that do not expose an explicit `Root` bone
- MHW_Model_Editor pose-space adaptation for MOD3-imported `MhBone_*` armatures:
  local translation samples are converted from game-unit rest positions into
  Blender pose deltas, while root object motion is converted through the MOD3
  import basis
- Blender Action / FCurve creation with linear keys
- diagnostics for skipped, unsupported, or unresolved tracks
- selected-action binding preview against the chosen target armature
- synthetic and live MOD3 smoke coverage for the first importer path

Current export-prep scope:

- selected Blender Action sampling for rotation / translation / scale tracks only
- root-track recovery from either an explicit `Root` pose bone or armature-object motion
- MhBone / BoneFunction local track recovery from supported action paths
- inverse MHW_Model_Editor space adaptation for MOD3-imported `MhBone_*` armatures
- sparse reconstruction back into LMT-style basis / key / root-tail semantics
- conservative export planning that chooses candidate buffer families per track and reports unsupported shapes before binary writing
- duplicate track identity and value-dimension validation before writing
- first binary writer milestone for single-action `.lmt` export covering basis vector/quaternion tracks, float vector key tracks, and q14 quaternion key tracks
- q14 writer safety that rejects frame deltas above 255 instead of wrapping them silently
- basis-only exports preserve a nonzero action duration when the reconstructed action range is explicit
- minimal Blender export operator/file dialog from the sidebar and File > Export menu
- source-aware merge export that preserves sibling actions inside the original container
- raw TIML subtree preservation with absolute-offset rebasing during merged export
- normalized sampled-track diagnostics before any binary packing/compression work
- synthetic and live MOD3 symmetry smoke coverage against decoded LMT source samples and reconstructed sparse tracks
- synthetic and live MOD3 writer roundtrip smoke coverage against decoded LMT source samples
- the first standalone TIML core reader / validator with typed data-entry, transform, and keyframe models

Quaternion note:

- raw LMT quaternion tuples are interpreted as `XYZW`
- decoded quaternions exposed by `core/` are normalized to `WXYZ`
- Blender-facing adapters should only consume the decoded `WXYZ` convention

Not implemented yet:

- helper/tether playback
- TIML Blender-side import/export rewrite
- EFX rewrite

## Layout

- `core/`: binary, diagnostics, and format logic
- `blender_adapter/`: Blender-facing translation layers
- `integration/`: MHW_Model_Editor and MhBone discovery helpers
- `ui/`: Blender panels, operators, and scene properties
- `tests/`: core tests and fixtures
- `tools/`: optional comparison/debug scripts

Useful smoke scripts:

- `tools/smoke_import_selected_action.py`
- `tools/smoke_sample_export_action.py`
- `tools/smoke_write_lmt_roundtrip.py`

Useful corpus scans:

- `tools/scan_lmt_export_safety.py`
- `tools/scan_lmt_writer_readiness.py`

Writer-readiness scan notes:

- use `--state <path>` plus `--resume` for long whole-corpus scans
- use `--max-files-per-run` or `--max-seconds` to chunk a scan across sessions
- use `--output <path>` to keep a rolling human-readable summary beside the raw state file

## Legacy reference

Use `D:\Freehkwowo\Old Base` as the reference implementation/spec for:

- file layout expectations
- buffer and flag semantics
- edge-case behavior on known assets

The new code should stay understandable on its own and should not become a
line-by-line port of the legacy add-on.
