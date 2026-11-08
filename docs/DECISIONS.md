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
