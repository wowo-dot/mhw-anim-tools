import unittest

from blender_adapter.timl_authoring import append_timl_binding
from blender_adapter.timl_authoring import delete_timl_transform_binding
from blender_adapter.timl_authoring import delete_timl_type_bindings
from blender_adapter.timl_authoring import ensure_timl_header_props
from blender_adapter.timl_authoring import insert_timl_transform_slot
from blender_adapter.timl_authoring import insert_timl_type_slot
from blender_adapter.timl_authoring import load_deleted_timl_identities
from blender_adapter.timl_authoring import mark_deleted_timl_identity
from blender_adapter.timl_authoring import move_timl_transform_binding
from blender_adapter.timl_authoring import move_timl_type_bindings
from blender_adapter.timl_authoring import retag_binding_preview_fcurve_groups
from blender_adapter.timl_authoring import save_timl_bindings_raw
from blender_adapter.timl_authoring import save_deleted_timl_identities
from blender_adapter.timl_authoring import timl_binding_source_identity
from blender_adapter.timl_authoring import seed_binding_source_identity
from blender_adapter.timl_authoring import sync_timl_bindings_from_meta_props
from blender_adapter.timl_metadata import TIML_HEADER_LABEL_HASH_KEY


class FakeBlenderIdProperties(dict):
    def __setitem__(self, key, value):
        if len(str(key)) > 63:
            raise KeyError("the length of IDProperty names is limited to 63 characters")
        if isinstance(value, int) and not (-(1 << 31) <= value <= (1 << 31) - 1):
            raise OverflowError("Python int too large to convert to C int")
        super().__setitem__(key, value)


class FakeGroup:
    def __init__(self, name):
        self.name = name


class FakeFCurve:
    def __init__(self, data_path, group_name):
        self.data_path = data_path
        self.group = FakeGroup(group_name)


class FakeAction:
    def __init__(self, fcurves):
        self.fcurves = list(fcurves)


class TimlAuthoringTests(unittest.TestCase):
    def test_insert_timl_transform_slot_shifts_colliding_bindings_up(self):
        bindings = [
            {"property_name": "a", "type_index": 0, "transform_index": 0},
            {"property_name": "b", "type_index": 0, "transform_index": 1},
            {"property_name": "c", "type_index": 1, "transform_index": 0},
        ]

        updated = insert_timl_transform_slot(bindings, type_index=0, transform_index=1)

        self.assertEqual(
            [(item["property_name"], item["type_index"], item["transform_index"]) for item in updated],
            [("a", 0, 0), ("b", 0, 2), ("c", 1, 0)],
        )

    def test_insert_timl_type_slot_shifts_colliding_types_up(self):
        bindings = [
            {"property_name": "a", "type_index": 0, "transform_index": 0},
            {"property_name": "b", "type_index": 1, "transform_index": 0},
        ]

        updated = insert_timl_type_slot(bindings, type_index=1)

        self.assertEqual(
            [(item["property_name"], item["type_index"], item["transform_index"]) for item in updated],
            [("a", 0, 0), ("b", 2, 0)],
        )

    def test_move_timl_transform_binding_reorders_within_type(self):
        bindings = [
            {"property_name": "a", "type_index": 0, "transform_index": 0},
            {"property_name": "b", "type_index": 0, "transform_index": 1},
            {"property_name": "c", "type_index": 0, "transform_index": 2},
        ]

        updated = move_timl_transform_binding(
            bindings,
            source_type_index=0,
            source_transform_index=2,
            target_type_index=0,
            target_transform_index=0,
        )

        self.assertEqual(
            sorted((item["property_name"], item["transform_index"]) for item in updated),
            [("a", 1), ("b", 2), ("c", 0)],
        )

    def test_move_timl_transform_binding_between_types_compacts_source_and_inserts_target(self):
        bindings = [
            {"property_name": "a", "type_index": 0, "transform_index": 0},
            {"property_name": "b", "type_index": 0, "transform_index": 1},
            {"property_name": "c", "type_index": 1, "transform_index": 0},
        ]

        updated = move_timl_transform_binding(
            bindings,
            source_type_index=0,
            source_transform_index=0,
            target_type_index=1,
            target_transform_index=0,
        )

        self.assertEqual(
            sorted((item["property_name"], item["type_index"], item["transform_index"]) for item in updated),
            [("a", 1, 0), ("b", 0, 0), ("c", 1, 1)],
        )

    def test_move_timl_type_bindings_reorders_existing_type_slots(self):
        bindings = [
            {"property_name": "a", "type_index": 0, "transform_index": 0},
            {"property_name": "b", "type_index": 1, "transform_index": 0},
            {"property_name": "c", "type_index": 2, "transform_index": 0},
        ]

        updated = move_timl_type_bindings(bindings, source_type_index=2, target_type_index=0)

        self.assertEqual(
            sorted((item["property_name"], item["type_index"]) for item in updated),
            [("a", 1), ("b", 2), ("c", 0)],
        )

    def test_delete_timl_transform_binding_compacts_remaining_type(self):
        bindings = [
            {"property_name": "a", "type_index": 0, "transform_index": 0},
            {"property_name": "b", "type_index": 0, "transform_index": 1},
            {"property_name": "c", "type_index": 1, "transform_index": 0},
        ]

        updated, removed = delete_timl_transform_binding(bindings, type_index=0, transform_index=0)

        self.assertEqual(removed["property_name"], "a")
        self.assertEqual(
            sorted((item["property_name"], item["type_index"], item["transform_index"]) for item in updated),
            [("b", 0, 0), ("c", 1, 0)],
        )

    def test_delete_timl_type_bindings_compacts_higher_types(self):
        bindings = [
            {"property_name": "a", "type_index": 0, "transform_index": 0},
            {"property_name": "b", "type_index": 1, "transform_index": 0},
            {"property_name": "c", "type_index": 2, "transform_index": 0},
        ]

        updated, removed_names = delete_timl_type_bindings(bindings, type_index=1)

        self.assertEqual(removed_names, ("b",))
        self.assertEqual(
            sorted((item["property_name"], item["type_index"]) for item in updated),
            [("a", 0), ("c", 1)],
        )

    def test_seed_binding_source_identity_uses_current_identity_once(self):
        binding = {"property_name": "a", "type_index": 3, "transform_index": 4}

        seed_binding_source_identity(binding)
        self.assertEqual(timl_binding_source_identity(binding), (3, 4))
        binding["type_index"] = 9
        binding["transform_index"] = 1
        seed_binding_source_identity(binding)

        self.assertEqual(timl_binding_source_identity(binding), (3, 4))

    def test_retag_binding_preview_fcurve_groups_uses_current_raw_identity(self):
        action = FakeAction(
            [
                FakeFCurve('["prop_a"]', "TIML 00:00"),
                FakeFCurve('["prop_b"]', "TIML 00:01"),
                FakeFCurve('["unrelated"]', "Elsewhere"),
            ]
        )

        retag_binding_preview_fcurve_groups(
            action,
            [
                {"property_name": "prop_a", "type_index": 2, "transform_index": 5},
                {"property_name": "prop_b", "type_index": 1, "transform_index": 0},
            ],
        )

        self.assertEqual(action.fcurves[0].group.name, "TIML 02:05")
        self.assertEqual(action.fcurves[1].group.name, "TIML 01:00")
        self.assertEqual(action.fcurves[2].group.name, "Elsewhere")

    def test_raw_hash_metadata_uses_blender_safe_id_properties(self):
        controller = FakeBlenderIdProperties()
        property_name = "timl_eventcollision_something_absurdly_long_t00_x00_deadbeef_cafebabe"

        save_timl_bindings_raw(
            controller,
            [
                {
                    "property_name": property_name,
                    "type_index": 0,
                    "transform_index": 0,
                    "timeline_parameter_hash": 0xF1234567,
                    "datatype_hash": 0xE64D793E,
                    "data_type": 1,
                    "data_type_name": "uint32",
                    "component_labels": ["value"],
                    "normalized_color": False,
                }
            ],
        )
        ensure_timl_header_props(controller, label_hash=0x8F64576D)

        self.assertLessEqual(max(len(str(key)) for key in controller), 63)
        self.assertLess(controller[TIML_HEADER_LABEL_HASH_KEY], 0)

        synced = sync_timl_bindings_from_meta_props(controller)
        self.assertEqual(synced[0]["timeline_parameter_hash"], 0xF1234567)
        self.assertEqual(synced[0]["datatype_hash"], 0xE64D793E)
        self.assertEqual(int(controller[TIML_HEADER_LABEL_HASH_KEY]) & 0xFFFFFFFF, 0x8F64576D)

    def test_deleted_timl_identity_metadata_roundtrips_and_deduplicates(self):
        controller = FakeBlenderIdProperties()

        save_deleted_timl_identities(controller, [(0, 1), (0, 1), (2, 3)])
        self.assertEqual(load_deleted_timl_identities(controller), ((0, 1), (2, 3)))

        mark_deleted_timl_identity(controller, type_index=5, transform_index=8)
        self.assertEqual(load_deleted_timl_identities(controller), ((0, 1), (2, 3), (5, 8)))

    def test_appending_binding_clears_matching_deleted_identity(self):
        controller = FakeBlenderIdProperties()
        mark_deleted_timl_identity(controller, type_index=2, transform_index=4)

        append_timl_binding(
            controller,
            type_index=2,
            transform_index=4,
            timeline_parameter_hash=0x11223344,
            datatype_hash=0x55667788,
            data_type=2,
        )

        self.assertEqual(load_deleted_timl_identities(controller), ())


if __name__ == "__main__":
    unittest.main()
