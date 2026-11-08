"""Abuse limits for a public demo: per-client rate limit, input size cap, daily spend cap.

All are off by default (0) for local use and switched on by environment variables in the
prepared deploy config (deploy/). In-memory state is per instance, which is fine for a
single small Cloud Run / Fly instance; a multi-instance deploy would move this to Redis.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import HTTPException


class Limits:
    def __init__(self, rpm: int = 0, max_input_chars: int = 0, daily_spend_usd: float = 0.0):
        self.rpm = rpm
        self.max_input_chars = max_input_chars
        self.daily_spend_usd = daily_spend_usd
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> Limits:
        return cls(
            rpm=int(os.getenv("RATE_LIMIT_RPM", "0")),
            max_input_chars=int(os.getenv("MAX_INPUT_CHARS", "0")),
            daily_spend_usd=float(os.getenv("DAILY_SPEND_CAP_USD", "0")),
        )

    def check_rate(self, client: str) -> None:
        if not self.rpm:
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.rpm:
                raise HTTPException(429, f"Rate limit: {self.rpm} requests per minute.")
            hits.append(now)

    def check_size(self, text: str) -> None:
        if self.max_input_chars and len(text) > self.max_input_chars:
            raise HTTPException(413, f"Prompt too long (max {self.max_input_chars} characters).")

    def check_spend(self, spent_today_usd: float) -> None:
        if self.daily_spend_usd and spent_today_usd >= self.daily_spend_usd:
            raise HTTPException(429, "Daily spend cap reached for this demo. Try again tomorrow.")


def start_of_day_utc() -> float:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
