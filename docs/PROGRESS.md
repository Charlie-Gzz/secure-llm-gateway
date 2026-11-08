# Progress

## Status
- [x] M0: environment setup
- [x] M1: skeleton + pass-through proxy
- [x] M2: guards + policy
- [x] M3: observability
- [x] M4: evaluation
- [x] M5: playground UI
- [x] M6: visual assets + portfolio kit
- [x] M7: README + handoff
- [x] Stretch 1: playground GIF
- [x] Stretch 2: Locust load test
- [x] Stretch 3: streaming
- [ ] Stretch 4: LLM-as-judge

## Log
- **M0** — Installed uv 0.13.7 and Python 3.12.16. Docker Desktop was not running; started it. PyPI and Hugging Face reachable. No API key → `UPSTREAM=mock`. Private repo created.

- **M1** — FastAPI app with OpenAI-compatible `/v1/chat/completions`, mock + Anthropic (SDK) upstreams, cost from `policy.yaml` prices, SQLite request log, `/healthz`. 8 tests pass incl. OpenAI SDK drop-in against a live uvicorn server.
- **M2** — Rules guard (9 regex families, Unicode normalization), ONNX classifier (protectai deberta-v3 v2, fp32, ~27 ms/prompt on CPU, windowed for long prompts), Presidio PII on input + output, policy.yaml wiring, graceful degrade if a guard can't load. int8 quantization tried and rejected (destroys accuracy). 51 tests pass.
- **M3** — OTel spans per step under one trace (verified in Jaeger v2 via `/api/v3`), Prometheus metrics at `/metrics`, docker compose stack (gateway, collector, Jaeger, Prometheus, Grafana w/ anonymous viewer + provisioned dashboard), `scripts/traffic.py`. Verified: 200 requests → Prometheus counts match traffic, Jaeger has `gateway.request` + 5 step spans. Image slimmed 4.85→3.29 GB. 53 tests pass.
- **M4** — `make eval`: 2,962 prompts (deepset, Gandalf, in-the-wild jailbreaks, no_robots, 60 hand-written holdout). Headline: catches 84.3% of attacks with 0.4% FPR, guards add 39 ms p50 / 329 ms p95 on benign prompts. Holdout recall 93.3%. Rules bugs found by the near-miss holdout fixed (v1 numbers kept in DECISIONS).
- **M5** — Playground at `/`: chat + request inspector, 6 example buttons, each verified to produce its intended pipeline (normal=all green, ignore=rules red, ssn=pii amber, roleplay=classifier red, indirect=classifier red, contact=pii-answer amber).
- **M6** — `make assets`: 5 charts (PNG 1600px + SVG, CVD-validated palette) + Plotly page, architecture diagram (SVG w/ embedded fonts + PNG), 9 Playwright screenshots (playground ×7, Grafana, Jaeger). DEMO_SCRIPT, SLIDES_OUTLINE, PORTFOLIO_CARD written. deploy/ (Cloud Run + Fly) with in-app rate/size/spend limits. CI workflow.
- **M7** — README (GIF hero, quickstart, how it works, results, limitations), LICENSE, `eval/cost_check.py`. Fresh clone from GitHub → `docker compose up` → healthy, traffic flows to Prometheus/Jaeger/Grafana. HANDOFF written. CI green (57 tests incl. ML).
- **Stretch 1** — `scripts/record_gif.py` → `assets/playground.gif` (2.8 MB).
- **Docs** — Mock upstream presented as a deliberate choice (Charlie: learning/showcase project, no API key needed).
- **Stretch 2** — `make loadtest` (Locust, 1–64 users). Found that the CPU-bound guards blocked the event loop: capacity flattened at 18.7 req/s. Moved classifier + Presidio to a thread pool sized by a sweep (3 workers × 4 ONNX threads on 12 cores): 35.9 req/s, p95 at 32 users 1.1 s → 0.48 s. Re-ran `make eval`: accuracy identical, latency 37 ms p50 / 316 ms p95. Chart `assets/charts/load_test.png`. 58 tests.
- **Stretch 3** — Streaming (`stream: true`): OpenAI chunk format, works with the OpenAI SDK, `include_usage`, blocked prompts stream a `content_filter` finish, mid-stream errors become an error event. Output PII is redacted per sentence so entities split across chunks never leak (tested with 1–3 character chunks). Playground streams; inspector shows time to first token. Jaeger trace verified. 66 tests.

## Next
- Stretch 4: LLM-as-judge for borderline classifier scores, added to the ablation.
