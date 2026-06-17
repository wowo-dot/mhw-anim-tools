# MHW Anim Tools

`mhw_anim_tools` is a Blender add-on for Monster Hunter World animation
workflows built around `.lmt` and `.timl` data in Blender.

The repository carries its own core format logic and Blender tooling. Some
developer tools can optionally compare results against external reference
copies during validation work, but the add-on does not depend on those copies
for normal use.

## Start Here

If you are new to the add-on, use these first:

- [Installation](docs/installation.md)
- [Quickstart](docs/quickstart.md)
- [Feature Map](docs/feature-map.md)
- [Basic LMT Workflow](docs/workflow-lmt.md)
- [TIML In LMT Workflow](docs/workflow-timl-in-lmt.md)
- [Testing And Caveats](docs/testing-and-caveats.md)
- [Known Warnings](docs/known-warnings.md)

Main UI locations in Blender:

- `3D View > Sidebar > MHW Anim`: session, armature selection, LMT inspect,
  import, diagnostics, and export
- `Graph Editor > Sidebar > MHW Anim`: TIML Workspace
- `Object Properties > TIML Inspector (Fallback)`: controller fallback view,
  not the main editing surface

Common first tasks:

- inspect an `.lmt`: `LMT Inspector > Inspect LMT`
- import one action: `LMT Inspector > Import Selected`
- import all actions from one source file: `LMT Inspector > Import All`
- edit embedded TIML: `Import TIML`, then `Open TIML Workspace`
- inspect a standalone TIML: `TIML Inspector > Inspect TIML`
- save a standalone TIML session: `Export > Export TIML`
- export the edited source file: `Export > Write Full LMT`
- check for add-on updates: `Edit > Preferences > Add-ons > MHW Anim Tools`

## Validation Snapshot

Current release-confidence highlights:

- `python -m unittest discover -s tests` passes with `268 / 268` tests green
- the full whole-corpus LMT writer-readiness replay currently lands at:
  - `5774 / 5774` files processed
  - `105040 / 105040` actions fully supported
  - `0` replay-planning failures
  - `0` decode-error actions
- embedded TIML corpus scan:
  - `5774 / 5774` LMT files parsed
  - `0` embedded TIML parse errors
- standalone TIML corpus scan:
  - `268 / 268` files parsed
  - `0` validation-error files
- representative live Blender source-backed merge export / reimport smokes pass for:
  - `stm730_084_00`
  - `em037_09` action `048`
  - `em080_00`
  - `em013_03`

## Credits

- Lukas Cone, author of MT Framework tools
- AsteriskAmpersand, author of Free Hyperkinetics
- Free Hyperkinetics credits Stracker and PredatorCZ for background format
  work, including datatype research
- Free Hyperkinetics credits Silvris for TIML work used as the basis of its
  TIMLWorks engine
- Free Hyperkinetics credits DMQW ICE for EFX work used in its TIMLWorks
  engine
- Free Hyperkinetics credits LyraVeil for edge cases and issues from earlier
  import-only tools

## Supported Today

Main supported workflows:

- inspect `.lmt` files, browse entries/tracks, and read diagnostics
- import one action or all actions from a source `.lmt`
- edit supported LMT motion channels and write the full source `.lmt` back
- import attached TIML into controller actions, edit it in the TIML Workspace,
  and write those edits back during source-backed LMT export
- inspect standalone `.timl` files, import selected entries into the same TIML
  Workspace model, and export the edited `.timl` file
- check for add-on updates from Blender preferences

LMT import currently supports:

- supported decoded rotation / translation / scale tracks only
- MhBone / BoneFunction track binding plus root-track fallback
- object-level root-motion binding on MHW-style armatures that do not expose an explicit `Root` bone
- `MHW_Model_Editor` pose-space adaptation for MOD3-imported `MhBone_*`
  armatures:
  local translation samples are converted from game-unit rest positions into
  Blender pose deltas, while root object motion is converted through the MOD3
  import basis
- Blender Action / FCurve creation with linear keys
- diagnostics for skipped, unsupported, or unresolved tracks
- selected-action binding preview against the chosen target armature
- synthetic and live MOD3 smoke coverage for the importer path

LMT export currently supports:

- selected Blender Action sampling for rotation / translation / scale tracks only
- root-track recovery from either an explicit `Root` pose bone or armature-object motion
- MhBone / BoneFunction local track recovery from supported action paths
- inverse `MHW_Model_Editor` space adaptation for MOD3-imported `MhBone_*`
  armatures
- sparse reconstruction back into LMT-style basis / key / root-tail semantics
- conservative export planning that chooses candidate buffer families per track and reports unsupported shapes before binary writing
- duplicate track-slot/source-index validation plus value-dimension validation
  before writing
- raw duplicate-track identity import/export through technical raw channels on
  the resolved pose bone when possible, with armature-level fallback when not
- binary writer coverage for basis vector/quaternion tracks, float vector key tracks, and q14 quaternion key tracks
- q14 writer safety that rejects frame deltas above 255 instead of wrapping them silently
- basis-only exports preserve a nonzero action duration when the reconstructed action range is explicit
- full-source Blender `.lmt` export from the sidebar
- source-aware merge export that preserves sibling actions inside the original container
- raw TIML subtree preservation with absolute-offset rebasing during merged export
- source-backed TIML controller writeback for:
  - unchanged payload preservation
  - value-only edits that preserve advanced source semantics
  - simple-source structural rebuilds from Blender CONSTANT/LINEAR keys
  - explicit blocking for unsafe advanced-source structural rebuilds
- normalized sampled-track diagnostics before any binary packing/compression work
- synthetic and live MOD3 symmetry smoke coverage against decoded LMT source samples and reconstructed sparse tracks
- synthetic and live MOD3 writer roundtrip smoke coverage against decoded LMT source samples
- standalone TIML reader / validator with typed data-entry, transform, and
  keyframe models
- standalone TIML semantics / summary helpers plus a real-corpus profiler for timeline/datatype usage
- LMT-side attached TIML subtree parsing and browser summaries for inspected actions
- imported attached TIML payloads as dedicated Blender controller actions with custom-property fcurves
- standalone TIML inspection/import into the same raw TIML workspace controller model
- standalone TIML file save from inspected controller sessions back to `.timl`
- reverse analysis of imported TIML controller actions back into typed TIML value space, with warnings for unsupported interpolation coverage, split-channel retiming, and quantization risk

Quaternion note:

- raw LMT quaternion tuples are interpreted as `XYZW`
- decoded quaternions exposed by `core/` are normalized to `WXYZ`
- Blender-facing adapters should only consume the decoded `WXYZ` convention

Current limits:

- helper/tether playback
- creating brand-new standalone TIML entry payloads from empty source slots
- broad TIML structural rebuild coverage beyond the current conservative
  source-backed path
- EFX support

## Main Caveats

The current `v1` caveats are mostly about representation and workflow surface,
not broad read/write correctness:

- the main supported export path is still `Write Full LMT` on source-backed
  imported actions
- duplicate raw source tracks with the same `bone_id + usage` identity import as
  technical raw custom-property FCurves:
  - on the resolved pose bone when possible
  - on the armature object when Blender cannot attach them to a real pose bone
- those duplicate/raw channels remain editable and exportable, but they do not
  behave like ordinary viewport pose controls
- Blender is the main editing shell, so the add-on aims to preserve motion
  intent and source semantics rather than recreate Capcom's internal authoring
  environment byte-for-byte for every edited case
- unsupported Blender rig logic, constraints, and procedural setups should be
  baked back into ordinary FCurves before export
- TIML writeback is strong for unchanged payloads, value edits, and the current
  conservative rebuild-friendly structural path, but advanced-source structural
  rebuilds are still intentionally blocked instead of guessed

See also:

- [Testing And Caveats](docs/testing-and-caveats.md)
- [Known Warnings](docs/known-warnings.md)

## Layout

- `core/`: binary, diagnostics, and format logic
- `blender_adapter/`: Blender-facing translation layers
- `integration/`: MHW_Model_Editor and MhBone discovery helpers
- `ui/`: Blender panels, operators, and scene properties
- `tests/`: core tests and fixtures
- `tools/`: optional comparison/debug scripts

Developer / validation tools:

Smoke scripts:

- `tools/smoke_import_all_actions.py`
- `tools/smoke_import_selected_action.py`
- `tools/smoke_import_attached_timl.py`
- `tools/smoke_analyze_timl_controller.py`
- `tools/smoke_merge_export_with_timl_edit.py`
- `tools/smoke_merge_export_with_timl_integer_quantization_block.py`
- `tools/smoke_merge_export_with_shared_timl_value_edit.py`
- `tools/smoke_merge_export_with_timl_simple_structural_edit.py`
- `tools/smoke_merge_export_with_timl_structural_edit.py`
- `tools/run_timl_shared_payload_suite.py`
- `tools/run_timl_simple_structural_suite.py`
- `tools/smoke_sample_export_action.py`
- `tools/smoke_write_lmt_roundtrip.py`

Corpus scans:

- `tools/scan_lmt_export_safety.py`
- `tools/scan_lmt_writer_readiness.py`
- `tools/scan_timl_corpus.py`
- `tools/scan_embedded_timl_corpus.py`

User docs:

- [Installation](docs/installation.md)
- [Quickstart](docs/quickstart.md)
- [Feature Map](docs/feature-map.md)
- [Basic LMT Workflow](docs/workflow-lmt.md)
- [TIML In LMT Workflow](docs/workflow-timl-in-lmt.md)
- [Testing And Caveats](docs/testing-and-caveats.md)
- [Known Warnings](docs/known-warnings.md)
- [Credits And Acknowledgements](docs/credits-and-acknowledgements.md)

Developer / release docs:

- [V1 Release Checklist](docs/v1-release-checklist.md)
- [V1 Validation Matrix](docs/v1-validation-matrix.md)
- [V1 Release Notes Draft](docs/v1-release-notes-draft.md)

Writer-readiness scan notes:

- use `--state <path>` plus `--resume` for long whole-corpus scans
- use `--max-files-per-run` or `--max-seconds` to chunk a scan across sessions
- use `--output <path>` to keep a rolling human-readable summary beside the raw state file

## Optional comparison utilities

Some tools in `tools/` can compare this repository against an external
reference copy. Use that only for:

- file layout expectations
- buffer and flag semantics
- edge-case behavior on known assets

This repository should stay understandable on its own and should not become a
line-by-line port of another add-on.

Those comparison scripts accept an explicit reference-root path instead of
assuming one fixed local workspace layout.
