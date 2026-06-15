# V1 Validation Matrix

This document turns `v1.0.0` from a vague goal into a concrete validation set.

Use it to track:

- what is already covered by unit tests
- what is already covered by Blender smoke tools
- which real-asset workflows still need manual validation
- which release gates are blocked on confidence rather than implementation

## Status legend

- `Automated`: covered by unit tests and/or repeatable smoke tools
- `Partial`: implementation exists and some automation exists, but manual or
  broader corpus validation is still missing
- `Pending`: not yet validated to release confidence

## Latest observed validation snapshot

Observed on `2026-06-15`:

- `python -m compileall -q .` passed
- `python -m unittest discover -s tests -v` passed with `171/171` tests green
- real-asset grindstone smokes passed:
  - selected LMT action import
  - attached TIML controller import
  - source-backed merge export
  - writer/read-decode roundtrip
- real-asset shared TIML suite passed `3/3` selected cases:
  - `npc018_09_st`
  - `npc016_09`
  - `ncom151_09`
- real-asset simple-source structural TIML suite passed `3/3` selected cases:
  - `st06_ot100`
  - `co00_00`
  - `npc002_00`

Useful note:

- one shared-payload suite case (`npc016_09`) rejected the first MOD3 companion
  candidate because it did not yield a compatible armature, then succeeded on a
  later candidate; this is good evidence that the narrow fallback/companion
  resolution path is behaving explicitly instead of silently binding to the
  wrong thing

## Release-candidate asset set

These are the first assets/workflow families we should keep validating as we
approach `v1.0.0`.

| Asset / family | Why it matters | Current role |
| --- | --- | --- |
| `stm730_084_00` | Baseline live MOD3 + LMT workflow target | Narrow import/export/manual visual sanity target |
| `npc018_09_st` | Nearby nested MOD3 companion resolution case | Embedded TIML / companion discovery coverage |
| `npc706_09` | `.gen` model-reference companion resolution case | Embedded TIML / companion discovery coverage |
| `npc016_09` | body-profile fallback companion resolution case | Embedded TIML / fallback safety coverage |
| `ncom151_09` | known common-motion fallback companion case | Shared TIML payload coverage with explicit narrow fallback |

These names come from real corpus/tooling assumptions already encoded in the
test and scan layer. Before release, we should confirm the exact local asset
paths used for the final smoke runs and keep the release notes generic.

## Workflow matrix

| Area | Workflow | Representative asset(s) | Automated coverage today | Manual validation still needed | Status |
| --- | --- | --- | --- | --- | --- |
| LMT import | Selected action import into MHW-style armature | `stm730_084_00` plus embedded TIML suite examples | `tools/smoke_import_selected_action.py`, live TIML suite imports, importer unit coverage | Playback/pose sanity across a broader asset spread | `Partial` |
| LMT import | Import all actions from one source LMT | synthetic multi-action source | `tools/smoke_import_all_actions.py` | one real multi-action user workflow pass in Blender | `Partial` |
| LMT import | MOD3/MhBone armature binding and pose-space adaptation | `stm730_084_00` | live MOD3 smoke coverage through importer/export tools | confirm on a second and third armature family | `Partial` |
| LMT export | Analyze export readiness from selected Blender action | synthetic + live imported actions | export-prep unit tests, `tools/smoke_sample_export_action.py`, `tools/smoke_timl_export_readiness.py` | user-facing workflow sanity in Blender UI | `Automated` |
| LMT export | Standalone export safety blocking | synthetic source contexts | `tests/test_lmt_export_context.py`, export workflow tests | none beyond normal regression checking | `Automated` |
| LMT export | Source-backed merge export with sibling preservation | synthetic shared-container source + live assets | `tests/test_lmt_merge_writer.py`, `tools/smoke_merge_export_selected_action.py`, live TIML merge smokes | broader real-asset export/reimport spread | `Partial` |
| LMT export | Writer/read-decode roundtrip for supported track families | synthetic actions and imported actions | writer unit tests, `tools/smoke_write_lmt_roundtrip.py` | confirm semantics on more edited real assets | `Partial` |
| TIML import | Attached TIML controller import | `stm730_084_00` plus embedded TIML corpus examples | `tools/smoke_import_attached_timl.py`, TIML reader/validation tests | spot-check controller organization in Blender | `Automated` |
| TIML analysis | Controller analysis and writeback classification | imported controller actions | `tools/smoke_analyze_timl_controller.py`, `tests/test_timl_writeback_plan.py`, `tests/test_timl_ui_labels.py` | none beyond normal UI sanity | `Automated` |
| TIML writeback | Preserve raw unchanged payloads | synthetic embedded payloads + live source-backed export | `tests/test_lmt_merge_writer.py`, `tests/test_timl_writeback.py` | spot-check a no-edit export on a live asset | `Partial` |
| TIML writeback | Value-only TIML edits preserving advanced semantics | shared payload real assets | `tools/smoke_merge_export_with_timl_edit.py`, `tools/smoke_merge_export_with_shared_timl_value_edit.py`, `tools/run_timl_shared_payload_suite.py` | manual playback/semantic checks on a few exported files | `Partial` |
| TIML writeback | Simple-source structural rebuild | rebuild-friendly real assets | `tools/smoke_merge_export_with_timl_simple_structural_edit.py`, `tools/run_timl_simple_structural_suite.py` | manual confirmation that edited timing/value behavior is still sane after reimport | `Partial` |
| TIML writeback | Unsafe structural rebuild blocking | advanced-source and quantization-risk cases | `tools/smoke_merge_export_with_timl_structural_edit.py`, `tools/smoke_merge_export_with_timl_integer_quantization_block.py` | none beyond regression checking | `Automated` |
| Shared payload safety | Detect shared TIML conflicts and impact scope before export | synthetic shared-offset sources + live examples | `tests/test_timl_writeback.py`, `tests/test_export_impact.py`, shared-payload suite | one manual UI sanity pass for conflict/error messaging | `Partial` |
| Corpus readiness | Scan export/TIML corpus for risk and workflow candidates | whole extracted corpus | `tools/scan_lmt_export_safety.py`, `tools/scan_lmt_writer_readiness.py`, `tools/scan_timl_corpus.py`, `tools/scan_embedded_timl_corpus.py` | final RC scan run and archived summary output | `Pending` |

## What still blocks release confidence

Implementation is no longer the main unknown for the narrow v1 scope. The
current blockers are mostly validation and workflow confidence:

1. broader real-asset export/reimport coverage across multiple asset families
2. manual Blender playback checks for root motion and quaternion-heavy actions
3. one clean fresh-install test from a packaged zip
4. short end-user docs for the supported LMT and TIML workflows

## Suggested release-candidate run order

1. Run the unit test suite
2. Run the narrow import/export smokes:
   - `tools/smoke_import_selected_action.py`
   - `tools/smoke_import_all_actions.py`
   - `tools/smoke_write_lmt_roundtrip.py`
3. Run the TIML workflow smokes:
   - `tools/smoke_import_attached_timl.py`
   - `tools/smoke_analyze_timl_controller.py`
   - `tools/smoke_merge_export_with_timl_edit.py`
   - `tools/smoke_merge_export_with_shared_timl_value_edit.py`
   - `tools/smoke_merge_export_with_timl_simple_structural_edit.py`
   - `tools/smoke_merge_export_with_timl_structural_edit.py`
4. Run the real-asset suites:
   - `tools/run_timl_shared_payload_suite.py`
   - `tools/run_timl_simple_structural_suite.py`
5. Run the corpus scans for archived release notes / validation artifacts
6. Do the final manual Blender validation pass on the release-candidate asset
   set
