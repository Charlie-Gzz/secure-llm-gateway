"""Fetch the prompt-injection classifier as ONNX for CPU inference with ONNX Runtime.

Primary:  protectai/deberta-v3-base-prompt-injection-v2 (Apache-2.0, ships an ONNX export).
Fallback: deepset/deberta-v3-base-injection (exported locally with optimum; needs torch).

Output: models/prompt-injection/{model.onnx, tokenizer.json, config.json}

Note: int8 dynamic quantization was tried and rejected; it destroys this model's accuracy
(see docs/DECISIONS.md). fp32 already runs in ~27 ms per prompt on a laptop CPU.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "models" / "prompt-injection"
PRIMARY = "protectai/deberta-v3-base-prompt-injection-v2"
FALLBACK = "deepset/deberta-v3-base-injection"


def fetch_primary() -> None:
    for name in ("model.onnx", "tokenizer.json", "config.json"):
        path = hf_hub_download(PRIMARY, f"onnx/{name}")
        shutil.copy(path, OUT / name)


def export_fallback() -> None:
    try:
        from optimum.onnxruntime import ORTModelForSequenceClassification
        from transformers import AutoTokenizer
    except ImportError:
        sys.exit("Fallback export needs: uv pip install 'optimum[onnxruntime]' transformers torch")
    model = ORTModelForSequenceClassification.from_pretrained(FALLBACK, export=True)
    model.save_pretrained(OUT)
    AutoTokenizer.from_pretrained(FALLBACK).save_pretrained(OUT)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = PRIMARY
    try:
        fetch_primary()
    except Exception as e:  # network, repo layout change, etc.
        print(f"Primary model failed ({e}); trying fallback {FALLBACK}")
        source = FALLBACK
        export_fallback()

    labels = json.loads((OUT / "config.json").read_text())["id2label"]
    (OUT / "source.json").write_text(json.dumps({"repo": source, "id2label": labels}, indent=2))
    for f in sorted(OUT.iterdir()):
        print(f"{f.name:20s} {f.stat().st_size / 1e6:8.1f} MB")
    print(f"Classifier ready from {source}; labels={labels}")


if __name__ == "__main__":
    main()
