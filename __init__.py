# -*- coding: utf-8 -*-
"""Blender add-on entry point for MHW Anim Tools."""

import bpy

from .ui import operators_export
from .ui import operators_import
from .ui import operators_timl
from .ui import operators_tools
from .ui import lists
from .ui import panels
from .ui import properties


bl_info = {
    "name": "MHW Anim Tools",
    "description": "Modern Monster Hunter World animation tools for Blender 4.5+",
    "category": "Import-Export",
    "author": "Akif + Codex rewrite scaffold",
    "version": (0, 1, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > MHW Anim",
    "doc_url": "",
    "tracker_url": "",
}


MODULES = (
    properties,
    lists,
    operators_tools,
    operators_import,
    operators_timl,
    operators_export,
    panels,
)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()


if __name__ == "__main__":
    register()
