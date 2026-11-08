"""Offline upstream for dev, tests, demos, and load: deterministic answers, realistic latency.

A few canned answers deliberately contain (fake) PII so the output PII check has
something to catch in the demo.
"""

from __future__ import annotations

import asyncio
import random

from gateway.cost import estimate_tokens
from gateway.schemas import ChatMessage
from gateway.upstreams.base import UpstreamResult

CANNED = [
    (
        ("contact", "reach", "email", "phone"),
        "You can reach our support lead, Dana Whitfield, at dana.whitfield@example.com "
        "or +1 415-555-0132. She usually replies within one business day.",
    ),
    (
        ("customer record", "account details", "look up"),
        "Found it. Customer: Jordan Reyes, SSN 536-22-8714, card 4111 1111 1111 1111. "
        "Let me know what you'd like to change.",
    ),
    (
        ("capital of france",),
        "The capital of France is Paris.",
    ),
]

CHUNK_CHARS = 4

GENERIC = (
    "Here's a concise answer from the mock upstream. In a real deployment this would come "
    'from Claude. Your question was about: "{topic}". The gateway inspected your prompt, '
    "found nothing it needed to block, and forwarded it."
)


class MockUpstream:
    name = "mock"
    model = "mock-haiku"

    def __init__(self, latency_ms: int = 150):
        self.latency_ms = latency_ms

    def _answer(self, messages: list[ChatMessage]) -> str:
        last_user = next((m.text() for m in reversed(messages) if m.role == "user"), "")
        lowered = last_user.lower()
        answer = next((text for keys, text in CANNED if any(k in lowered for k in keys)), None)
        if answer is None:
            topic = " ".join(last_user.split()[:12]) or "nothing"
            answer = GENERIC.format(topic=topic)
        return answer

    def _result(self, messages: list[ChatMessage], answer: str, max_tokens: int) -> UpstreamResult:
        prompt = "\n".join(m.text() for m in messages)
        return UpstreamResult(
            text=answer,
            input_tokens=estimate_tokens(prompt),
            output_tokens=min(estimate_tokens(answer), max_tokens),
            model=self.model,
        )

    async def complete(self, messages: list[ChatMessage], max_tokens: int) -> UpstreamResult:
        answer = self._answer(messages)
        if self.latency_ms:
            jitter = random.uniform(0.7, 1.3)
            await asyncio.sleep(self.latency_ms * jitter / 1000)
        return self._result(messages, answer, max_tokens)

    async def stream(self, messages: list[ChatMessage], max_tokens: int):
        """Token-sized chunks (4 characters, so emails and phone numbers get split mid-way,
        as with a real tokenizer). Half the latency before the first chunk, half spread out."""
        answer = self._answer(messages)
        chunks = [answer[i : i + CHUNK_CHARS] for i in range(0, len(answer), CHUNK_CHARS)]
        delay = self.latency_ms * random.uniform(0.7, 1.3) / 1000 if self.latency_ms else 0
        if delay:
            await asyncio.sleep(delay / 2)
        for chunk in chunks:
            yield chunk
            if delay:
                await asyncio.sleep(delay / 2 / len(chunks))
        yield self._result(messages, answer, max_tokens)
