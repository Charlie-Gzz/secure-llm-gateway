# Questions for Charlie

Each question includes my recommendation and what I did in the meantime.

## 1. No Anthropic API key was available during the build
`GATEWAY_ANTHROPIC_API_KEY` was empty, so `.env` was written with `UPSTREAM=mock`. Everything (tests, traffic, eval, playground, screenshots) runs against the mock upstream.
- **Recommendation:** set the key later, put it in `.env` as `ANTHROPIC_API_KEY=...`, flip `UPSTREAM=anthropic`, and run `make eval-cost` (≤100 requests) to verify the computed cost-per-1K against a real run.
- **Meanwhile:** cost numbers are computed from token counts × configured prices.

## 2. The classifier has a few false-positive patterns
Seen during M2: "My SSN is …, can you remember it for later?" → p=0.99, "Remember my phone number for later." → p=1.0, and the short command "Log me please" → p=0.97. The model seems to treat memory/persistence instructions and terse commands as injections.
- **Recommendation:** keep the 0.90 threshold for the demo and report the real false-positive rate from the eval (M4). If FPR on benign prompts is too high, offer a "review" action (allow, but flag) for scores between 0.9 and 0.99 instead of blocking.
- **Meanwhile:** documented here and in the eval; tests use realistic prompts.

