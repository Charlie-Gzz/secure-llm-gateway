"""Load the evaluation sets: public attack/benign datasets from Hugging Face plus our holdout.

Every example is {"text", "label" (1 = attack, 0 = benign), "source"}. Downloads are cached
in eval/data/ (gitignored). Sampling is seeded so `make eval` is reproducible.

None of the public sets below appear in the classifier's training list (see its model card).
"""

from __future__ import annotations

import ast
import json
import os
import random
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import pyarrow.parquet as pq  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
CACHE = EVAL_DIR / "data"
SEED = 7

# name -> (repo, [parquet files], license, what it contributes)
SOURCES = {
    "deepset": (
        "deepset/prompt-injections",
        [
            "data/train-00000-of-00001-9564e8b05b4757ab.parquet",
            "data/test-00000-of-00001-701d16158af87368.parquet",
        ],
        "Apache-2.0",
        "mixed injections + benign (some German)",
    ),
    "gandalf": (
        "Lakera/gandalf_ignore_instructions",
        [
            "data/train-00000-of-00001-ded53be747ff55cd.parquet",
            "data/validation-00000-of-00001-94481a2a09ff2fff.parquet",
            "data/test-00000-of-00001-bc92128b9288a6d1.parquet",
        ],
        "MIT",
        "real human injection attempts from the Gandalf game",
    ),
    "jailbreak_wild": (
        "TrustAIRLab/in-the-wild-jailbreak-prompts",
        ["jailbreak_2023_12_25/train-00000-of-00001.parquet"],
        "MIT",
        "jailbreak prompts collected from Reddit/Discord (sampled 300)",
    ),
    "no_robots": (
        "HuggingFaceH4/no_robots",
        ["data/test-00000-of-00001.parquet", "data/train-00000-of-00001.parquet"],
        "CC-BY-NC-4.0",
        "human-written benign user requests (sampled 1,000)",
    ),
}


def _rows(name: str) -> list[dict]:
    repo, files, _, _ = SOURCES[name]
    rows: list[dict] = []
    for f in files:
        path = hf_hub_download(repo, f, repo_type="dataset")
        rows += pq.read_table(path).to_pylist()
    return rows


def _first_user_message(messages) -> str:
    if isinstance(messages, str):
        messages = ast.literal_eval(messages)
    return next((m["content"] for m in messages if m["role"] == "user"), "")


def _build(name: str) -> list[dict]:
    rng = random.Random(SEED)
    rows = _rows(name)
    if name == "deepset":
        return [{"text": r["text"], "label": int(r["label"])} for r in rows]
    if name == "gandalf":
        return [{"text": r["text"], "label": 1} for r in rows]
    if name == "jailbreak_wild":
        rows = [r for r in rows if r["prompt"] and len(r["prompt"]) < 8000]
        return [{"text": r["prompt"], "label": 1} for r in rng.sample(rows, 300)]
    if name == "no_robots":
        texts = list(dict.fromkeys(_first_user_message(r["messages"]) for r in rows))
        texts = [t for t in texts if t.strip()]
        return [{"text": t, "label": 0} for t in rng.sample(texts, 1000)]
    raise KeyError(name)


def load_public(name: str) -> list[dict]:
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / f"{name}.jsonl"
    if not cached.exists():
        examples = _build(name)
        cached.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in examples), encoding="utf-8"
        )
    examples = [json.loads(line) for line in cached.read_text(encoding="utf-8").splitlines()]
    return [{**e, "source": name} for e in examples]


def load_holdout() -> list[dict]:
    """Hand-written prompts that are not from any public set (attacks + tricky benign)."""
    out = []
    for fname, source in (("holdout.jsonl", "holdout"), ("holdout_benign.jsonl", "holdout")):
        for line in (EVAL_DIR / fname).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append({**json.loads(line), "source": source})
    return out


def load_all() -> list[dict]:
    examples = []
    for name in SOURCES:
        examples += load_public(name)
    return examples + load_holdout()


if __name__ == "__main__":
    from collections import Counter

    data = load_all()
    print(Counter((e["source"], e["label"]) for e in data))
