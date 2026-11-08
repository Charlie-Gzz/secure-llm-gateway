"""The interface every upstream LLM implements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gateway.schemas import ChatMessage


@dataclass
class UpstreamResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: str = "stop"


class UpstreamError(Exception):
    """The upstream LLM failed; the gateway answers 502."""


class Upstream(Protocol):
    name: str
    model: str

    async def complete(self, messages: list[ChatMessage], max_tokens: int) -> UpstreamResult: ...
