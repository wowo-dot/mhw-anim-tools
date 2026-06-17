"""Helpers for capturing and validating imported source file identity."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


SOURCE_FILE_SHA256_KEY = "mhw_anim_tools_source_file_sha256"
SOURCE_FILE_SIZE_KEY = "mhw_anim_tools_source_file_size"


@dataclass(frozen=True)
class SourceFileIdentity:
    size: int
    sha256: str


def source_file_identity_from_bytes(source_bytes: bytes) -> SourceFileIdentity:
    normalized_bytes = bytes(source_bytes or b"")
    return SourceFileIdentity(
        size=len(normalized_bytes),
        sha256=sha256(normalized_bytes).hexdigest(),
    )


def source_file_identity_from_path(path: str | Path) -> SourceFileIdentity:
    return source_file_identity_from_bytes(Path(path).read_bytes())


def store_source_file_identity(owner, identity: SourceFileIdentity) -> None:
    owner[SOURCE_FILE_SIZE_KEY] = int(identity.size)
    owner[SOURCE_FILE_SHA256_KEY] = str(identity.sha256 or "")


def load_source_file_identity(owner) -> SourceFileIdentity | None:
    getter = getattr(owner, "get", None)
    if not callable(getter):
        return None
    try:
        size = int(getter(SOURCE_FILE_SIZE_KEY, 0) or 0)
    except (TypeError, ValueError):
        return None
    sha = str(getter(SOURCE_FILE_SHA256_KEY, "") or "").strip().lower()
    if size <= 0 or not sha:
        return None
    return SourceFileIdentity(size=size, sha256=sha)
