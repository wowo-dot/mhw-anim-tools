# Testing And Caveats

This page is the short public answer to two questions:

1. what has actually been tested
2. where should users still keep their eyes open

It is meant to be read alongside:

- [Quickstart](quickstart.md)
- [Basic LMT Workflow](workflow-lmt.md)
- [TIML In LMT Workflow](workflow-timl-in-lmt.md)
- [Known Warnings](known-warnings.md)

## What is strongly tested right now

Automated coverage:

- `292 / 292` unit tests pass
- full LMT writer-readiness replay:
  - `5774 / 5774` extracted `.lmt` files processed
  - `105040 / 105040` actions fully supported in the read-only replay probe
  - `0` replay-planning failures
  - `0` decode-error actions
- embedded TIML corpus scan:
  - `5774 / 5774` LMT files parsed
  - `0` embedded TIML parse errors
- standalone TIML corpus scan:
  - `268 / 268` files parsed
  - `0` validation-error files

Representative live Blender workflow smokes:

- `stm730_084_00`
  - sampled export readiness
  - source-backed merge export / reimport
  - no-edit source-backed merge export returning to byte-identical output
- `em037_09` action `048`
  - sampled export readiness
  - source-backed merge export / reimport
- `em080_00`
  - source-backed merge export / reimport
- `em013_03`
  - source-backed merge export / reimport

TIML workflow coverage also includes:

- attached TIML import
- controller analysis
- unchanged payload preservation
- shared-payload value edits
- simple-source structural rebuilds
- explicit blocking for unsafe structural/quantization-risk cases

## What that testing does and does not mean

What it means:

- the core LMT reader/decoder/replay/export planner path is no longer the weak
  point it used to be
- source-backed LMT export and conservative TIML writeback are the intended
  strong paths
- the add-on is validated against a broad real extracted corpus, not only
  synthetic fixtures

What it does not mean:

- every Blender rig trick is a safe export path
- every raw source structure becomes a normal viewport control
- the add-on reproduces Capcom's original authoring environment exactly in all
  edited cases

## Current practical caveats

## 1. Prefer the source-backed workflow

The main supported export path is:

1. inspect a source `.lmt`
2. import one action or all actions
3. edit the imported action(s)
4. use `Write Full LMT`

That path preserves the source container, sibling actions, TIML payload scope,
and raw slot metadata most reliably.

## 2. Source-backed export now expects the same source file

Imported LMT actions now carry source file identity metadata:

- source file size
- source file SHA256

If the source `.lmt` on disk changes after import, or if the imported action is
missing that identity metadata, source-backed export should be treated as
unsafe. Re-inspect and re-import before writing the full file.

## 3. Duplicate raw source tracks are technical channels

Some source actions contain multiple tracks with the same `bone_id + usage`
identity.

Those tracks are imported as raw custom-property FCurves:

- on the resolved pose bone when Blender has a real target bone
- otherwise on the armature object

They are still editable and source-backed exportable, but they are not ordinary
pose preview lanes. Treat them as technical/raw channels in the Graph Editor.

## 4. Blender preview is not the same thing as source structure

The add-on is designed to preserve motion intent and source semantics in game,
not to claim that every edited action remains internally identical to Capcom's
original authoring process.

That distinction matters most when:

- Blender normalizes or simplifies curve data
- a source track is represented as a technical/raw channel
- a result is motion-equivalent but not structurally identical to the source

## 5. Bake procedural rig behavior before export

Constraints, drivers, retarget setups, and arbitrary helper-rig logic should be
baked back into ordinary supported FCurves before export.

The strongest supported motion paths remain:

- pose-bone `rotation_quaternion`
- pose-bone `location`
- pose-bone `scale`
- armature object root motion

## 6. TIML is conservative on purpose

TIML writeback is intentionally strong where the add-on can preserve meaning
confidently:

- unchanged payloads
- value edits
- shared-payload updates
- conservative rebuild-friendly structural edits

Advanced-source structural rebuilds are still blocked when the raw layout is
not safe to rebuild. That blocking is deliberate.

## 7. Standalone TIML has a narrower promise than source-backed LMT

## 8. Some armatures may gain a helper root-motion bone on import

If an MHW-style armature does not expose a usable explicit root, the importer
may create a non-deforming `MHW_RootMotion` helper bone and parent rootless
bones under it.

That is not random cleanup. It is the adapter making Blender's armature graph
explicit enough to carry root motion sanely.

Standalone `.timl` editing is supported for imported standalone sessions and
full-file saveback.

What is not the main `v1` promise:

- inventing brand-new standalone TIML entry payloads from empty source slots
- implying that all embedded-TIML-safe behaviors automatically generalize to
  every standalone structural authoring scenario

## Bottom line

For `v1`, the add-on is strongest when used as a conservative source-backed
engineering tool:

- inspect real source data
- edit supported motion and TIML values
- export back through the source-aware merge path
- trust explicit warnings/blocks when the tool says a case is unsafe

That is the main contract the current testing supports.
