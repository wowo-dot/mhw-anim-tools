"""Helpers for presenting diagnostics without noisy duplication."""

from __future__ import annotations


def has_text_diagnostic(items, *, level: str, source: str, message: str) -> bool:
    """Return True when an equivalent text diagnostic already exists."""

    expected_level = str(level or "")
    expected_source = str(source or "")
    expected_message = str(message or "")
    for item in items:
        item_level = str(getattr(item, "level", "") or "")
        item_source = str(getattr(item, "source", "") or "")
        item_message = str(getattr(item, "message", "") or "")
        if (
            item_level == expected_level
            and item_source == expected_source
            and item_message == expected_message
        ):
            return True
    return False
