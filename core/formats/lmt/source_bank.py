"""Explicit, worker-local reuse of immutable source banks.

Every load reads and compares the complete file contents. A cache hit never
depends on timestamps, inode numbers or file size alone. No Blender state or
mutable analysis result is cached. Callers should own one cache per worker.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from threading import RLock

from .model import LmtFile
from .reader import read_lmt_bytes


@dataclass(frozen=True)
class LmtSourceBank:
    data: bytes
    lmt: LmtFile
    sha256: str
    charged_bytes: int


def _memory_charge(data: bytes, lmt: LmtFile) -> int:
    # Conservative CPython 3.10/3.11 allowance for dataclasses, their dictionaries,
    # scalar/tuple objects and LRU bookkeeping, in addition to owned byte buffers.
    # This deliberately overcounts shared/interned scalar objects.
    return (len(data) + 4096 + len(lmt.entry_offsets) * 64 + len(lmt.actions) * 4096
            + sum(2048 + len(track.raw_buffer) for action in lmt.actions for track in action.tracks))


class LmtSourceBankCache:
    """Content-verified LRU; at most two banks / 512 MiB charged by default.

    Oversized banks are returned but not retained. Budgets cover retained cache
    entries, not transient reads or snapshots held by the caller. Explicit clear
    releases cache ownership; snapshots already in use stay valid. Crossing a
    process boundary clears inherited entries and counters before use.
    """

    def __init__(self, *, max_banks: int = 2, max_bytes: int = 512 * 1024 * 1024):
        if max_banks < 0 or max_bytes < 0:
            raise ValueError("Cache limits must be non-negative")
        self.max_banks = int(max_banks)
        self.max_bytes = int(max_bytes)
        self._pid = os.getpid()
        self._lock = RLock()
        self._banks = OrderedDict()
        self._charged_bytes = 0
        self._hits = self._misses = self._evictions = 0

    def _check_process(self):
        if self._pid != os.getpid():
            # Reset the lock too: a parent thread may have held it at fork time.
            self._lock = RLock()
            self._banks = OrderedDict()
            self._charged_bytes = 0
            self._hits = self._misses = self._evictions = 0
            self._pid = os.getpid()

    def load(self, path: str | Path) -> LmtSourceBank:
        self._check_process()
        path = Path(path).resolve()
        key = os.path.normcase(str(path))
        with self._lock:
            previous = self._banks.get(key)
            try:
                data = path.read_bytes()
            except OSError:
                self._discard(key)
                raise
            if previous is not None and data == previous.data:
                self._hits += 1
                self._banks.move_to_end(key)
                return previous
            self._discard(key)
            self._misses += 1
            lmt = read_lmt_bytes(data, source_name=str(path))
            bank = LmtSourceBank(data, lmt, sha256(data).hexdigest(), _memory_charge(data, lmt))
            if self.max_banks and bank.charged_bytes <= self.max_bytes:
                while self._banks and (len(self._banks) >= self.max_banks or self._charged_bytes + bank.charged_bytes > self.max_bytes):
                    self._discard(next(iter(self._banks)))
                    self._evictions += 1
                self._banks[key] = bank
                self._charged_bytes += bank.charged_bytes
            return bank

    def _discard(self, key):
        bank = self._banks.pop(key, None)
        if bank is not None:
            self._charged_bytes -= bank.charged_bytes

    def clear(self):
        self._check_process()
        with self._lock:
            self._banks.clear()
            self._charged_bytes = 0

    def stats(self) -> dict[str, int]:
        self._check_process()
        with self._lock:
            return dict(hits=self._hits, misses=self._misses, evictions=self._evictions,
                        banks=len(self._banks), charged_bytes=self._charged_bytes,
                        max_banks=self.max_banks, max_bytes=self.max_bytes)
