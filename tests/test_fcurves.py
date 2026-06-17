from __future__ import annotations

import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("bpy", MagicMock())

from blender_adapter.fcurves import assign_action
from blender_adapter.fcurves import bind_action_slot
from blender_adapter.fcurves import clear_action_assignment


class _FakeSlot:
    def __init__(self, handle: int, name: str = ""):
        self.handle = handle
        self.name = name


class _FakeAnimationData:
    def __init__(self, suitable_slots=None):
        self.action = None
        self.action_slot = None
        self.action_slot_handle = 0
        self.action_suitable_slots = list(suitable_slots or [])


class FCurveHelpersTests(unittest.TestCase):
    def test_assign_action_binds_first_slot_when_available(self):
        action = SimpleNamespace(slots=[_FakeSlot(101, "OBLegacy Slot")])
        animation_data = _FakeAnimationData()

        chosen = assign_action(animation_data, action)

        self.assertIs(animation_data.action, action)
        self.assertIs(chosen, action.slots[0])
        self.assertIs(animation_data.action_slot, action.slots[0])
        self.assertEqual(animation_data.action_slot_handle, 101)

    def test_bind_action_slot_prefers_matching_suitable_slot_handle(self):
        action_slots = [_FakeSlot(101, "Wrong"), _FakeSlot(202, "Right")]
        animation_data = _FakeAnimationData(suitable_slots=[_FakeSlot(202, "Right")])
        animation_data.action = SimpleNamespace(slots=action_slots)

        chosen = bind_action_slot(animation_data)

        self.assertIs(chosen, action_slots[1])
        self.assertIs(animation_data.action_slot, action_slots[1])
        self.assertEqual(animation_data.action_slot_handle, 202)

    def test_clear_action_assignment_resets_slot_state(self):
        slot = _FakeSlot(101, "OBLegacy Slot")
        action = SimpleNamespace(slots=[slot])
        animation_data = _FakeAnimationData()
        assign_action(animation_data, action)

        clear_action_assignment(animation_data, action)

        self.assertIsNone(animation_data.action)
        self.assertIsNone(animation_data.action_slot)
        self.assertEqual(animation_data.action_slot_handle, 0)


if __name__ == "__main__":
    unittest.main()
