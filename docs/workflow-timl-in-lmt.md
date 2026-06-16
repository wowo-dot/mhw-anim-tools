# TIML In LMT Workflow

This is the supported v1 path for editing embedded TIML data.

## 1. Inspect an LMT that has attached TIML

1. In the sidebar, click `Inspect LMT`
2. Select an entry that reports `TIML attached`
3. Use `Import TIML`

This creates a TIML controller object/action in Blender for that source entry.

## 2. Open the TIML workspace

Use `Open TIML Workspace` from the sidebar session header.

That workspace is the main editing surface for TIML now. It is meant to be
raw-first:

- the source identity is the truth
- semantic labels are helpers
- Graph Editor curves are still the actual value-edit surface

## 3. Make edits

Supported v1 edit shapes:

- value-only edits on existing transforms
- simple-source structural edits where the source layout is rebuild-friendly
- shared-payload edits where multiple source actions point to one embedded TIML
  payload

The workspace and diagnostics distinguish between:

- value-only edits
- rebuild-capable edits
- blocked edits

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

- exporting a TIML controller action as a standalone TIML file
- broad standalone TIML authoring/export outside a source-backed LMT
- unsafe structural rebuilds on advanced-source payloads
