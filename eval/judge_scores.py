"""Judge (Qwen3Guard) probabilities for every eval prompt, cached in eval/data/judge_cache.jsonl.

The judge takes ~1 s per prompt on a laptop CPU, so `make eval` reuses this cache and only
scores prompts it hasn't seen. Run it directly to fill the cache:

    uv run python eval/judge_scores.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE = ROOT / "eval" / "data" / "judge_cache.jsonl"
MODEL_DIR = ROOT / "models" / "judge"


def key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def load_cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    rows = (json.loads(line) for line in CACHE.read_text(encoding="utf-8").splitlines() if line)
    return {r["key"]: r for r in rows}


def judge_scores(texts: list[str]) -> dict[str, dict] | None:
    """{key(text): {"p_flagged", "p_jailbreak", "ms"}}, or None if the judge isn't exported."""
    if not (MODEL_DIR / "model.onnx").exists():
        return None
    from gateway.guards.judge import JudgeGuard

    cache = load_cache()
    todo = [t for t in dict.fromkeys(texts) if key(t) not in cache]
    if todo:
        judge = JudgeGuard(MODEL_DIR)
        judge.score("warm up")
        started = time.perf_counter()
        with CACHE.open("a", encoding="utf-8") as f:
            for i, text in enumerate(todo, 1):
                t0 = time.perf_counter()
                flagged, jailbreak = judge.probabilities(text)
                row = {
                    "key": key(text),
                    "p_flagged": flagged,
                    "p_jailbreak": jailbreak,
                    "ms": (time.perf_counter() - t0) * 1000,
                }
                f.write(json.dumps(row) + "\n")
                f.flush()
                cache[row["key"]] = row
                if i % 100 == 0:
                    rate = i / (time.perf_counter() - started)
                    print(f"  judge {i}/{len(todo)} ({rate:.1f}/s)", flush=True)
    return {key(t): cache[key(t)] for t in texts}


if __name__ == "__main__":
    from eval.datasets import load_all

    examples = load_all()
    scores = judge_scores([e["text"] for e in examples])
    print("judge model missing; run `make judge-model`" if scores is None else f"{len(scores)} ok")
