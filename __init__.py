# -*- coding: utf-8 -*-
"""Blender add-on entry point for MHW Anim Tools."""

import bpy

from .ui import addon_preferences
from .ui import operators_export
from .ui import operators_import
from .ui import operators_timl
from .ui import operators_tools
from .ui import lists
from .ui import panels
from .ui import properties


bl_info = {
    "name": "MHW Anim Tools",
    "description": "Monster Hunter World animation tools for Blender 4.5 LTS",
    "category": "Import-Export",
    "author": "wowo",
    "version": (1, 0, 1),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > MHW Anim",
    "doc_url": "https://github.com/wowo-dot/mhw-anim-tools",
    "tracker_url": "https://github.com/wowo-dot/mhw-anim-tools/issues",
}


MODULES = (
    addon_preferences,
    properties,
    lists,
    operators_tools,
    operators_import,
    operators_timl,
    operators_export,
    panels,
)


def register():
    addon_preferences.configure(bl_info)
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()


if __name__ == "__main__":
    register()
