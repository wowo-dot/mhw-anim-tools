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

## Remaining whole-corpus writer-readiness failures

The full read-only source replay scan now lands at:

- `105021 / 105040` actions fully supported
- `19` actions still unsupported

Current remaining failure families are narrow quaternion edge cases, not the old
duplicate-track family:

- `10` actions in parts of the `em037` corpus with root-rotation samples that
  are not normalized closely enough for planning
- `9` actions across a small set of files where raw source-aware quaternion
  values do not fit the preserved source lerp basis closely enough to allow the
  current fallback path

Representative assets from the latest scan:

- `em037_09.lmt`
- `em037_10.lmt`
- `em100_05.lmt`
- `evm067_00.lmt`
- `otomo000_00.lmt`
- `wp_one000.lmt`

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
- the remaining release-risk family is a much smaller quaternion edge-case set
