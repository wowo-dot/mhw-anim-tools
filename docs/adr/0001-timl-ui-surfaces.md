# ADR 0001: TIML UI Surfaces

## Status

Accepted

## Context

TIML support is now strong enough that the rewrite needs a stable UI contract
 before deeper editing/export milestones land. The current sidebar can launch
 the workflow, but it is not the right place for dense transform-by-transform
 inspection.

We want a UI that matches Blender 4.5 habits, stays readable beside
 `MHW_Model_Editor`, and does not force future redesign once TIML editing grows.

## Decision

We lock the TIML surfaces as follows:

1. The `View3D > Sidebar > MHW Anim` panel remains a workflow hub.
2. The TIML sidebar section is named `TIML Workflow`.
3. A dedicated TIML workspace becomes the primary deep-edit shell.
4. The Graph Editor hosts the main TIML editor in that workspace.
5. The Properties panel remains a technical fallback named `TIML Inspector`.
6. The Graph Editor remains the place where users edit imported TIML preview
   curves.
7. The imported TIML controller object is the inspection anchor.
8. TIML writeback modes are named exactly:
   - `Preserve Raw`
   - `Patch Values`
   - `Rebuild Preview`
   - `Blocked`

## Surface roles

### 1. Sidebar: `TIML Workflow`

Purpose:

- pick or auto-resolve the controller
- select the controller object quickly
- run analysis
- show compact readiness/status counts

Must not become the full editing surface.

### 2. TIML Workspace

Purpose:

- host the main TIML browser/detail editor
- keep block browsing and curve editing visible together
- present both semantic and raw TIML views

### 3. Properties: `TIML Inspector`

Purpose:

- show the active imported controller summary
- show source container metadata
- show transform-by-transform writeback mode
- show per-transform diagnostics and preview structure

This is the fallback/debugging surface, not the primary authoring view.

### 4. Graph Editor

Purpose:

- actual curve editing
- interpolation changes
- keyframe timing/value edits

The inspector reports what those edits imply for writeback; it does not replace
 curve editing.

## First implementation scope

The first inspector milestone should include:

- controller summary
- source LMT / entry / offset summary
- analyze button
- compact writeback counts
- transform list
- selected transform details
- selected transform writeback mode and short explanation

It should not include:

- custom keyframe widgets
- batch retiming tools
- bulk transform repair tools
- EFX editing
- a new node editor surface

## Consequences

Benefits:

- the sidebar stays useful instead of overcrowded
- TIML editing scales without fighting the rest of the add-on
- export/writeback truth can be surfaced without hiding it in operator logs

Trade-offs:

- users will move between Sidebar, TIML Workspace, and Graph Editor instead of doing
  everything in one place
- some state must be mirrored into scene/UI properties for inspection

## Follow-up

Future EFX UI should follow the same pattern:

- sidebar for workflow entry and status
- dedicated inspector surface for dense data
- core editing in Blender-native editors where practical

See also:

- `docs/ui-architecture-checklist.md`
