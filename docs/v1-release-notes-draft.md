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

## Important workflow note

For normal v1 use, prefer `Write Full LMT`.

That path writes the full source container using all imported Blender actions
from the same source file and is the main supported export flow now.

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
