"""Shared result type for all guards."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["pass", "redact", "block", "skip", "error"]


@dataclass
class GuardResult:
    status: Status
    reason: str | None = None
    score: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)
