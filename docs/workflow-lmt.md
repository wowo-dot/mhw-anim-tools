# Basic LMT Workflow

This is the supported v1 path for editing an LMT action and writing it back.

Main UI location:

- `3D View > Sidebar > MHW Anim`

## 1. Prepare the scene

1. Import the target model/armature into Blender
2. In the `MHW Anim Tools` sidebar, choose the target armature
3. Use `Use Active` or `Auto Detect` if needed

Best results come from MHW-style armatures imported through
`MHW_Model_Editor`.

## 2. Inspect the source LMT

1. In `LMT Inspector`, click `Inspect LMT`
2. Pick the source `.lmt`
3. Browse the entry list and select the action you want

The inspector shows:

- frame count
- loop frame
- track counts
- root translation/rotation summary
- whether the entry has attached TIML

Open the selected `Entry` and `Tracks` foldouts when you want the per-entry or
per-track details.

## 3. Import the action

Choose one of these:

- `Import Selected` to bring one source action into Blender
- `Import All` to import the whole source LMT as Blender actions

Imported actions keep source metadata such as:

- source LMT path
- source entry id
- source TIML offset when present

That metadata is what makes source-backed export and full-source export work.

## 4. Edit in Blender

Edit the imported Blender action on the target armature.

Supported motion channels for export:

- pose-bone `rotation_quaternion`
- pose-bone `location`
- pose-bone `scale`
- armature object root motion

Keep the final result baked into normal FCurves if you use constraints,
retargeting, or procedural rigs.

When an action contains duplicate raw source tracks with the same
`bone_id + usage` identity, the add-on keeps them editable as raw custom
properties:

- on the resolved pose bone when Blender has a real bone target
- on the armature object when the slot has to stay armature-level

Those slots are still technical/raw channels. They round-trip through export,
but they do not pretend to be one ordinary transform lane.

## 5. Analyze before writing

In the `Export` section:

1. choose the imported action if it is not already active
2. click `Analyze Export Action`

This gives you:

- sampled track counts
- planned export buffer families
- warnings/errors for unsupported or risky shapes

## 6. Write the file

Use `Write Full LMT`.

That writes the full source container using every imported Blender action from
that same source file.

## What is safe today

- source-backed export of supported edited LMT actions
- preserving untouched sibling actions in the same source LMT
- preserving source container metadata in merge mode

## What still needs care

- unsupported FCurve paths are skipped
- duplicate raw track-identity source actions import as technical raw
  pose-bone/armature channels, not normal pose preview channels
- export confidence is strongest on the supported rotation/translation/scale
  path, not on arbitrary Blender rig logic
- a small remaining quaternion edge-case family is still called out in
  [Known Warnings](known-warnings.md)
