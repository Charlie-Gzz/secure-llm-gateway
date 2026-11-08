"""Tracing hooks. A no-op placeholder until OpenTelemetry is wired in (M3)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any


@contextmanager
def span(name: str, **attributes: Any):
    yield None


def current_trace_id() -> str | None:
    return None
