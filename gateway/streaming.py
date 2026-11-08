"""Streaming helpers: OpenAI `chat.completion.chunk` objects, SSE framing, and the sentence
buffer that makes output PII redaction safe on a stream.

Why a sentence buffer: the model streams a few characters at a time, so an email address or
card number usually arrives split across chunks. Redacting each chunk on its own would leak
the pieces. Instead the gateway holds text back until a sentence boundary (". ", "! ", "? ",
or a newline), redacts the whole sentence, and only then releases it. None of the redacted
entity types (emails, phones, SSNs, cards, IBANs, passports, IPs) contain a boundary, so a
boundary can't split one. The trade-off: text arrives a sentence at a time, not per token.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

# A sentence ends at . ! ? followed by whitespace, or at a newline.
BOUNDARY = re.compile(r"[.!?]\s+|\n")
# Safety valve for text with no boundaries (e.g. a long code line): release at the last space
# once the buffer is this long. Rare, and documented as a limitation.
MAX_HOLD_CHARS = 2000


class SentenceBuffer:
    """Accumulate streamed text; release only complete sentences."""

    def __init__(self, max_hold: int = MAX_HOLD_CHARS):
        self.buf = ""
        self.max_hold = max_hold

    def feed(self, text: str) -> str:
        """Add text; return everything up to the last complete sentence ("" if none yet)."""
        self.buf += text
        last_end = 0
        for m in BOUNDARY.finditer(self.buf):
            last_end = m.end()
        if not last_end and len(self.buf) > self.max_hold:
            last_end = self.buf.rfind(" ") + 1  # 0 if there is no space at all: keep holding
        out, self.buf = self.buf[:last_end], self.buf[last_end:]
        return out

    def flush(self) -> str:
        out, self.buf = self.buf, ""
        return out


def chunk(
    completion_id: str,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """One OpenAI `chat.completion.chunk`."""
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        **extra,
    }


def usage_chunk(completion_id: str, model: str, usage: dict[str, int]) -> dict[str, Any]:
    """The extra final chunk OpenAI sends when `stream_options.include_usage` is true."""
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [],
        "usage": usage,
    }


def sse(event: dict[str, Any] | str) -> str:
    """Frame one server-sent event. `[DONE]` is sent as a bare string, like OpenAI does."""
    data = event if isinstance(event, str) else json.dumps(event, separators=(",", ":"))
    return f"data: {data}\n\n"
