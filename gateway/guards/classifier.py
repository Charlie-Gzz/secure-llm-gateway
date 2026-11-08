"""Classifier guard: a DeBERTa-v3 prompt-injection model served with ONNX Runtime on CPU.

Loaded once at startup. Long prompts are scored in overlapping windows and the max
injection probability wins, so an attack can't hide at the end of a long message.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from gateway.guards.base import GuardResult


class ClassifierGuard:
    def __init__(
        self, model_dir: Path, threshold: float = 0.9, max_length: int = 512, stride: int = 128
    ):
        onnx_file = model_dir / "model.onnx"
        if not onnx_file.exists():
            raise FileNotFoundError(f"{onnx_file} missing; run `make models`")

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 0  # let ORT use all physical cores
        self.session = ort.InferenceSession(
            str(onnx_file), opts, providers=["CPUExecutionProvider"]
        )
        self.input_names = {i.name for i in self.session.get_inputs()}

        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.no_padding()
        self.tokenizer.no_truncation()

        labels = json.loads((model_dir / "config.json").read_text())["id2label"]
        self.injection_idx = next(
            int(i) for i, name in labels.items() if name.upper() not in {"SAFE", "LEGIT"}
        )
        self.threshold = threshold
        self.window = max_length - 2  # room for [CLS] and [SEP]
        self.stride = stride
        self.model_name = onnx_file.name
        self.cls_id = self.tokenizer.token_to_id("[CLS]")
        self.sep_id = self.tokenizer.token_to_id("[SEP]")

    def score(self, text: str) -> float:
        """Probability that `text` is a prompt injection (max over windows)."""
        ids = self.tokenizer.encode(text, add_special_tokens=False).ids
        chunks = [
            ids[i : i + self.window]
            for i in range(0, max(len(ids) - self.stride, 1), self.window - self.stride)
        ]
        batch = [[self.cls_id, *c, self.sep_id] for c in chunks]
        width = max(len(b) for b in batch)
        input_ids = np.zeros((len(batch), width), dtype=np.int64)
        mask = np.zeros_like(input_ids)
        for row, seq in enumerate(batch):
            input_ids[row, : len(seq)] = seq
            mask[row, : len(seq)] = 1

        feeds = {"input_ids": input_ids, "attention_mask": mask}
        if "token_type_ids" in self.input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)
        logits = self.session.run(None, feeds)[0]
        exp = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = exp / exp.sum(axis=1, keepdims=True)
        return float(probs[:, self.injection_idx].max())

    def check(self, text: str) -> GuardResult:
        if not text.strip():
            return GuardResult(status="pass", score=0.0)
        t0 = time.perf_counter()
        p = self.score(text)
        detail = {
            "model": self.model_name,
            "threshold": self.threshold,
            "inference_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
        if p >= self.threshold:
            return GuardResult(
                status="block",
                score=p,
                detail=detail,
                reason=f"Classifier flagged injection (p={p:.2f})",
            )
        return GuardResult(status="pass", score=p, detail=detail)
