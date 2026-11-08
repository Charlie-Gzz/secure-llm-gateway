# Progress

## Status
- [x] M0: environment setup
- [x] M1: skeleton + pass-through proxy
- [x] M2: guards + policy
- [x] M3: observability
- [ ] M4: evaluation
- [ ] M5: playground UI
- [ ] M6: visual assets + portfolio kit
- [ ] M7: README + handoff

## Log
- **M0** â€” Installed uv 0.13.7 and Python 3.12.16. Docker Desktop was not running; started it. PyPI and Hugging Face reachable. No API key â†’ `UPSTREAM=mock`. Private repo created.

- **M1** — FastAPI app with OpenAI-compatible `/v1/chat/completions`, mock + Anthropic (SDK) upstreams, cost from `policy.yaml` prices, SQLite request log, `/healthz`. 8 tests pass incl. OpenAI SDK drop-in against a live uvicorn server.
- **M2** — Rules guard (9 regex families, Unicode normalization), ONNX classifier (protectai deberta-v3 v2, fp32, ~27 ms/prompt on CPU, windowed for long prompts), Presidio PII on input + output, policy.yaml wiring, graceful degrade if a guard can't load. int8 quantization tried and rejected (destroys accuracy). 51 tests pass.
- **M3** — OTel spans per step under one trace (verified in Jaeger v2 via `/api/v3`), Prometheus metrics at `/metrics`, docker compose stack (gateway, collector, Jaeger, Prometheus, Grafana w/ anonymous viewer + provisioned dashboard), `scripts/traffic.py`. Verified: 200 requests → Prometheus counts match traffic, Jaeger has `gateway.request` + 5 step spans. Image slimmed 4.85→3.29 GB. 53 tests pass.

## Next
- M4: finish eval run (datasets: deepset, gandalf, in-the-wild jailbreaks, no_robots + holdout), commit results.
