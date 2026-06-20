# Installation

This add-on targets Blender 4.5 LTS.

## What you need

- Blender 4.5 LTS
- this repository as a zip package or local add-on folder
- Monster Hunter World assets outside the repository

Required for the main armature import/edit/export workflow:

- `Blender MHW Model Editor` enabled in the same Blender install

The add-on can still inspect LMT files without `Blender MHW Model Editor`, but
the main supported LMT import/edit/export path depends on MHW-style armatures
imported through that toolchain.

For `v1.0.1`, Blender 4.5 LTS is the supported and tested release target.
Later Blender versions may work, but they are not the current compatibility
promise.

## Install from zip

1. In Blender, open `Edit > Preferences > Add-ons`
2. Click `Install from Disk...`
3. Choose the `mhw_anim_tools` zip
4. Enable the `MHW Anim Tools` add-on
5. Open the 3D View sidebar and confirm the `MHW Anim Tools` panel appears

## Install from a local folder

1. Copy the `mhw_anim_tools` folder into Blender's add-ons directory
2. Start Blender
3. Open `Edit > Preferences > Add-ons`
4. Enable `MHW Anim Tools`

Typical Windows add-on location:

- `%APPDATA%\\Blender Foundation\\Blender\\4.5\\scripts\\addons`

## First-run check

After enabling the add-on:

1. Open the `MHW Anim Tools` sidebar panel
2. Confirm `Inspect LMT` is visible
3. If you also use `Blender MHW Model Editor`, import a known `.mod3` target and make
   sure the target armature picker sees it

## Read next

After install, these are the best next docs:

- [Quickstart](quickstart.md)
- [Feature Map](feature-map.md)
- [Basic LMT Workflow](workflow-lmt.md)
- [TIML In LMT Workflow](workflow-timl-in-lmt.md)

## Known setup expectations

- `Inspect LMT` works without a target armature
- importing actions into Blender requires a target armature
- exporting edited LMT actions is most trustworthy when the action came from a
  source LMT import and still has source metadata
- standalone TIML inspect/import/export is supported for existing source
  entries
- creating brand-new standalone TIML entries from empty source slots is not a
  v1 workflow
- updater controls live in `Edit > Preferences > Add-ons > MHW Anim Tools`
