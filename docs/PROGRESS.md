# Progress

## Status
- [x] M0: environment setup
- [x] M1: skeleton + pass-through proxy
- [ ] M2: guards + policy
- [ ] M3: observability
- [ ] M4: evaluation
- [ ] M5: playground UI
- [ ] M6: visual assets + portfolio kit
- [ ] M7: README + handoff

## Log
- **M0** — Installed uv 0.13.7 and Python 3.12.16. Docker Desktop was not running; started it. PyPI and Hugging Face reachable. No API key → `UPSTREAM=mock`. Private repo created.

- **M1** � FastAPI app with OpenAI-compatible `/v1/chat/completions`, mock + Anthropic (SDK) upstreams, cost from `policy.yaml` prices, SQLite request log, `/healthz`. 8 tests pass incl. OpenAI SDK drop-in against a live uvicorn server.

## Next
- M2: rules guard, ONNX classifier (protectai deberta v2), Presidio PII, policy wiring, tests.
