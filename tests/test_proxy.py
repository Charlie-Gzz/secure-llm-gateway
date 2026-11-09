"""M1: pass-through proxy, OpenAI compatibility, cost tracking."""

import sqlite3

from openai import OpenAI

from gateway.config import Price
from gateway.cost import cost_usd
from gateway.schemas import ChatMessage
from gateway.upstreams.anthropic_upstream import to_anthropic
from tests.conftest import chat


def test_healthz(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["upstream"] == "mock"


def test_chat_completion_shape(client):
    body = chat(client, "What is the capital of France?")
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "The capital of France is Paris."
    assert body["usage"]["total_tokens"] > 0
    gw = body["gateway"]
    assert gw["upstream"] == "mock"
    assert gw["cost_usd"] > 0
    assert [s["name"] for s in gw["steps"]] == [
        "rules",
        "classifier",
        "judge",
        "pii_input",
        "llm",
        "pii_output",
    ]


def test_verdict_header(client):
    resp = client.post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hello"}]}
    )
    assert resp.headers["X-Gateway-Verdict"] in {"allowed", "redacted", "blocked"}


def test_request_logged_to_sqlite(client, db_path):
    body = chat(client, "What is a good name for a golden retriever?")
    rid = body["gateway"]["request_id"]
    row = (
        sqlite3.connect(db_path)
        .execute("SELECT verdict, cost_usd, prompt_tokens FROM requests WHERE id = ?", (rid,))
        .fetchone()
    )
    assert row is not None
    assert row[1] > 0 and row[2] > 0


def test_openai_sdk_drop_in(live_server):
    """The official OpenAI client works by changing only base_url."""
    oai = OpenAI(base_url=f"{live_server}/v1", api_key="unused")
    resp = oai.chat.completions.create(
        model="gpt-whatever",
        messages=[
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "What is the capital of France?"},
        ],
    )
    assert resp.choices[0].message.content == "The capital of France is Paris."
    assert resp.usage.total_tokens > 0


def test_cost_math():
    prices = {"m": Price(input=0.10, output=0.50)}
    assert cost_usd(prices, "m", 1_000_000, 1_000_000) == 0.60
    assert cost_usd(prices, "unknown", 100, 100) == 0.0


def test_openai_to_anthropic_translation():
    msgs = [
        ChatMessage(role="system", content="sys A"),
        ChatMessage(role="developer", content="sys B"),
        ChatMessage(role="user", content=[{"type": "text", "text": "part 1"}]),
        ChatMessage(role="user", content="part 2"),
        ChatMessage(role="assistant", content="ok"),
    ]
    system, turns = to_anthropic(msgs)
    assert system == "sys A\n\nsys B"
    assert turns == [
        {"role": "user", "content": "part 1\n\npart 2"},
        {"role": "assistant", "content": "ok"},
    ]


def test_limits():
    import pytest
    from fastapi import HTTPException

    from gateway.limits import Limits

    lim = Limits(rpm=2, max_input_chars=10, daily_spend_usd=1.0)
    lim.check_rate("a")
    lim.check_rate("a")
    with pytest.raises(HTTPException) as e:
        lim.check_rate("a")
    assert e.value.status_code == 429
    lim.check_rate("b")  # other clients unaffected
    with pytest.raises(HTTPException):
        lim.check_size("x" * 11)
    with pytest.raises(HTTPException):
        lim.check_spend(1.0)
    Limits().check_rate("a")  # all disabled by default
