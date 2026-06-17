# V1.0 Release Notes Draft

`mhw_anim_tools v1.0.0` is the first public release of the Blender add-on
focused on Monster Hunter World LMT and TIML workflows.

## What v1 is for

This release is meant to be a trustworthy engineer-facing workflow for:

- inspecting `.lmt` files
- importing supported LMT actions into Blender
- editing supported motion tracks
- exporting back through a source-aware merge path
- importing, editing, and writing back embedded TIML payloads inside source
  LMT workflows
- inspecting, editing, and exporting standalone TIML files when the edited
  entries came from an imported source `.timl`

## What is safe today

- source-backed LMT export for supported rotation/translation/scale tracks
- preserving untouched sibling actions inside the original source `.lmt`
- attached TIML import into dedicated controller actions
- value-only TIML edits that preserve advanced source semantics
- simple-source structural TIML rebuilds when the source layout is compatible
- shared embedded TIML payload handling with explicit scope reporting
- standalone TIML export for imported standalone TIML sessions
- blocking unsupported or unsafe export cases instead of silently dropping data

## Validation snapshot

Current release-confidence highlights:

- `268 / 268` unit tests green
- full whole-corpus writer-readiness replay:
  - `5774 / 5774` files
  - `105040 / 105040` actions fully supported
  - `0` replay-planning failures
  - `0` decode-error actions
- representative live Blender source-backed merge export / reimport smokes pass
  for:
  - `stm730_084_00`
  - `em037_09` action `048`
  - `em080_00`
  - `em013_03`

## Important workflow note

For normal v1 use, prefer `Write Full LMT`.

That path writes the full source container using all imported Blender actions
from the same source file and is the main supported export flow now.

## Important caveats

- duplicate raw source tracks are preserved as technical raw custom-property
  FCurves on a pose bone when possible, with armature-level fallback when not
- those raw duplicate-track channels remain editable/exportable, but they are
  not ordinary viewport pose controls
- the add-on is designed to preserve motion intent and source semantics, not to
  claim byte-identical Capcom-internal authoring parity for every edited case
- unsupported Blender rig logic should be baked back into ordinary supported
  FCurves before export
- advanced-source TIML structural rebuilds are still intentionally blocked

## What is intentionally blocked or still out of scope

- creating brand-new standalone TIML entry payloads from empty source slots
- unsafe advanced-source TIML structural rebuilds
- unsupported Blender FCurve paths outside the supported motion channels
- EFX support work
- broad coverage claims for every rare legacy asset edge case

## Current release-confidence focus

The main remaining v1 work is not core architecture. It is release confidence:

- broader real-asset export/reimport validation
- final manual Blender playback checks
- clean install-from-zip validation
- final release packaging and publication cleanup
