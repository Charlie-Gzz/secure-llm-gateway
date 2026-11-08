"""SQLite request log: one row per request with verdict, tokens, and cost."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from gateway.schemas import GatewayInfo

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id                TEXT PRIMARY KEY,
    ts                REAL NOT NULL,
    upstream          TEXT NOT NULL,
    model             TEXT NOT NULL,
    verdict           TEXT NOT NULL,
    decided_by        TEXT,
    reason            TEXT,
    prompt_tokens     INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd          REAL NOT NULL,
    total_ms          REAL NOT NULL,
    trace_id          TEXT
);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests (ts);
"""


class RequestStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def record(self, info: GatewayInfo) -> None:
        row = (
            info.request_id,
            time.time(),
            info.upstream,
            info.model,
            info.verdict,
            info.decided_by,
            info.reason,
            info.usage.prompt_tokens,
            info.usage.completion_tokens,
            info.cost_usd,
            info.latency_ms.get("total", 0.0),
            info.trace_id,
        )
        with self._lock:
            self._conn.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", row)
            self._conn.commit()

    def summary(self, since_ts: float = 0.0) -> dict:
        with self._lock:
            cur = self._conn.execute(
                """SELECT COUNT(*), COALESCE(SUM(cost_usd), 0),
                          COALESCE(SUM(prompt_tokens + completion_tokens), 0),
                          COALESCE(SUM(verdict = 'blocked'), 0)
                   FROM requests WHERE ts >= ?""",
                (since_ts,),
            )
            count, cost, tokens, blocked = cur.fetchone()
        return {"requests": count, "cost_usd": cost, "tokens": tokens, "blocked": blocked}

    def close(self) -> None:
        self._conn.close()
