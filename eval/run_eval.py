"""Evaluate Bulwark's guards (no upstream calls) and write eval/results/.

Measures, for rules only / classifier only / rules + classifier:
  precision, recall, F1, false-positive rate on benign prompts, per-source recall,
  holdout vs public recall, latency p50/p95 per layer, and cost per 1K requests.

    uv run python eval/run_eval.py          (or: make eval)
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.datasets import SOURCES, load_all  # noqa: E402
from gateway.config import Policy  # noqa: E402
from gateway.cost import cost_usd, estimate_tokens  # noqa: E402
from gateway.guards.classifier import ClassifierGuard  # noqa: E402
from gateway.guards.pii import PiiGuard  # noqa: E402
from gateway.guards.rules import RulesGuard  # noqa: E402

RESULTS = ROOT / "eval" / "results"
SWEEP = [0.5, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995, 0.999]

# Cost assumptions (documented in results.md). Prices themselves come from policy.yaml.
ASSUMED_OUTPUT_TOKENS = 300  # typical chat answer length
ASSUMED_SYSTEM_TOKENS = 150  # app system prompt sent with every request
VCPU_SECOND_USD = 0.000024  # Cloud Run CPU list price per vCPU-second (assumption)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def score_all(examples: list[dict], policy: Policy) -> list[dict]:
    rules = RulesGuard()
    clf = ClassifierGuard(ROOT / "models" / "prompt-injection", policy.guards.classifier.threshold)
    pii = PiiGuard()
    pii_cfg = policy.guards.pii_input
    clf.score("warm up")
    pii.redact("warm up", pii_cfg.entities, pii_cfg.min_score)

    records = []
    started = time.perf_counter()
    for i, ex in enumerate(examples, 1):
        text = ex["text"]
        t0 = time.perf_counter()
        rule_hits = [r.id for r in rules.matches(text)]
        t1 = time.perf_counter()
        score = clf.score(text)
        t2 = time.perf_counter()
        pii.redact(text, pii_cfg.entities, pii_cfg.min_score)
        t3 = time.perf_counter()
        records.append(
            {
                **ex,
                "rules": rule_hits,
                "score": score,
                "ms": {
                    "rules": (t1 - t0) * 1000,
                    "classifier": (t2 - t1) * 1000,
                    "pii": (t3 - t2) * 1000,
                },
            }
        )
        if i % 250 == 0:
            print(f"  scored {i}/{len(examples)} ({time.perf_counter() - started:.0f}s)")
    return records


def predictors(threshold: float) -> dict:
    return {
        "rules only": lambda r: bool(r["rules"]),
        "classifier only": lambda r: r["score"] >= threshold,
        "rules + classifier": lambda r: bool(r["rules"]) or r["score"] >= threshold,
    }


def confusion(records: list[dict], predict) -> dict:
    tp = sum(1 for r in records if r["label"] == 1 and predict(r))
    fn = sum(1 for r in records if r["label"] == 1 and not predict(r))
    fp = sum(1 for r in records if r["label"] == 0 and predict(r))
    tn = sum(1 for r in records if r["label"] == 0 and not predict(r))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
        "attacks": tp + fn,
        "benign": fp + tn,
    }


def examples_of(records, predict, label, wanted, n=8):
    """A few misclassified prompts for error analysis (truncated)."""
    picked = [r for r in records if r["label"] == label and predict(r) == wanted]
    picked.sort(key=lambda r: r["score"], reverse=not wanted)
    return [
        {
            "source": r["source"],
            "score": round(r["score"], 3),
            "rules": r["rules"],
            "text": r["text"][:220],
        }
        for r in picked[:n]
    ]


def latency_stats(records: list[dict]) -> dict:
    layers = {k: [r["ms"][k] for r in records] for k in ("rules", "classifier", "pii")}
    layers["total guards"] = [sum(r["ms"].values()) for r in records]
    return {
        k: {"p50": percentile(v, 0.5), "p95": percentile(v, 0.95), "mean": statistics.fmean(v)}
        for k, v in layers.items()
    }


def cost_per_1k(records: list[dict], policy: Policy, lat: dict, combined) -> dict:
    model = policy.upstream.model
    benign = [r for r in records if r["label"] == 0]
    avg_in = statistics.fmean(estimate_tokens(r["text"]) for r in benign) + ASSUMED_SYSTEM_TOKENS
    per_request = cost_usd(policy.pricing, model, round(avg_in), ASSUMED_OUTPUT_TOKENS)
    attack_share = 0.2  # same mix as scripts/traffic.py
    recall = confusion(records, combined)["recall"]
    guard_cpu_s = lat["total guards"]["mean"] / 1000
    return {
        "model": model,
        "avg_input_tokens": round(avg_in, 1),
        "assumed_output_tokens": ASSUMED_OUTPUT_TOKENS,
        "llm_usd_per_1k": per_request * 1000,
        "guard_compute_usd_per_1k": guard_cpu_s * VCPU_SECOND_USD * 1000,
        "saved_by_blocking_usd_per_1k": per_request * 1000 * attack_share * recall,
        "assumptions": {
            "system_prompt_tokens": ASSUMED_SYSTEM_TOKENS,
            "attack_share_of_traffic": attack_share,
            "vcpu_second_usd": VCPU_SECOND_USD,
            "token_estimate": "~4 characters per token",
        },
    }


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def to_markdown(res: dict) -> str:
    h = res["headline"]
    lines = [
        "# Bulwark evaluation results",
        "",
        f"_Generated {res['generated_at']} on {res['machine']}. Regenerate with `make eval`._",
        "",
        f"**{h['sentence']}**",
        "",
        "## Ablation (all public sets)",
        "",
        "| Config | Precision | Recall | F1 | FPR on benign |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, m in res["configs"].items():
        lines.append(
            f"| {name} | {pct(m['precision'])} | {pct(m['recall'])} | "
            f"{pct(m['f1'])} | {pct(m['fpr'])} |"
        )
    lines += [
        "",
        "## Recall by attack source",
        "",
        "| Source | Attacks | Rules only | Classifier only | Rules + classifier |",
        "|---|---:|---:|---:|---:|",
    ]
    for src, row in res["by_source"].items():
        if row["attacks"]:
            lines.append(
                f"| {src} | {row['attacks']} | {pct(row['rules only'])} | "
                f"{pct(row['classifier only'])} | {pct(row['rules + classifier'])} |"
            )
    lines += [
        "",
        "## False-positive rate by benign source",
        "",
        "| Source | Benign prompts | Rules only | Classifier only | Rules + classifier |",
        "|---|---:|---:|---:|---:|",
    ]
    for src, row in res["by_source"].items():
        if row["benign"]:
            lines.append(
                f"| {src} | {row['benign']} | {pct(row['fpr rules only'])} | "
                f"{pct(row['fpr classifier only'])} | "
                f"{pct(row['fpr rules + classifier'])} |"
            )
    g = res["generalization"]
    lines += [
        "",
        "## Generalization (holdout vs public)",
        "",
        f"Hand-written holdout attacks not from any public set: recall "
        f"**{pct(g['holdout_recall'])}** vs **{pct(g['public_recall'])}** on public sets "
        f"(rules + classifier). Holdout benign FPR: {pct(g['holdout_fpr'])}.",
        "",
        "## Latency per layer (ms, CPU)",
        "",
        "Benign prompts are what normal users send (the headline number). All prompts include",
        "long jailbreaks (up to 8K characters) that need several 512-token classifier windows.",
        "",
        "| Layer | p50 benign | p95 benign | p50 all | p95 all |",
        "|---|---:|---:|---:|---:|",
    ]
    for layer, s in res["latency_ms_benign"].items():
        a = res["latency_ms"][layer]
        lines.append(
            f"| {layer} | {s['p50']:.2f} | {s['p95']:.2f} | {a['p50']:.2f} | {a['p95']:.2f} |"
        )
    c = res["cost"]
    lines += [
        "",
        "## Cost per 1K requests",
        "",
        f"- Upstream LLM ({c['model']}): **${c['llm_usd_per_1k']:.4f}** "
        f"(avg {c['avg_input_tokens']} input + {c['assumed_output_tokens']} output tokens)",
        f"- Guard compute (CPU): **${c['guard_compute_usd_per_1k']:.4f}**",
        f"- Saved by blocking attacks before the LLM (20% attack mix): "
        f"**${c['saved_by_blocking_usd_per_1k']:.4f}**",
        "",
        "## Classifier threshold sweep",
        "",
        "| Threshold | Precision | Recall | FPR |",
        "|---:|---:|---:|---:|",
    ]
    for row in res["threshold_sweep"]:
        lines.append(
            f"| {row['threshold']} | {pct(row['precision'])} | {pct(row['recall'])} | "
            f"{pct(row['fpr'])} |"
        )
    lines += [
        "",
        "## Datasets",
        "",
        "| Name | Hugging Face repo | License | Role |",
        "|---|---|---|---|",
    ]
    for name, (repo, _, lic, role) in SOURCES.items():
        lines.append(f"| {name} | `{repo}` | {lic} | {role} |")
    lines.append(
        "| holdout | `eval/holdout*.jsonl` (hand-written) | MIT (this repo) | "
        "30 attacks + 30 tricky benign prompts |"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    policy = Policy.load(ROOT / "policy.yaml")
    threshold = policy.guards.classifier.threshold
    print("Loading datasets...")
    examples = load_all()
    print(f"Scoring {len(examples)} prompts with all guards...")
    records = score_all(examples, policy)

    public = [r for r in records if r["source"] != "holdout"]
    holdout = [r for r in records if r["source"] == "holdout"]
    preds = predictors(threshold)
    combined = preds["rules + classifier"]

    configs = {name: confusion(public, p) for name, p in preds.items()}
    by_source = {}
    for src in [*SOURCES, "holdout"]:
        subset = [r for r in records if r["source"] == src]
        row = {
            "attacks": sum(r["label"] for r in subset),
            "benign": sum(1 - r["label"] for r in subset),
        }
        for name, p in preds.items():
            m = confusion(subset, p)
            row[name], row[f"fpr {name}"] = m["recall"], m["fpr"]
        by_source[src] = row

    sweep = []
    for t in SWEEP:
        for name in ("classifier only", "rules + classifier"):
            m = confusion(public, predictors(t)[name])
            sweep.append(
                {
                    "threshold": t,
                    "config": name,
                    **{k: m[k] for k in ("precision", "recall", "f1", "fpr")},
                }
            )

    lat = latency_stats(records)
    # What a normal user pays: latency on benign prompts (attack prompts include very long
    # jailbreaks that need several classifier windows and would skew the headline).
    lat_benign = latency_stats([r for r in public if r["label"] == 0])
    best = configs["rules + classifier"]
    holdout_m = confusion(holdout, combined)
    p95 = lat_benign["total guards"]["p95"]
    res = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
        "threshold": threshold,
        "n_prompts": len(records),
        "headline": {
            "recall": best["recall"],
            "fpr": best["fpr"],
            "p95_added_latency_ms": p95,
            "sentence": f"Catches {pct(best['recall'])} of prompt-injection attacks with "
            f"{pct(best['fpr'])} false positives, adding {p95:.0f} ms p95 latency.",
        },
        "configs": configs,
        "by_source": by_source,
        "generalization": {
            "public_recall": best["recall"],
            "holdout_recall": holdout_m["recall"],
            "holdout_fpr": holdout_m["fpr"],
        },
        "latency_ms": lat,
        "latency_ms_benign": lat_benign,
        "cost": cost_per_1k(public, policy, lat, combined),
        "threshold_sweep": [s for s in sweep if s["config"] == "rules + classifier"],
        "threshold_sweep_classifier_only": [s for s in sweep if s["config"] == "classifier only"],
        "errors": {
            "missed_attacks": examples_of(records, combined, 1, False),
            "false_positives": examples_of(records, combined, 0, True),
        },
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "results.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (RESULTS / "results.md").write_text(to_markdown(res), encoding="utf-8")
    print(f"\n{res['headline']['sentence']}")
    for name, m in configs.items():
        print(
            f"  {name:20s} P={pct(m['precision'])} R={pct(m['recall'])} "
            f"F1={pct(m['f1'])} FPR={pct(m['fpr'])}"
        )
    print(f"  holdout recall {pct(holdout_m['recall'])}, holdout FPR {pct(holdout_m['fpr'])}")
    print(f"Wrote {RESULTS / 'results.json'} and results.md")


if __name__ == "__main__":
    main()
