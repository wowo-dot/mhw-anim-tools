"""Shared TIML carrier metadata keys.

Keep these strings Blender-free so import/export/readiness helpers can share
them without importing bpy-bound adapter modules.
"""

TIML_PROPERTY_LIST_KEY = "mhw_anim_tools_timl_property_names"
TIML_BINDINGS_KEY = "mhw_anim_tools_timl_bindings"
TIML_SOURCE_LMT_KEY = "mhw_anim_tools_timl_source_lmt"
TIML_ENTRY_ID_KEY = "mhw_anim_tools_timl_entry_id"
TIML_SOURCE_OFFSET_KEY = "mhw_anim_tools_timl_source_offset"
TIML_ACTION_NAME_KEY = "mhw_anim_tools_timl_action_name"
TIML_IMPORTED_PREVIEW_SIGNATURE_KEY = "mhw_anim_tools_timl_imported_preview_signature"
