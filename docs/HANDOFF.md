# Handoff

Milestones M0–M7 are done, plus stretch item 1 (the README GIF). The private repo is
https://github.com/Charlie-Gzz/secure-llm-gateway, and CI is green (lint + 57 tests).

## 1. What was built
- **Bulwark**, an OpenAI-compatible gateway (`POST /v1/chat/completions`) in FastAPI. It has a Claude upstream (`claude-haiku-5-5` through the official SDK) and an offline mock upstream.
- **Layered guards:**
  - Regex rules (9 families, with Unicode normalization).
  - A DeBERTa-v3 prompt-injection classifier on ONNX Runtime (CPU, windowed for long prompts).
  - Presidio PII redaction on both the prompt and the answer.
  - `policy.yaml` holds thresholds, actions, the model ID, and prices.
- **A `gateway` verdict field and `X-Gateway-Verdict` header** on every response: verdict, deciding layer and reason, scores, redactions, the redacted prompt, latency per step, tokens, cost, and trace ID.
- **Observability:** one OpenTelemetry trace per request with a span per step (Collector → Jaeger), Prometheus metrics at `/metrics`, a provisioned dark Grafana dashboard, and a SQLite request/cost log.
- **Evaluation** (`make eval`): about 3,000 prompts from 4 public datasets plus a hand-written holdout of 30 attacks and 30 near-miss benign prompts. It covers the ablation, per-source recall, a threshold sweep, latency per layer, and cost per 1K requests.
- **Playground** at `/`: chat plus a request inspector with 6 one-click examples. Each example was verified to light up the intended pipeline.
- **Portfolio kit:** charts, diagram, screenshots, a GIF, a demo script, a slides outline, and a portfolio card.
- **Deploy configs** for Cloud Run and Fly.io, prepared but not deployed. They rely on in-app limits: rate limit, prompt-size cap, and daily spend cap.

## 2. How to run it
```bash
git clone https://github.com/Charlie-Gzz/secure-llm-gateway && cd secure-llm-gateway
docker compose up -d --build     # playground :8000 · Grafana :3000 · Jaeger :16686 · Prometheus :9090
uv run python scripts/traffic.py # or `make traffic`, to fill the dashboard
```
Local development (no Docker): `uv sync && uv run python scripts/export_classifier.py && make run`.
On Windows, use `mingw32-make <target>` if GNU make isn't installed.
Other targets: `make test`, `make lint`, `make eval`, `make assets` (needs the stack running), `make gif`, and `make eval-cost` (needs an API key, max 100 requests).

## 3. Headline results (eval/results/results.md)
- **Catches 84.3% of prompt-injection attacks with 0.4% false positives** (precision 99.5%, F1 91.3%) on 1,563 public attacks and 1,399 benign prompts.
- **93.3% recall on hand-written holdout attacks** that aren't in any dataset. The near-miss benign false-positive rate is 6.7%.
- **Ablation:** rules alone get 36.7% recall at 0% FPR; the classifier alone gets 83.9%; the two together get 84.3%.
- **Recall by source:** Gandalf 99.9%, in-the-wild jailbreaks 71%, deepset 40% (many misses are German or role-play prompts that deepset labels as injections).
- **Latency on benign prompts:** guards add 39 ms at p50 and 329 ms at p95. Rules take 0.1 ms, PII 7 ms, and the classifier 32 ms at p50.
- **Cost per 1K requests:** about $0.17 of Haiku spend, $0.004 of guard CPU time, and about $0.03 saved by blocking attacks. These are computed from token estimates; no real API run yet.

## 4. Visual assets (`assets/`)
- `charts/`: ablation, latency, precision_recall, cost_per_1k, and recall_by_source as PNG (1600 px) and SVG, plus `index.html` (interactive Plotly).
- `screenshots/`: playground for each example (×6), playground-hero, grafana, and jaeger-trace (all 2× retina).
- `diagram/`: architecture.svg (fonts embedded) and architecture.png.
- `playground.gif`: the README hero (2.8 MB).
- `fonts/`: Inter and JetBrains Mono (OFL), used by charts and the diagram.
- Docs: `docs/DEMO_SCRIPT.md`, `docs/SLIDES_OUTLINE.md`, `docs/PORTFOLIO_CARD.md`.

## 5. Questions on direction (details in QUESTIONS_FOR_CHARLIE.md)
1. **Add an API key and run `make eval-cost`?** Everything currently runs on the mock upstream. *Recommendation:* create a key with a low monthly limit, put it in `.env` (`ANTHROPIC_API_KEY`, `UPSTREAM=anthropic`), and run `make eval-cost` (50 requests, a fraction of a cent) to confirm the cost-per-1K estimate.
2. **Should the rules layer block or only observe?** It adds little recall but makes verdicts explainable and skips the classifier on obvious attacks. *Recommendation:* keep it blocking and tell the honest ablation story: "the classifier does the heavy lifting".
3. **Do a speed pass on p95 latency?** The classifier's cost grows steeply with prompt length, and thread tuning didn't help. *Recommendation:* present p50 and p95 as they are for now; if you want a better number, try ONNX Runtime's transformer optimizer or a distilled model, and re-run `make eval`.
4. **How loudly to state the limitations?** These are English-only detection, some indirect injections, and role-play jailbreaks. *Recommendation:* keep the README's Limitations section; it builds credibility. The LLM-as-judge stretch item would address borderline cases.
5. **Name and visibility.** I chose "Bulwark" but didn't check trademark or package-name conflicts. The repo stays private until you review it. *Recommendation:* do a quick name search, then make it public.

## 6. Skipped or simplified, and why
- **Mock upstream everywhere:** no `GATEWAY_ANTHROPIC_API_KEY` was set, so no real Claude call was ever made. The Anthropic upstream is implemented and unit-tested only for message translation. `make eval-cost` exists but hasn't been run.
- **Cost numbers are estimates:** about 4 characters per token, plus an assumed 150-token system prompt and 300 output tokens (listed in `results.md`).
- **int8 quantization was rejected:** it destroyed accuracy. The fp32 model is served, and the lesson is logged.
- **The rules were tuned once after seeing the holdout:** three real bugs, fixed with general patterns and regression tests. The v1 numbers are logged in DECISIONS.md, and the holdout is no longer fully blind for the rules layer.
- **The fresh-clone test reused Docker's layer cache.** The layers matched by content, so the files are identical. The actual model download inside the Dockerfile was verified on the first, uncached build.
- **Stretch items 2–4 weren't done:** a Locust load test, streaming, and an LLM-as-judge layer.
- **Not deployed anywhere,** as the plan requires. The configs in `deploy/` are ready for review.
