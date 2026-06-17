# Quickstart

This is the shortest path to the main v1 workflows.

## Before you start

- Blender 4.5 or newer
- the add-on installed and enabled
- Monster Hunter World assets outside this repository
- for import/edit/export, a target model imported through `MHW_Model_Editor`
  is strongly recommended

If you only want to inspect an `.lmt`, no target armature is required.
If you want to inspect or edit a standalone `.timl`, no target armature is
required there either.

## Learn the two main UI surfaces

- `3D View > Sidebar > MHW Anim`: session, armature selection, LMT inspect,
  import, diagnostics, and export
- `Graph Editor > Sidebar > MHW Anim`: TIML Workspace

For actual motion and TIML value curves, Blender's Graph Editor is still the
real keyframe surface.

## Fastest way to inspect an LMT

1. Open `3D View > Sidebar > MHW Anim`
2. In `LMT Inspector`, click `Inspect LMT`
3. Pick the source `.lmt`
4. Browse the entries list
5. Open the selected `Entry` and `Tracks` foldouts if you want more detail

This path is safe even without a target armature.

## Fastest way to import, edit, and export an action

1. Import the target model through `MHW_Model_Editor`
2. In `Workspace`, choose the target armature or use `Use Active` /
   `Auto Detect`
3. In `LMT Inspector`, click `Inspect LMT`
4. Select an entry and use `Import Selected` or `Import All`
5. Edit the imported Blender action
6. In `Export`, click `Analyze Export Action`
7. Use `Write Full LMT`

## Fastest way to edit embedded TIML

1. Inspect an `.lmt` entry that shows `TIML attached`
2. Click `Import TIML`
3. Use `Open TIML Workspace`
4. In `Graph Editor > Sidebar > MHW Anim`, edit:
   - `Header` for TIML header fields
   - `Types` for type-level raw identity
   - `Transforms` for transform-level raw identity
   - the selected transform detail plus Graph Editor curves for actual values
5. Use `Write Full LMT`

This is still the main path for TIML that came from an `.lmt`.

## Fastest way to open, edit, and save a standalone TIML

1. Open `3D View > Sidebar > MHW Anim`
2. In `TIML Inspector`, click `Inspect TIML`
3. Pick the source `.timl`
4. Use `Open TIML Workspace`
5. In `Graph Editor > Sidebar > MHW Anim > Entries`, use `Import Selected`
   or `Import All`
6. Edit `Header`, `Types`, `Transforms`, and the Graph Editor curves
7. In `Export`, click `Export TIML`

## Good habits

- Prefer imported actions and TIML controllers that still carry source metadata
- Prefer `Write Full LMT`
- Check `Diagnostics` and export analysis before writing
- Keep final motion and TIML values baked into ordinary FCurves
- Treat duplicate raw track channels as technical Graph Editor data, not as
  ordinary pose preview controls

## Main caveat to remember

The add-on is strongest as a conservative source-backed workflow tool.

Use it like this:

1. inspect the source file
2. import the action or TIML session
3. edit supported curves/values
4. export back through `Write Full LMT` or `Export TIML`

If a case is represented as a raw technical channel or the tool blocks a TIML
rebuild shape, believe that warning before trying to force it.

## Not the v1 path

- EFX authoring/export
- arbitrary Blender rig logic presented as safe LMT export
- treating every duplicate raw source track like a normal viewport pose lane

See also:

- [Testing And Caveats](testing-and-caveats.md)
