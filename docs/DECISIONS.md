# Decisions

Format: `Decision | Options considered | Why I picked this | Easy to change? (yes/no)`

| Decision | Options considered | Why I picked this | Easy to change? |
|---|---|---|---|
| Product name: **Bulwark** | Bastion, Aegis, Sentinel, Warden, Moat | Short, memorable, literally means "a defensive wall"; fits the shield logo; less overused than Aegis/Sentinel in the LLM-security space | yes (string in config + logo SVG) |
| Default branch `main` | main, master | GitHub default | yes |
| Upstream defaults to `mock` | anthropic, mock | `GATEWAY_ANTHROPIC_API_KEY` was not set at build time (Section 1.2) | yes (`UPSTREAM` in `.env`) |
| Upstream model `claude-haiku-5-5` at $0.10 / $0.50 per 1M tokens, effort `low` | Haiku 4.5 ($1/$5), Sonnet 5.5 | Cheapest current Claude model per Anthropic's model table (checked Nov 2026). `low` effort keeps proxy latency/cost down. Model ID + prices live in `policy.yaml` | yes |
| Call Claude with the official `anthropic` SDK instead of raw httpx | httpx (plan's stack table), anthropic SDK | Anthropic's guidance is to use the official SDK (typed errors, retries); httpx is still used by tests and scripts. Note: anthropic 2.x is built on `httpx2` | yes |
| Don't forward `temperature` / `top_p` to Claude | forward them, drop them | Non-default sampling params return 400 on Haiku 5.5; dropping them keeps OpenAI clients that send `temperature` working | yes |
| Blocked requests return HTTP 200 with `finish_reason: "content_filter"` | 400/403 error, 200 + content_filter | Matches OpenAI's own behavior for filtered content, so unmodified clients don't crash; verdict is also in the `X-Gateway-Verdict` header and `gateway` field | yes |
| Mock upstream priced as Haiku (`mock-haiku`) and tokens estimated at ~4 chars/token | price at $0, real tokenizer | Keeps dashboards and cost math realistic offline without a tokenizer download | yes |
| Only `user` and `tool` message text is screened; `system`/`developer` prompts are trusted | screen everything | System prompts come from the app developer, not the end user; screening them would flag legit instructions like "ignore off-topic requests" | yes |
| OpenAI drop-in test uses a real uvicorn server on a free port | ASGI transport | openai 3.x uses `httpx2`, which can't share Starlette's httpx test client; a real socket is the more honest test anyway | yes |
| `make` on Windows via `mingw32-make` | install GNU make, PowerShell scripts | Already installed; Makefile is portable to macOS/Linux/devcontainer unchanged | yes |
| Classifier: `protectai/deberta-v3-base-prompt-injection-v2`, using the ONNX export shipped in its repo (Apache-2.0, not gated) | Export with optimum+torch; deepset fallback | Repo already publishes `onnx/model.onnx`; downloading it avoids a ~2 GB PyTorch install in dev and Docker. The optimum export path remains for the deepset fallback | yes |
| **Serve fp32, not int8.** Tried ONNX Runtime dynamic int8 quantization twice (default, and per-channel MatMul-only) | int8 (244–539 MB, ~21 ms) vs fp32 (739 MB, ~27 ms) | int8 destroyed accuracy: attacks scored ~0.05–0.15 and benign prompts up to 0.997. A ~20% latency gain is worthless if the model misses every attack. Lesson for the write-up: always re-evaluate after quantizing | yes |
| Classifier threshold 0.90 | 0.5, 0.8, 0.9, 0.95 | Model outputs are near-binary (most scores <0.05 or >0.95); 0.9 trims borderline false positives. Revisit after M4 eval | yes (`policy.yaml`) |
| Long prompts scored in 512-token windows (stride 128), max probability wins | truncate to 512 | Truncation would let an attacker hide the payload after 512 tokens of filler; covered by a test | yes |
| Presidio entities: SSN, credit card, email, phone, IBAN, passport, IP. **No PERSON** | include PERSON | spaCy PERSON would redact names in ordinary questions ("Who was Abraham Lincoln?"), breaking answers and inflating "redacted" verdicts | yes (`policy.yaml`) |
| PII `min_score` 0.4 | 0.5 (Presidio default-ish) | Presidio scores US phone numbers at 0.4 without strong context, so 0.5 missed "call 415-555-0132" | yes |
| spaCy `en_core_web_lg` pinned as a wheel URL in `pyproject.toml` | `spacy download` at setup time | `uv sync` removes packages that aren't in the lockfile, so a downloaded model would vanish on the next sync | yes |
| Rules guard tuned for precision; `no_restrictions` requires a response verb nearby | broad keyword match | Benign text like "a kingdom with no rules" must pass; the classifier handles subtler attacks | yes |
| Pipeline order kept as Rules → Classifier → PII | PII first | Tested: the classifier false positive on "remember X for later" persists after redaction, so reordering wouldn't help | yes |
