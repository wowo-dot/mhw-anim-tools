# Known Warnings

Last updated on `2026-06-17`.

This page is the short version of the current "what should I actually worry
about?" story for `v1`.

## Duplicate raw LMT track identities

Some source `.lmt` actions contain more than one raw source track with the same
`bone_id + usage` identity.

Corpus frequency in the full extracted game corpus:

- `114 / 5774` `.lmt` files
- `773 / 105040` actions

Current add-on behavior:

- these tracks are imported as clearly named raw custom-property FCurves on
  the resolved pose bone when Blender has a real bone target
- if Blender cannot attach them to a pose bone, they fall back to an
  armature-level raw channel
- they stay inside the same Blender action, so they are editable in the Graph
  Editor and preserved by source-backed export
- they do not drive direct armature pose preview, because Blender cannot map
  multiple source tracks onto one ordinary pose/object transform channel

Practical meaning:

- you can still edit and export them
- you should treat them as technical/raw channels, not as ordinary viewport
  motion controls

## Writer-readiness scan status

The older read-only replay warning about `19` remaining quaternion-edge actions
was real at the time, but it is no longer current.

What we verified after the latest root-basis quaternion planning fix:

- targeted core replay rechecks now pass for:
  - `em037_09.lmt`
  - `em037_10.lmt`
  - `em100_05.lmt`
  - `evm067_00.lmt`
  - `otomo000_00.lmt`
  - `wp_one000.lmt`
- a fresh full whole-corpus writer-readiness rerun is now complete:
  - `5774 / 5774` files processed
  - `105040 / 105040` actions fully supported
  - `0` replay-planning failures
  - `0` decode-error actions

Practical meaning:

- the previously documented `em037` root-rotation blocker was a real planner
  bug in our code, and it is now fixed
- the current source replay path now covers the full extracted game corpus cleanly

## TIML corpus status

The TIML side remains clean in the same full extracted corpus:

- standalone TIML scan: `268 / 268` files parsed, `0` validation-error files
- embedded TIML scan: `5774 / 5774` LMT files parsed, `0` embedded TIML parse
  errors
- embedded supported-transform ratio: `1.0`

## Bottom line

For `v1`, the important warning is no longer "duplicate raw source tracks are a
hard blocker." The current warning is simpler:

- duplicate source tracks are now a technical Graph Editor path
- the current whole-corpus writer-readiness replay now lands cleanly, so the
  remaining release risk is not broad planner coverage but user-facing workflow
  confidence and documented fidelity limits

One useful recent sanity note:

- the baseline live sampled-export / writer-roundtrip path for `stm730_084_00`
  no longer hard-fails after import; the current behavior is a warning-backed
  fallback to `q14` quaternion keys on the affected visible Blender lanes
- the no-edit source-backed merge export path for `stm730_084_00` is now
  byte-identical again after preserving source chunk ordering inside the merge
  writer
