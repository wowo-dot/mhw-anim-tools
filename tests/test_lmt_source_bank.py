from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.formats.lmt.source_bank import LmtSourceBankCache
from core.formats.lmt.reader import read_lmt_bytes
from core.diagnostics.errors import BinaryFormatError
from test_lmt_merge_writer import _build_source_container_with_shared_timl


class SourceBankCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.lmt"
        self.raw = _build_source_container_with_shared_timl()[0]
        self.path.write_bytes(self.raw)

    def test_hit_reuses_immutable_parse_and_hash(self):
        cache = LmtSourceBankCache()
        first = cache.load(self.path)
        with patch("core.formats.lmt.source_bank.read_lmt_bytes", side_effect=AssertionError("reparsed")), patch("core.formats.lmt.source_bank.sha256", side_effect=AssertionError("rehashed")):
            self.assertIs(cache.load(self.path), first)
        with self.assertRaises(FrozenInstanceError):
            first.lmt.actions[0].header.frame_count = 999
        self.assertEqual(cache.stats()["hits"], 1)

    def test_same_size_same_mtime_edit_and_atomic_replacement_invalidate(self):
        cache = LmtSourceBankCache()
        first = cache.load(self.path)
        stamp = self.path.stat()
        changed = bytearray(self.raw)
        changed[8] ^= 1
        self.path.write_bytes(changed)
        os.utime(self.path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        second = cache.load(self.path)
        self.assertNotEqual(second.sha256, first.sha256)
        self.assertEqual(second.lmt, read_lmt_bytes(bytes(changed), str(self.path)))
        replacement = self.path.with_suffix(".new")
        replacement.write_bytes(self.raw)
        os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        os.replace(replacement, self.path)
        self.assertEqual(cache.load(self.path).sha256, first.sha256)
        self.assertEqual(cache.stats()["misses"], 3)

    def test_missing_or_invalid_source_cannot_return_stale_bank(self):
        cache = LmtSourceBankCache()
        cache.load(self.path)
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            cache.load(self.path)
        self.assertEqual(cache.stats()["banks"], 0)
        self.path.write_bytes(self.raw)
        cache.load(self.path)
        self.path.write_bytes(b"bad")
        with self.assertRaises(BinaryFormatError):
            cache.load(self.path)
        self.assertEqual(cache.stats()["banks"], 0)

    def test_lru_eviction_budget_clear_and_oversized_bypass(self):
        cache = LmtSourceBankCache(max_banks=1)
        first = cache.load(self.path)
        other = self.path.with_name("other.lmt")
        other.write_bytes(self.raw)
        cache.load(other)
        self.assertEqual(cache.stats()["evictions"], 1)
        self.assertIsNot(cache.load(self.path), first)
        cache.clear()
        self.assertEqual(cache.stats()["charged_bytes"], 0)
        limited = LmtSourceBankCache(max_bytes=first.charged_bytes - 1)
        self.assertEqual(limited.load(self.path).data, self.raw)
        self.assertEqual(limited.stats()["banks"], 0)
        disabled = LmtSourceBankCache(max_banks=0)
        disabled.load(self.path)
        self.assertEqual(disabled.stats()["banks"], 0)

    def test_new_worker_does_not_reuse_parent_cache(self):
        cache = LmtSourceBankCache()
        first = cache.load(self.path)
        with patch("core.formats.lmt.source_bank.os.getpid", return_value=os.getpid() + 1):
            self.assertIsNot(cache.load(self.path), first)
            self.assertEqual(cache.stats()["hits"], 0)
            self.assertEqual(cache.stats()["misses"], 1)

    def test_cache_owns_no_more_than_byte_budget_with_multiple_banks(self):
        charge = LmtSourceBankCache().load(self.path).charged_bytes
        cache = LmtSourceBankCache(max_banks=100, max_bytes=charge)
        cache.load(self.path)
        other = self.path.with_name("different.lmt")
        other.write_bytes(self.raw)
        cache.load(other)
        self.assertEqual(cache.stats()["banks"], 1)
        self.assertEqual(cache.stats()["evictions"], 1)
        self.assertLessEqual(cache.stats()["charged_bytes"], cache.max_bytes)
