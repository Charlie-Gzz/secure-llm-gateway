"""OpenAI-compatible request/response shapes, plus Bulwark's `gateway` verdict field."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None

    def text(self) -> str:
        """Flatten OpenAI content (string or list of parts) to plain text."""
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        return "\n".join(p.get("text", "") for p in self.content if p.get("type") == "text")


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # accept and ignore unknown OpenAI params

    model: str | None = None
    messages: list[ChatMessage]
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    stream: bool = False


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Step(BaseModel):
    """One stage of the pipeline, as drawn in the playground's request inspector."""

    name: str  # rules | classifier | pii_input | llm | pii_output
    status: Literal["pass", "redact", "block", "skip", "error"]
    latency_ms: float
    detail: dict[str, Any] = {}


class GatewayInfo(BaseModel):
    request_id: str
    verdict: Literal["allowed", "redacted", "blocked"]
    decided_by: str | None = None
    reason: str | None = None
    steps: list[Step]
    scores: dict[str, float] = {}
    redactions: list[dict[str, Any]] = []
    latency_ms: dict[str, float] = {}
    usage: Usage = Usage()
    cost_usd: float = 0.0
    upstream: str
    model: str
    trace_id: str | None = None
