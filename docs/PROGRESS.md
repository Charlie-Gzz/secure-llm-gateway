# Progress

## Status
- [x] M0: environment setup
- [ ] M1: skeleton + pass-through proxy
- [ ] M2: guards + policy
- [ ] M3: observability
- [ ] M4: evaluation
- [ ] M5: playground UI
- [ ] M6: visual assets + portfolio kit
- [ ] M7: README + handoff

## Log
- **M0** — Installed uv 0.13.7 and Python 3.12.16. Docker Desktop was not running; started it. PyPI and Hugging Face reachable. No API key → `UPSTREAM=mock`. Private repo created.

## Next
- M1: pyproject, Makefile, FastAPI app with `/v1/chat/completions`, mock + Anthropic upstreams, cost tracking in SQLite, `/healthz`.
