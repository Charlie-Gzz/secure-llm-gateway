"""Judge guard: a small guard LLM (Qwen3Guard-Gen-0.6B, Apache-2.0) for borderline prompts.

The classifier is fast but sometimes unsure. Prompts whose classifier score falls inside a
configurable band are escalated to this judge, which reads the whole prompt with an
instruction-following model trained for moderation (its "Jailbreak" category is "content
that explicitly attempts to override the model's system prompt or model conditioning").

No text generation: one forward pass over

    <policy prompt> + user text + <assistant turn> + "Safety: Unsafe\\nCategories:"

reads two next-token distributions at once (teacher forcing):
  - after "Safety:"      -> P(Unsafe or Controversial) vs P(Safe)
  - after "Categories:"  -> P(Jailbreak) among the model's categories
The judge score is their product: "flagged, and flagged as a jailbreak". Running offline on
CPU keeps the whole project key-free; a Claude-based judge would be a drop-in alternative.

Export the model with `make judge-model` (scripts/export_judge.py).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from gateway.config import classifier_threads
from gateway.guards.base import GuardResult

LABEL_CUE = "Safety:"
CATEGORY_CUE = " Unsafe\nCategories:"
LABELS = {"safe": " Safe", "unsafe": " Unsafe", "controversial": " Controversial"}
CATEGORIES = [
    " Violent",
    " Non-violent Illegal Acts",
    " Sexual Content or Sexual Acts",
    " PII",
    " Suicide & Self-Harm",
    " Unethical Acts",
    " Politically Sensitive Topics",
    " Copyright Violation",
    " Jailbreak",
    " None",
]
MAX_CHARS = 6000  # judge sees at most this much of a prompt (head + tail), ~1.5K tokens


class JudgeGuard:
    def __init__(self, model_dir: Path, threshold: float = 0.5):
        onnx_file = model_dir / "model.onnx"
        if not onnx_file.exists():
            raise FileNotFoundError(f"{onnx_file} missing; run `make judge-model`")
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = classifier_threads()
        self.session = ort.InferenceSession(
            str(onnx_file), opts, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.no_padding()
        self.tokenizer.no_truncation()
        template = json.loads((model_dir / "template.json").read_text(encoding="utf-8"))
        self.prefix, self.suffix = template["prefix"], template["suffix"]
        self.model_name = template.get("model", "judge")
        self.threshold = threshold

        def first_id(text: str) -> int:
            return self.tokenizer.encode(text, add_special_tokens=False).ids[0]

        self.label_ids = {k: first_id(v) for k, v in LABELS.items()}
        self.category_ids = sorted({first_id(c) for c in CATEGORIES})
        self.jailbreak_id = first_id(" Jailbreak")
        if len(set(self.label_ids.values())) != len(LABELS):
            raise ValueError("judge label tokens are not distinct")

    def probabilities(self, text: str) -> tuple[float, float]:
        """(P(flagged: unsafe or controversial), P(jailbreak | flagged))."""
        if len(text) > MAX_CHARS:
            half = MAX_CHARS // 2
            text = text[:half] + "\n[...]\n" + text[-half:]
        head = self.prefix + text + self.suffix + LABEL_CUE
        full = head + CATEGORY_CUE
        enc = self.tokenizer.encode(full, add_special_tokens=False)
        # Token positions whose prediction is the next token after each cue.
        pos_label = _token_ending_at(enc.offsets, len(head))
        pos_category = len(enc.ids) - 1
        ids = np.array([enc.ids], dtype=np.int64)
        logits = self.session.run(
            None,
            {
                "input_ids": ids,
                "attention_mask": np.ones_like(ids),
                "positions": np.array([pos_label, pos_category], dtype=np.int64),
            },
        )[0][0]
        label = _softmax_over(logits[0], list(self.label_ids.values()))
        p_safe, p_unsafe, p_contro = (label[self.label_ids[k]] for k in LABELS)
        category = _softmax_over(logits[1], self.category_ids)
        return float(p_unsafe + p_contro), float(category[self.jailbreak_id])

    def score(self, text: str) -> float:
        flagged, jailbreak = self.probabilities(text)
        return flagged * jailbreak

    def check(self, text: str) -> GuardResult:
        t0 = time.perf_counter()
        flagged, jailbreak = self.probabilities(text)
        p = flagged * jailbreak
        detail = {
            "model": self.model_name,
            "p_flagged": round(flagged, 4),
            "p_jailbreak": round(jailbreak, 4),
            "threshold": self.threshold,
            "inference_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
        if p >= self.threshold:
            reason = f"Judge flagged a jailbreak (p={p:.2f})"
            return GuardResult(status="block", score=p, detail=detail, reason=reason)
        return GuardResult(status="pass", score=p, detail=detail)


def _token_ending_at(offsets: list[tuple[int, int]], char_end: int) -> int:
    """Index of the last token that ends at or before `char_end`."""
    idx = 0
    for i, (_, end) in enumerate(offsets):
        if end <= char_end:
            idx = i
        else:
            break
    return idx


def _softmax_over(logits: np.ndarray, ids: list[int]) -> dict[int, float]:
    """Softmax restricted to the candidate token ids (the answer must be one of them)."""
    sub = logits[ids].astype(np.float64)
    e = np.exp(sub - sub.max())
    probs = e / e.sum()
    return dict(zip(ids, probs.tolist(), strict=True))
