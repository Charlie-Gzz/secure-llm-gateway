# Questions for Charlie

Each question includes my recommendation and what I did in the meantime.

## 1. No Anthropic API key was available during the build
`GATEWAY_ANTHROPIC_API_KEY` was empty, so `.env` was written with `UPSTREAM=mock`. Everything (tests, traffic, eval, playground, screenshots) runs against the mock upstream.
- **Recommendation:** set the key later, put it in `.env` as `ANTHROPIC_API_KEY=...`, flip `UPSTREAM=anthropic`, and run `make eval-cost` (≤100 requests) to verify the computed cost-per-1K against a real run.
- **Meanwhile:** cost numbers are computed from token counts × configured prices.

