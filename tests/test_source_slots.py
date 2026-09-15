from dataclasses import replace
from hashlib import sha256
import unittest

from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.source_bank import LmtSourceBank
from core.formats.lmt.source_slots import export_source_slots, audit_source_slots
from core.formats.lmt.merge_writer import write_multi_merged_lmt_bytes
from core.formats.lmt.content_signature import track_content_signature
from test_lmt_merge_writer import _build_source_container_with_shared_timl
from pose_test_support import static


class SourceSlotTests(unittest.TestCase):
    def test_edit_one_duplicate_preserves_other_slot_siblings_and_rebased_timl(self):
        raw, _ = _build_source_container_with_shared_timl()
        lmt = read_lmt_bytes(raw)
        first = lmt.actions[0]
        seed = static(9,1)
        duplicate = replace(seed, header=replace(seed.header, basis=(9.,8.,7.,0.)))
        first = replace(first, header=replace(first.header, fcurve_count=2), tracks=(seed,duplicate))
        lmt = replace(lmt, actions=(first, *lmt.actions[1:]))
        raw = write_multi_merged_lmt_bytes(lmt, raw, {})
        lmt = read_lmt_bytes(raw)
        bank = LmtSourceBank(raw, lmt, sha256(raw).hexdigest(), len(raw))
        self.assertIs(export_source_slots(bank), raw)
        first = lmt.actions[0]
        original = first.tracks[0]
        edit = replace(original, header=replace(original.header, basis=(123.,2.,3.,0.)))
        result = export_source_slots(bank, {first.id:{0:edit}})
        readback = read_lmt_bytes(result)
        self.assertEqual(track_content_signature(readback.actions[0].tracks[-1]), track_content_signature(first.tracks[-1]))
        expected_first = replace(first, tracks=(edit, *first.tracks[1:]))
        expected = replace(lmt, actions=(expected_first,*lmt.actions[1:]))
        audit_source_slots(expected, raw, readback, result)
        self.assertEqual(result, export_source_slots(bank,{first.id:{0:edit}}))
        with self.assertRaises(ValueError):
            export_source_slots(bank,{first.id:{0:replace(edit,header=replace(edit.header,usage=5))}})
        with self.assertRaises(ValueError):
            export_source_slots(bank,{first.id:{999:edit}})
        with self.assertRaises(ValueError):
            export_source_slots(bank,{999:{0:edit}})
