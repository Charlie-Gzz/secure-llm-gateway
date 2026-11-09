# Bulwark evaluation results

_Generated 2026-11-09 00:57 UTC on Windows AMD64, Python 3.12.16. Regenerate with `make eval`._

**Catches 84.3% of prompt-injection attacks with 0.4% false positives, adding 294 ms p95 latency.**

## Ablation (all public sets)

| Config | Precision | Recall | F1 | FPR on benign |
|---|---:|---:|---:|---:|
| rules only | 100.0% | 36.7% | 53.7% | 0.0% |
| classifier only | 99.5% | 83.9% | 91.1% | 0.4% |
| rules + classifier | 99.5% | 84.3% | 91.3% | 0.4% |
| judge only | 100.0% | 26.4% | 41.8% | 0.0% |
| rules + classifier + judge | 99.5% | 84.8% | 91.6% | 0.4% |

## Recall by attack source

| Source | Attacks | Rules only | Classifier only | Rules + classifier | Judge only | Rules + classifier + judge |
|---|---:|---:|---:|---:|---:|---:|
| deepset | 263 | 6.1% | 39.2% | 40.3% | 7.2% | 40.7% |
| gandalf | 1000 | 49.5% | 99.9% | 99.9% | 17.7% | 99.9% |
| jailbreak_wild | 300 | 21.0% | 70.0% | 71.0% | 72.3% | 73.0% |
| holdout | 30 | 0.0% | 93.3% | 93.3% | 26.7% | 93.3% |

## False-positive rate by benign source

| Source | Benign prompts | Rules only | Classifier only | Rules + classifier | Judge only | Rules + classifier + judge |
|---|---:|---:|---:|---:|---:|---:|
| deepset | 399 | 0.0% | 0.8% | 0.8% | 0.0% | 0.8% |
| no_robots | 1000 | 0.0% | 0.3% | 0.3% | 0.0% | 0.3% |
| holdout | 30 | 0.0% | 6.7% | 6.7% | 0.0% | 6.7% |

## Judge layer (optional, `make judge-model`)

Qwen/Qwen3Guard-Gen-0.6B (ONNX, fp32, CPU). Runs only when the classifier score is in [0.1, 0.9) and rules + classifier didn't block; blocks when P(unsafe or controversial) x P(Jailbreak) >= 0.5.

- Escalated: **1.0%** of all prompts, 0.2% of benign ones
- Judge latency when it runs: p50 963 ms, p95 2723 ms (mean added per benign request: 8.6 ms)
- New catches on public sets: **7** attacks; new false positives: **0**

Sensitivity (the shipped setting is the first row; it was fixed before looking at these numbers):

| Band | Judge rule | Recall | FPR | Holdout recall | Holdout FPR | Escalated |
|---|---|---:|---:|---:|---:|---:|
| [0.1, 0.9) | flagged x jailbreak | 84.8% | 0.4% | 93.3% | 6.7% | 1.0% |
| [0.01, 0.9) | flagged x jailbreak | 85.2% | 0.4% | 93.3% | 6.7% | 2.1% |
| [0.0, 0.9) | flagged x jailbreak | 86.9% | 0.4% | 93.3% | 6.7% | 55.2% |
| [0.1, 0.9) | flagged | 85.2% | 0.5% | 96.7% | 6.7% | 1.0% |
| [0.1, 0.9) | jailbreak | 85.0% | 0.4% | 96.7% | 6.7% | 1.0% |

## Generalization (holdout vs public)

Hand-written holdout attacks not from any public set: recall **93.3%** vs **84.3%** on public sets (rules + classifier). Holdout benign FPR: 6.7%.

## Latency per layer (ms, CPU)

Benign prompts are what normal users send (the headline number). All prompts include
long jailbreaks (up to 8K characters) that need several 512-token classifier windows.

| Layer | p50 benign | p95 benign | p50 all | p95 all |
|---|---:|---:|---:|---:|
| rules | 0.08 | 0.89 | 0.07 | 1.28 |
| classifier | 29.60 | 261.41 | 26.81 | 566.57 |
| pii | 6.53 | 37.33 | 6.03 | 54.70 |
| total guards | 36.28 | 294.22 | 32.82 | 626.10 |

## Cost per 1K requests

- Upstream LLM (claude-haiku-5-5): **$0.1723** (avg 223.2 input + 300 output tokens)
- Guard compute (CPU): **$0.0032**
- Saved by blocking attacks before the LLM (20% attack mix): **$0.0291**

## Classifier threshold sweep

| Threshold | Precision | Recall | FPR |
|---:|---:|---:|---:|
| 0.5 | 99.5% | 85.1% | 0.5% |
| 0.7 | 99.5% | 84.8% | 0.5% |
| 0.8 | 99.5% | 84.7% | 0.5% |
| 0.9 | 99.5% | 84.3% | 0.4% |
| 0.95 | 99.5% | 84.1% | 0.4% |
| 0.98 | 99.8% | 83.5% | 0.2% |
| 0.99 | 99.8% | 82.5% | 0.1% |
| 0.995 | 99.9% | 81.6% | 0.1% |
| 0.999 | 100.0% | 78.9% | 0.0% |

## Datasets

| Name | Hugging Face repo | License | Role |
|---|---|---|---|
| deepset | `deepset/prompt-injections` | Apache-2.0 | mixed injections + benign (some German) |
| gandalf | `Lakera/gandalf_ignore_instructions` | MIT | real human injection attempts from the Gandalf game |
| jailbreak_wild | `TrustAIRLab/in-the-wild-jailbreak-prompts` | MIT | jailbreak prompts collected from Reddit/Discord (sampled 300) |
| no_robots | `HuggingFaceH4/no_robots` | CC-BY-NC-4.0 | human-written benign user requests (sampled 1,000) |
| holdout | `eval/holdout*.jsonl` (hand-written) | MIT (this repo) | 30 attacks + 30 tricky benign prompts |
