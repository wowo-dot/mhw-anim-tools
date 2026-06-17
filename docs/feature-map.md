# Feature Map

This page maps the add-on's main features to the Blender panels where they
live.

## Main sidebar

Location: `3D View > Sidebar > MHW Anim`

| Panel | Use it for | Main controls |
| --- | --- | --- |
| `Session Browser` | See current session status and jump to the TIML workspace | `Open TIML Workspace` |
| `Workspace` | Choose the target armature used for import/export | `Target Armature`, `Use Active`, `Auto Detect`, `Refresh Workspace` |
| `LMT Inspector` | Load an `.lmt`, browse entries, inspect tracks, import actions, import attached TIML | `Inspect LMT`, `Import Selected`, `Import All`, `Import TIML`, `Focus TIML` |
| `TIML Inspector` | Inspect and summarize a standalone `.timl` session | `Inspect TIML` |
| `Diagnostics` | Read current session warnings and errors | diagnostic list |
| `Export` | Analyze and write back edited actions or save standalone TIML sessions | `Export Action`, `Analyze Export Action`, `Write Full LMT`, `Export TIML` |

Notes:

- `LMT Inspector` works without a target armature
- import/export workflows are best on MHW-style armatures imported through
  `Blender MHW Model Editor`
- `Write Full LMT` is the main supported export path

## TIML Workspace

Location: `Graph Editor > Sidebar > MHW Anim`

| Section | Use it for | Main controls |
| --- | --- | --- |
| workspace header | See the focused controller or standalone TIML session summary | controller or file summary |
| `Entries` | Browse loaded LMT entries, or browse the inspected standalone TIML session when no LMT is loaded | `Import Selected`, `Import All`, `Focus` |
| workspace toolbar | Common workspace actions | `Open TIML Workspace`, `Select Controller`, `Analyze` |
| `Header` | Edit TIML header values | `Edit Header` |
| `Types` | Add, duplicate, edit, or remove raw TIML types | `Add`, `Duplicate`, `Edit Raw`, `Delete`, `Curves`, `Use Span` |
| `Transforms` | Add, duplicate, clone, edit, or remove raw transforms | `Add`, `Duplicate`, `Clone`, `Edit Raw`, `Delete` |
| selected transform detail | Inspect one transform, edit preview-bound values, and jump to its curves | `Edit Raw`, `Curves`, `Use Span`, `Create Preview` |
| `Diagnostics` | Read TIML-specific warnings and errors | diagnostic list |

Notes:

- the TIML Workspace is the main TIML editing surface
- Graph Editor curves are still the real value-edit surface
- some transforms may need `Create Preview` before there is an editable custom
  property binding

## Fallback inspector

Location: `Object Properties > TIML Inspector (Fallback)`

Use it for:

- quickly reopening the TIML Workspace
- selecting the current TIML controller object
- checking controller/source metadata when a controller object is selected

This is a fallback surface, not the main authoring UI.

## Add-on preferences

Location: `Edit > Preferences > Add-ons > MHW Anim Tools`

Use it for:

- checking GitHub for updates
- installing the newest release/tag into a normal add-on install
- clearing ignored update state
- controlling the automatic update-check interval

Notes:

- the direct installer refuses to overwrite a git worktree
- after installing an update, reload scripts or restart Blender

## Common tasks

| I want to... | Go here |
| --- | --- |
| inspect an `.lmt` | `3D View > MHW Anim > LMT Inspector` |
| inspect a standalone TIML | `3D View > MHW Anim > TIML Inspector > Inspect TIML` |
| choose the armature used for import/export | `3D View > MHW Anim > Workspace` |
| import one action | `LMT Inspector > Import Selected` |
| import all actions from one source file | `LMT Inspector > Import All` |
| import attached TIML for one entry | `LMT Inspector > Import TIML` |
| browse and edit raw TIML structure | `Graph Editor > MHW Anim > TIML Workspace` |
| save a standalone TIML file | `3D View > MHW Anim > Export > Export TIML` |
| check export readiness | `3D View > MHW Anim > Export > Analyze Export Action` |
| write the whole source file back | `3D View > MHW Anim > Export > Write Full LMT` |
