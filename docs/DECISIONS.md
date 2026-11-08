# Decisions

Format: `Decision | Options considered | Why I picked this | Easy to change? (yes/no)`

| Decision | Options considered | Why I picked this | Easy to change? |
|---|---|---|---|
| Product name: **Bulwark** | Bastion, Aegis, Sentinel, Warden, Moat | Short, memorable, literally means "a defensive wall"; fits the shield logo; less overused than Aegis/Sentinel in the LLM-security space | yes (string in config + logo SVG) |
| Default branch `main` | main, master | GitHub default | yes |
| Upstream defaults to `mock` | anthropic, mock | `GATEWAY_ANTHROPIC_API_KEY` was not set at build time (Section 1.2) | yes (`UPSTREAM` in `.env`) |
