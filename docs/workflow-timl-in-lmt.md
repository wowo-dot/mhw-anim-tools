# TIML In LMT Workflow

This is the supported v1 path for editing embedded TIML data.

Main UI locations:

- `3D View > Sidebar > MHW Anim`
- `Graph Editor > Sidebar > MHW Anim`

## 1. Inspect an LMT that has attached TIML

1. In the sidebar, click `Inspect LMT`
2. Select an entry that reports `TIML attached`
3. Use `Import TIML`

This creates a TIML controller object/action in Blender for that source entry.

Added LMT slots also seed a blank attached TIML controller. That means a new
entry can move straight into the same TIML Workspace flow instead of getting
stuck as a no-TIML placeholder.

## 2. Open the TIML workspace

Use `Open TIML Workspace` from the sidebar session header.

That workspace is the main editing surface for TIML now. It is meant to be
raw-first:

- the source identity is the truth
- semantic labels are helpers
- Graph Editor curves are still the actual value-edit surface

The TIML Workspace lives in `Graph Editor > Sidebar > MHW Anim`.

## 3. Make edits

The workspace is split into a few practical sections:

- `Header`: edit TIML header values such as animation length and loop fields
- `Types`: add, duplicate, edit, or delete raw TIML types
- `Transforms`: add, duplicate, clone, edit, or delete raw transforms
- selected transform detail: inspect one transform, select its curves, use its
  frame span, or create an editable preview binding

Supported v1 edit shapes:

- value-only edits on existing transforms
- simple-source structural edits where the source layout is rebuild-friendly
- shared-payload edits where multiple source actions point to one embedded TIML
  payload

The workspace and diagnostics distinguish between:

- value-only edits
- rebuild-capable edits
- blocked edits

Useful TIML Workspace buttons:

- `Analyze`: refresh controller analysis and writeback classification
- `Select Controller`: jump back to the controller object
- `Curves`: select the relevant Graph Editor curves
- `Use Span`: set preview range from the selected type/transform
- `Create Preview`: create an editable custom-property preview when one does
  not exist yet

## 4. Export through the source LMT

TIML writeback happens during source-backed LMT export.

Normal path:

1. keep the matching imported LMT action in the scene
2. edit the TIML controller
3. use `Write Full LMT`

The exporter will:

- preserve unchanged TIML payloads raw
- patch supported value-only edits while preserving advanced source semantics
- rebuild supported simple-source structural edits
- block unsafe structural cases explicitly

## Shared payload note

Some embedded TIML payloads are shared by multiple source actions.

When that happens:

- the workspace/export diagnostics show the shared scope
- a successful merge export updates every linked source action that points at
  that same payload

This is expected behavior, not accidental spillover.

## What is not the v1 path

- unsafe structural rebuilds on advanced-source payloads

## Standalone TIML note

Standalone `.timl` files now have their own direct path:

1. `3D View > Sidebar > MHW Anim > TIML Inspector > Inspect TIML`
2. in the TIML Workspace `Entries` section, use `Import Selected` or `Import All`
3. edit in the TIML Workspace
4. `Export > Export TIML`

That path saves the whole standalone TIML file. This page is still specifically
about embedded TIML that lives inside an `.lmt`.
