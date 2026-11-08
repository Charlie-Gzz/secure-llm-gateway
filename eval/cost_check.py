"""Check the eval's cost-per-1K estimate against a small real Claude run (max 100 requests).

Sends benign prompts through the real pipeline with the Anthropic upstream and compares
the billed token usage to the estimate in eval/results/results.json.

    ANTHROPIC_API_KEY=... uv run python eval/cost_check.py --n 50     (or: make eval-cost)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.datasets import load_public  # noqa: E402
from gateway.config import Policy, get_settings  # noqa: E402
from gateway.pipeline import Pipeline  # noqa: E402
from gateway.schemas import ChatMessage, ChatRequest  # noqa: E402
from gateway.upstreams.anthropic_upstream import AnthropicUpstream  # noqa: E402

MAX_REQUESTS = 100  # hard cap from the project plan
SYSTEM = "You are a helpful assistant. Answer concisely."


async def main(n: int) -> None:
    key = get_settings().anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set (put it in .env). Nothing was sent.")
    n = min(n, MAX_REQUESTS)
    policy = Policy.load(ROOT / "policy.yaml")
    pipeline = Pipeline(policy, AnthropicUpstream(key, policy.upstream))  # no guards: cost only

    prompts = [e["text"] for e in load_public("no_robots")]
    random.Random(1).shuffle(prompts)
    total_cost, tokens_in, tokens_out = 0.0, 0, 0
    for i, text in enumerate(prompts[:n], 1):
        req = ChatRequest(
            messages=[
                ChatMessage(role="system", content=SYSTEM),
                ChatMessage(role="user", content=text),
            ]
        )
        _, info = await pipeline.run(req)
        total_cost += info.cost_usd
        tokens_in += info.usage.prompt_tokens
        tokens_out += info.usage.completion_tokens
        print(f"  {i}/{n}  in={info.usage.prompt_tokens} out={info.usage.completion_tokens}")

    measured = total_cost / n * 1000
    estimate = json.loads((ROOT / "eval/results/results.json").read_text())["cost"]
    print(
        f"\nMeasured: ${measured:.4f} per 1K requests "
        f"(avg {tokens_in / n:.0f} in / {tokens_out / n:.0f} out tokens)"
    )
    print(f"Estimated in results.json: ${estimate['llm_usd_per_1k']:.4f} per 1K")
    out = ROOT / "eval/results/cost_check.json"
    out.write_text(
        json.dumps(
            {
                "requests": n,
                "measured_usd_per_1k": measured,
                "avg_input_tokens": tokens_in / n,
                "avg_output_tokens": tokens_out / n,
                "estimated_usd_per_1k": estimate["llm_usd_per_1k"],
            },
            indent=2,
        )
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help=f"requests to send (max {MAX_REQUESTS})")
    asyncio.run(main(ap.parse_args().n))
