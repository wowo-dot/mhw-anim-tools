from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from pathlib import Path
import re


_VERSION_RE = re.compile(r"^[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version_text(text: str) -> tuple[int, int, int] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = _VERSION_RE.match(raw)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return (
        int(major or 0),
        int(minor or 0),
        int(patch or 0),
    )


def normalize_version(version: tuple[int, ...] | list[int] | None) -> tuple[int, int, int]:
    if not version:
        return (0, 0, 0)
    items = list(version[:3])
    while len(items) < 3:
        items.append(0)
    return (int(items[0]), int(items[1]), int(items[2]))


def is_version_newer(candidate: tuple[int, ...] | None, current: tuple[int, ...] | None) -> bool:
    if candidate is None:
        return False
    return normalize_version(candidate) > normalize_version(current)


def should_check_for_updates(
    last_check_text: str,
    *,
    auto_check_enabled: bool,
    months: int = 0,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
    now: datetime | None = None,
) -> bool:
    if not auto_check_enabled:
        return False
    now_value = now or datetime.now().astimezone()
    try:
        last_check = datetime.fromisoformat(str(last_check_text or ""))
    except ValueError:
        return True
    interval = timedelta(
        days=int(months or 0) * 30 + int(days or 0),
        hours=int(hours or 0),
        minutes=int(minutes or 0),
    )
    if interval <= timedelta(0):
        interval = timedelta(days=1)
    return now_value - last_check >= interval


def find_addon_root(search_root: Path) -> Path | None:
    root = Path(search_root)
    direct_init = root / "__init__.py"
    if direct_init.is_file():
        text = direct_init.read_text(encoding="utf-8", errors="ignore")
        if "bl_info" in text:
            return root

    for init_file in root.rglob("__init__.py"):
        candidate = init_file.parent
        try:
            text = init_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "bl_info" in text:
            return candidate
    return None
