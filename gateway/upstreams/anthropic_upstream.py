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

    def _kwargs(self, messages: list[ChatMessage], max_tokens: int) -> dict:
        system, turns = to_anthropic(messages)
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": turns,
            "output_config": {"effort": self.effort},
        }
        if system:
            kwargs["system"] = system
        return kwargs

    @staticmethod
    def _result(msg) -> UpstreamResult:
        return UpstreamResult(
            text="".join(b.text for b in msg.content if b.type == "text"),
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            model=msg.model,
            finish_reason=FINISH.get(msg.stop_reason or "", "stop"),
        )

    async def complete(self, messages: list[ChatMessage], max_tokens: int) -> UpstreamResult:
        try:
            resp = await self.client.messages.create(**self._kwargs(messages, max_tokens))
        except anthropic.APIStatusError as e:
            raise UpstreamError(f"Anthropic API returned {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise UpstreamError("Could not reach the Anthropic API") from e
        return self._result(resp)

    async def stream(self, messages: list[ChatMessage], max_tokens: int):
        try:
            async with self.client.messages.stream(**self._kwargs(messages, max_tokens)) as s:
                async for text in s.text_stream:
                    yield text
                final = await s.get_final_message()
        except anthropic.APIStatusError as e:
            raise UpstreamError(f"Anthropic API returned {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise UpstreamError("Could not reach the Anthropic API") from e
        yield self._result(final)
