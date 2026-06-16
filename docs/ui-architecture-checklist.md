# UI / Architecture Checklist

This document turns our recent addon/tooling comparison pass into concrete
guardrails for `mhw_anim_tools`.

It is not a feature roadmap. It is a design checklist we use before adding
more workflow surface area, especially around `LMT`, embedded `TIML`, and later
`EFX`.

Guiding phrase:

> Observable parity where useful, architectural freedom everywhere else.

## Why this exists

The add-on is now far enough along that the main risk is not "missing a parser
detail." The main risk is letting future feature work smear responsibilities
back together:

- binary logic drifting into Blender operators
- the 3D sidebar turning into the whole editor
- diagnostics becoming vague or optimistic
- internal backing properties becoming the user-facing UI by accident

The comparison set reinforced the same themes from different angles:

- Blender `io_scene_gltf2`: separate core I/O from Blender adaptation
- `DragonFF`: reusable standalone binary modules
- `SourceIO`: honest support matrix and partial-support signaling
- `Sollumz`: large-suite UI needs navigation structure, not one giant panel
- `io_scene_psk_psa`: conservative animation workflow, metadata preservation,
  visible testing/CI
- `blender_niftools_addon`: documentation and long-term hygiene matter
- `TIMLJSON`: good structural oracle for TIML, but not a workflow or
  architecture model

## Non-negotiable rules

Before merging a large change, check:

### 1. Core format logic stays Blender-free

- `core/` must not import `bpy`
- parsing, writing, validation, planning, and semantic labeling live outside
  Blender UI modules
- a feature that can be unit-tested without Blender must be implemented there
  first

Good examples:

- `LMT` reader/writer/validation
- `TIML` structure models, labels, summaries, writeback planning
- export readiness planning

Bad examples:

- resolving binary writeback decisions inside a UI operator
- putting hash-label decisions in panel code

### 2. Blender adapters translate, not invent

- `blender_adapter/` converts between core data and Blender data
- adapter code may map coordinate systems, action/fcurve structure, or object
  ownership
- adapter code must not silently guess unsupported semantics into existence

Good examples:

- action import from decoded LMT samples
- TIML controller action creation
- pose-space conversion for MHW-style rigs

Bad examples:

- hidden fallback that binds the wrong armature just to avoid blocking
- UI-only state becoming the source of truth for export

### 3. UI operators stay thin

- operators collect context, call a workflow/service layer, report results
- operators should not own the business rules for export planning, TIML
  writeback classification, or metadata resolution
- when an operator grows orchestration logic, move it into a workflow module

Good shape:

- `operator -> workflow/service -> core/blender_adapter -> diagnostics`

Bad shape:

- `operator` directly reading metadata, picking fallbacks, building plans,
  mutating multiple subsystems, and formatting export truth all in one file

### 4. The sidebar is a cockpit, not a spreadsheet

The `View3D > Sidebar > MHW Anim` surface should stay optimized for:

- active target/controller selection
- quick import/export entry points
- readiness / diagnostics summaries
- one-click analysis and selection helpers

It must not become:

- the full TIML inspector
- a giant raw metadata dump
- the place where dozens of transform details compete for vertical space

### 5. Deep data belongs in a dedicated editor surface

Dense format data should live outside the sidebar in a dedicated editor shell.

For `TIML`, the deep-edit surface is:

- `TIML Workspace`
- Graph Editor plus a dedicated TIML browser/detail panel
- `Properties Editor > TIML Inspector` as a fallback technical view

That surface should be:

- list/detail driven
- semantic first
- raw metadata second
- explicit about writeback mode and risk

### 6. Curve edits stay Blender-native

If users are editing time/value/interpolation, the authoritative editor should
remain the Graph Editor / Dope Sheet / Action system.

We should prefer:

- semantic inspector + curve focus helpers

over:

- building a second custom mini-curve editor in panels

### 7. Unknowns stay visible

If we do not understand a hash, timeline, datatype, or structural case:

- show the unknown value
- explain the limitation
- block unsafe rebuilds

Do not:

- rename unknowns into fake-friendly labels
- silently degrade advanced payloads into "successful" lossy exports

### 8. Support status must be explicit

Follow the spirit of `SourceIO`:

- `Supported`
- `Preview`
- `Blocked`

or the equivalent writeback/diagnostic language we already use.

The user should always be able to tell:

- what is safe
- what is editable
- what is preserved raw
- what is rebuild-only
- what is blocked and why

## UI surface contract

### View3D Sidebar: `MHW Anim`

Keep:

- target armature/context
- import/export entry
- compact status
- analyze/select helpers
- compact TIML workflow launcher/status

Avoid:

- long per-transform detail blocks
- giant embedded metadata tables
- raw JSON-ish backing strings

### TIML Workspace

This is the main deep TIML surface.

It should own:

- controller summary
- source LMT / entry / offset
- grouped semantic block browser
- raw transform browser
- selected block/transform detail
- writeback mode and reason
- focused diagnostics
- curve focus helpers

It should not expose raw custom properties as the intended editing UX.

### Properties Editor: `TIML Inspector`

This is the fallback/debugging surface.

It may mirror:

- controller summary
- source metadata
- selected raw transform details
- diagnostics

### Graph Editor

This remains the real key editor for:

- timing
- values
- interpolation
- easing previews where represented in Blender curves

The TIML workspace should help users navigate to the right curves, not replace
the Graph Editor.

## Data-heavy UI checklist

Before adding a new dense inspector/editor section, verify:

- [ ] Is the summary view separate from the detail view?
- [ ] Is the default state readable on a laptop-height viewport?
- [ ] Are known semantics shown with human labels first?
- [ ] Are unknown values still visible for advanced users?
- [ ] Are dangerous/blocked states obvious before export?
- [ ] Can the user tell what object/action/controller they are editing?
- [ ] Does the section avoid exposing backing implementation blobs by default?

If several answers are "no", the feature is not ready for public UI.

## Module growth watchlist

These are the kinds of smells we should catch early:

### Split soon if they keep growing

- `ui/operators_export.py`
  - risk: turns into a workflow hub instead of operator glue
  - fix: move planning/metadata/writeback orchestration into a workflow module

- `ui/panel_sections.py` or any successor panel module
  - risk: becomes one giant draw sink again
  - fix: split into surface-specific section builders or presenter-backed views

- `ui/operators_timl.py`
  - risk: TIML helper actions, analysis, selection, and future authoring all
    pile together
  - fix: separate select/focus helpers from writeback/analyze workflows

- presenter/view-model modules once `EFX` arrives
  - risk: one presenter starts representing every dense format in the addon
  - fix: keep `TIML` and future `EFX` presenters separate

## Workflow patterns to prefer

### Pattern A: import/export dialog options

Prefer the `glTF` / `Sollumz` style:

- file browser operator settings
- clear import/export panels
- settings stored in properties
- helper validation around filepath/extension and context

### Pattern B: reusable binary packages

Prefer the `DragonFF` style:

- binary module can be imported in isolation
- Blender layer calls into it
- tests can exercise it without Blender

### Pattern C: support-matrix honesty

Prefer the `SourceIO` style:

- visible supported/partial/not planned language
- release docs match reality
- export buttons do not imply guarantees we do not have

### Pattern D: animation workflow conservatism

Prefer the `io_scene_psk_psa` style:

- metadata preservation matters
- import should not do surprising scene-wide mutations
- export should be explicit about source scope and sequence/action ownership

## TIML-specific guardrails

`TIMLJSON` confirms that TIML is structured and layered. Use that insight, but
do not copy its product assumptions blindly.

For our tool, this means:

- model TIML semantically (`time -> timeline -> member -> keyframe`)
- label known hashes carefully
- preserve unknown/advanced payloads whenever possible
- rebuild only when we have a validated safe path

Do not treat:

- partially understood fields
- community guesses
- legacy names

as sufficient reason to expose broad structural authoring too early.

## What this means for v1

Before `v1.0.0`, the UI/architecture direction should look like this:

### Must be true

- [ ] sidebar stays compact and workflow-focused
- [ ] TIML Workspace is the official deep TIML surface, with TIML Inspector as
      fallback
- [ ] Graph Editor remains the actual key editor
- [ ] raw controller custom properties are implementation detail, not the
      intended workflow
- [ ] diagnostics/writeback modes remain explicit and conservative
- [ ] export/import orchestration is not trapped inside UI modules

### Must not happen

- [ ] reintroducing a node-editor-style TIML authoring model for v1
- [ ] packing deep TIML detail back into the 3D sidebar
- [ ] adding structural TIML authoring before the safe edit/writeback path is
      fully trustworthy
- [ ] letting public UI imply that no-TIML files can author brand new TIML
      safely in v1

## Next-change checklist

Use this before starting the next dense TIML/editor change:

1. Define the user task in one sentence
   - example: "edit an existing attached EventLoop safely"

2. Identify the real editing surface
   - sidebar launcher?
   - properties inspector?
   - graph editor?

3. Decide the source of truth
   - core semantic model?
   - Blender action/controller?
   - source-backed metadata?

4. Decide the safety state
   - preserve raw?
   - patch values?
   - rebuild preview?
   - blocked?

5. Add diagnostics before convenience
   - if we cannot explain the state, we are not ready to expose the feature

6. Add unit tests before broad UI surface
   - label resolution
   - summary/view-model generation
   - writeback mode classification
   - unsafe blocking

7. Only then add helpers
   - select
   - focus curves
   - refresh/analyze
   - compact export readiness

## Decision summary

If a future change makes us choose between:

- "more visible all-in-one UI right now"

and

- "clear surface boundaries + conservative semantics"

we choose the second one.

That trade is what turns this from a clever port into a reliable tool.
