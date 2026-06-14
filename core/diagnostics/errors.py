"""Error types shared by the new core."""

from __future__ import annotations


class MhwAnimToolsError(Exception):
    """Base error for the rewrite."""


class BinaryFormatError(MhwAnimToolsError):
    """Raised when binary input is malformed or truncated."""

    def __init__(self, message: str, **context) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        pairs = ", ".join(f"{key}={value}" for key, value in sorted(self.context.items()))
        return f"{self.message} ({pairs})"


class ValidationError(MhwAnimToolsError):
    """Raised when required format invariants are broken."""
