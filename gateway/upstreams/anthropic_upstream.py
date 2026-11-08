"""Claude via the official Anthropic SDK, translating OpenAI chat messages to the Messages API."""

from __future__ import annotations

import anthropic

from gateway.config import UpstreamPolicy
from gateway.schemas import ChatMessage
from gateway.upstreams.base import UpstreamError, UpstreamResult

# Anthropic stop reasons -> OpenAI finish reasons
FINISH = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "refusal": "content_filter",
}


def to_anthropic(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    """Split system prompts out and merge consecutive same-role turns."""
    system_parts: list[str] = []
    turns: list[dict] = []
    for m in messages:
        text = m.text()
        if m.role in ("system", "developer"):
            system_parts.append(text)
            continue
        role = "assistant" if m.role == "assistant" else "user"  # tool output is sent as user text
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n\n" + text
        else:
            turns.append({"role": role, "content": text})
    if turns and turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": "(conversation continues)"})
    return "\n\n".join(system_parts), turns


class AnthropicUpstream:
    name = "anthropic"

    def __init__(self, api_key: str, policy: UpstreamPolicy):
        self.model = policy.model
        self.effort = policy.effort
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=policy.timeout_s)

    async def complete(self, messages: list[ChatMessage], max_tokens: int) -> UpstreamResult:
        system, turns = to_anthropic(messages)
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": turns,
            "output_config": {"effort": self.effort},
        }
        if system:
            kwargs["system"] = system
        try:
            resp = await self.client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            raise UpstreamError(f"Anthropic API returned {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise UpstreamError("Could not reach the Anthropic API") from e

        text = "".join(b.text for b in resp.content if b.type == "text")
        return UpstreamResult(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=resp.model,
            finish_reason=FINISH.get(resp.stop_reason or "", "stop"),
        )
