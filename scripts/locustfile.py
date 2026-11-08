"""Locust user for Bulwark: sends the same benign / PII / attack mix as scripts/traffic.py.

Run it through scripts/load_test.py (steps through concurrency levels and writes results),
or interactively with the Locust web UI:

    uv run locust -f scripts/locustfile.py --host http://localhost:8000
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from locust import HttpUser, between, task

sys.path.insert(0, str(Path(__file__).resolve().parent))
from traffic import MIX  # noqa: E402

CATEGORIES = ["benign", "pii", "attack"]


class ChatUser(HttpUser):
    # Each simulated user "thinks" for 0.5-1.5 s between messages, like a person in a chat app.
    wait_time = between(0.5, 1.5)

    @task
    def chat(self) -> None:
        idx = random.choices(range(len(MIX)), weights=[w for _, w in MIX])[0]
        prompt = random.choice(MIX[idx][0])
        with self.client.post(
            "/v1/chat/completions",
            json={"model": "bulwark", "messages": [{"role": "user", "content": prompt}]},
            name=CATEGORIES[idx],
            catch_response=True,
        ) as r:
            if r.status_code != 200 or "X-Gateway-Verdict" not in r.headers:
                r.failure(f"HTTP {r.status_code}")
