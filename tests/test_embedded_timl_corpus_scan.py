from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.scan_embedded_timl_corpus import _nearby_mod3_candidates_for_lmt
from tools.scan_embedded_timl_corpus import _normalize_gen_model_reference
from tools.scan_embedded_timl_corpus import _record_ranked_example
from tools.scan_embedded_timl_corpus import _resolve_gen_model_reference_to_mod3
from tools.scan_embedded_timl_corpus import _shared_payload_example_rank


class EmbeddedTimlCorpusScanTests(unittest.TestCase):
    def test_normalize_gen_model_reference_trims_prefix_noise(self):
        reference = "XAssets\\evm\\evm055\\evm055_00\\mod\\evm055_00"
        self.assertEqual(
            _normalize_gen_model_reference(reference),
            "Assets\\evm\\evm055\\evm055_00\\mod\\evm055_00",
        )

    def test_resolve_gen_model_reference_to_mod3_uses_chunk_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_root = Path(tmpdir) / "chunk"
            model_path = chunk_root / "Assets" / "evm" / "evm055" / "evm055_00" / "mod" / "evm055_00.mod3"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_bytes(b"")

            resolved = _resolve_gen_model_reference_to_mod3(
                "XAssets\\evm\\evm055\\evm055_00\\mod\\evm055_00",
                chunk_root=chunk_root,
            )

            self.assertEqual(resolved, str(model_path))

    def test_nearby_mod3_candidates_find_nested_mod_root_models(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_root = Path(tmpdir) / "npc" / "npc018"
            lmt_path = asset_root / "mot" / "npc018_09_st" / "npc018_09_st.lmt"
            model_path = asset_root / "mod" / "body" / "npc018.mod3"
            lmt_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            lmt_path.write_bytes(b"")
            model_path.write_bytes(b"")

            candidates = _nearby_mod3_candidates_for_lmt(lmt_path, limit=3)

            self.assertIn(str(model_path), candidates)

    def test_nearby_mod3_candidates_can_fall_back_to_asset_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_root = Path(tmpdir) / "effects" / "fx001"
            lmt_path = asset_root / "mot" / "fx001_idle" / "fx001_idle.lmt"
            model_path = asset_root / "preview" / "fx001.mod3"
            lmt_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            lmt_path.write_bytes(b"")
            model_path.write_bytes(b"")

            candidates = _nearby_mod3_candidates_for_lmt(lmt_path, limit=3)

            self.assertIn(str(model_path), candidates)

    def test_nearby_mod3_candidates_include_existing_gen_model_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_root = Path(tmpdir) / "chunk"
            asset_root = chunk_root / "npc" / "npc706"
            lmt_path = asset_root / "mot" / "npc706_09" / "npc706_09.lmt"
            gen_path = asset_root / "mod" / "npc706_100.gen"
            model_path = chunk_root / "Assets" / "evm" / "evm055" / "evm055_00" / "mod" / "evm055_00.mod3"
            lmt_path.parent.mkdir(parents=True, exist_ok=True)
            gen_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            lmt_path.write_bytes(b"")
            model_path.write_bytes(b"")
            gen_path.write_bytes(
                b"\x00\x01XAssets\\evm\\evm055\\evm055_00\\mod\\evm055_00\x00"
            )

            candidates = _nearby_mod3_candidates_for_lmt(lmt_path, limit=3)

            self.assertIn(str(model_path), candidates)

    def test_nearby_mod3_candidates_can_use_body_profile_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_root = Path(tmpdir) / "chunk"
            unresolved_root = chunk_root / "npc" / "npc016"
            reference_root = chunk_root / "npc" / "npc117"
            unresolved_lmt = unresolved_root / "mot" / "npc016_09" / "npc016_09.lmt"
            unresolved_gen = unresolved_root / "mod" / "npc016_00.gen"
            reference_gen = reference_root / "mod" / "npc117_00.gen"
            model_path = chunk_root / "Assets" / "evm" / "evm527" / "evm527_00" / "mod" / "evm527_00.mod3"

            unresolved_lmt.parent.mkdir(parents=True, exist_ok=True)
            unresolved_gen.parent.mkdir(parents=True, exist_ok=True)
            reference_gen.parent.mkdir(parents=True, exist_ok=True)
            model_path.parent.mkdir(parents=True, exist_ok=True)

            unresolved_lmt.write_bytes(b"")
            unresolved_gen.write_bytes(b"\x00npc\\common\\body_info\\airu\x00")
            reference_gen.write_bytes(
                b"\x00npc\\common\\body_info\\airu\x00XAssets\\evm\\evm527\\evm527_00\\mod\\evm527_00\x00"
            )
            model_path.write_bytes(b"")

            candidates = _nearby_mod3_candidates_for_lmt(unresolved_lmt, limit=5)

            self.assertIn(str(model_path), candidates)

    def test_nearby_mod3_candidates_can_use_known_common_motion_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_root = Path(tmpdir) / "chunk"
            lmt_path = chunk_root / "npc" / "common" / "mot" / "ncom151_09" / "ncom151_09.lmt"
            model_path = chunk_root / "Assets" / "evm" / "evm055" / "evm055_00" / "mod" / "evm055_00.mod3"

            lmt_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.parent.mkdir(parents=True, exist_ok=True)

            lmt_path.write_bytes(b"")
            model_path.write_bytes(b"")

            candidates = _nearby_mod3_candidates_for_lmt(lmt_path, limit=5)

            self.assertIn(str(model_path), candidates)

    def test_ranked_example_retention_prefers_runnable_shared_examples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            live_mod3 = Path(tmpdir) / "live.mod3"
            live_mod3.write_bytes(b"")
            items: list[dict[str, object]] = []

            unrunnable_large = {
                "path": "a.lmt",
                "payload_offset": 1,
                "mod3_path": "",
                "mod3_candidates": [],
                "shared_action_count": 8,
                "supported_transform_count": 10,
                "transform_count": 10,
            }
            runnable_small = {
                "path": "b.lmt",
                "payload_offset": 2,
                "mod3_path": str(live_mod3),
                "mod3_candidates": [str(live_mod3)],
                "shared_action_count": 2,
                "supported_transform_count": 3,
                "transform_count": 3,
            }

            _record_ranked_example(
                items,
                unrunnable_large,
                rank_key=_shared_payload_example_rank,
                unique_key=lambda item: (str(item.get("path", "")), int(item.get("payload_offset", 0) or 0)),
                limit=1,
            )
            _record_ranked_example(
                items,
                runnable_small,
                rank_key=_shared_payload_example_rank,
                unique_key=lambda item: (str(item.get("path", "")), int(item.get("payload_offset", 0) or 0)),
                limit=1,
            )

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["path"], "b.lmt")


if __name__ == "__main__":
    unittest.main()
