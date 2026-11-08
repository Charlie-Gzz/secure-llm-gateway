# Bulwark: slide outline (7 slides)

All visuals are in `assets/`. Numbers come from `eval/results/results.md` (regenerate with `make eval`).

| # | Title (states the takeaway) | Content | Asset |
|---|---|---|---|
| 1 | **Bulwark: a security gateway for LLM apps** | One-line pitch: a drop-in proxy that blocks prompt injection, redacts PII, and shows exactly what happened to every request. Your name and the repo link. | `ui/logo.svg` + `assets/screenshots/playground-hero.png` |
| 2 | **LLM apps trust every prompt, and attackers know it** | Three risks with one example each: instruction override ("ignore previous instructions"), hidden instructions in documents (indirect injection), and PII sent to a third-party model. | `assets/screenshots/playground-ignore.png` (cropped to the chat) |
| 3 | **Layered guards, cheapest first** | Rules (~0.1 ms) → classifier (DeBERTa-v3 on ONNX, CPU) → PII redaction in and out. Blocked requests never reach the model. OpenAI-compatible: change one `base_url`. | `assets/diagram/architecture.png` |
| 4 | **Demo: watch a request get inspected** | Live demo or video clip. Show four buttons: normal (green), rules block (red), classifier block (red at layer 2), SSN redaction (amber). | `assets/screenshots/playground-roleplay.png`, `playground-ssn.png` |
| 5 | **The classifier does the heavy lifting; rules are the fast path** | Ablation: recall and FPR for rules only / classifier only / both. Callout: holdout recall vs public recall (it generalizes). | `assets/charts/ablation.png`, `assets/charts/recall_by_source.png` |
| 6 | **Safety costs milliseconds and fractions of a cent** | p95 added latency per layer; cost per 1K requests (LLM spend vs guard compute vs savings from blocking). Grafana screenshot as proof it's observable in production. | `assets/charts/latency.png`, `assets/charts/cost_per_1k.png`, `assets/screenshots/grafana.png` |
| 7 | **What I learned** | (1) int8 quantization made the model 3× smaller and destroyed it; always re-evaluate after optimizing. (2) Public benchmarks disagree on what counts as "injection" (role-play prompts, German text). (3) Near-miss benign prompts ("enable developer mode on Android") are where rules break. (4) Known gaps: non-English, some indirect injections, jailbreak role-play. Next: an LLM-as-judge for borderline scores. | `assets/charts/precision_recall.png`, `assets/screenshots/jaeger-trace.png` |

**Speaker-note tip:** lead every results slide with the headline sentence from `results.md`
("Catches X% of prompt-injection attacks with Y% false positives, adding Z ms p95 latency").
