"""Simple structured diagnostics used across milestone one."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Diagnostic:
    level: str
    code: str
    message: str


@dataclass
class Report:
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add(self, level: str, code: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(level=level, code=code, message=message))

    def add_warning(self, code: str, message: str) -> None:
        self.add("warning", code, message)

    def add_error(self, code: str, message: str) -> None:
        self.add("error", code, message)

    @property
    def error_count(self) -> int:
        return sum(1 for diagnostic in self.diagnostics if diagnostic.level == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for diagnostic in self.diagnostics if diagnostic.level == "warning")
