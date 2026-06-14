"""MhBone naming helpers."""

from __future__ import annotations

import re


MHBONE_PATTERN = re.compile(r"^MhBone_(\d{3})$")
BONEFUNCTION_PATTERN = re.compile(r"^BoneFunction\.(\d{3})$")


def is_mhbone_name(name: str) -> bool:
    return bool(MHBONE_PATTERN.match(name or ""))


def is_bonefunction_name(name: str) -> bool:
    return bool(BONEFUNCTION_PATTERN.match(name or ""))


def bone_index_from_name(name: str) -> int | None:
    match = MHBONE_PATTERN.match(name or "")
    if not match:
        return None
    return int(match.group(1))


def bonefunction_index_from_name(name: str) -> int | None:
    match = BONEFUNCTION_PATTERN.match(name or "")
    if not match:
        return None
    return int(match.group(1))


def mhbone_name_from_index(index: int) -> str:
    return f"MhBone_{int(index):03d}"


def bonefunction_name_from_index(index: int) -> str:
    return f"BoneFunction.{int(index):03d}"
