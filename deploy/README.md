# Deploy (prepared, not deployed)

Two equivalent configs for a small public demo of the playground:

| File | Platform | Notes |
|---|---|---|
| `cloudrun.yaml` | Google Cloud Run | scale-to-zero, max 1 instance, key from Secret Manager |
| `fly.toml` | Fly.io | auto-stop machines, volume for the SQLite log |

## Cost and abuse guardrails

| Guardrail | Where | Demo value |
|---|---|---|
| Per-client rate limit | `RATE_LIMIT_RPM` → `gateway/limits.py` | 20 req/min |
| Prompt size cap | `MAX_INPUT_CHARS` → 413 before any guard runs | 4,000 chars |
| Output token cap | `policy.yaml` → `upstream.max_tokens` | 1,024 tokens |
| Daily spend cap | `DAILY_SPEND_CAP_USD` (summed from the SQLite request log) | $2/day |
| Max instances | platform config | 1 |
| Backstop | Anthropic Console monthly limit + cloud budget alert | set manually |

At Claude Haiku 5.5 prices ($0.10 / $0.50 per 1M tokens) a $2/day cap is roughly
10,000 typical requests per day, far above what a portfolio demo will see.

The observability stack (Jaeger, Prometheus, Grafana) is for local demos; for a public
deploy, point `OTEL_EXPORTER_OTLP_ENDPOINT` at a managed backend (e.g. Grafana Cloud).
