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

## 3. Should the rules layer block, or only observe?
The eval shows rules add very little recall on top of the classifier (v1: 83.9% → 84.3%), but rules caused most false positives on the near-miss benign set. They're still valuable as a ~0.1 ms first line that skips the 30–40 ms classifier for obvious attacks, and they make the "decided by" explanation human-readable.
- **Recommendation:** keep rules blocking for the demo (it makes the playground explainable), but present the ablation honestly: "the classifier does the heavy lifting; rules are a cheap, explainable fast path".
- **Meanwhile:** `policy.yaml` supports `action: allow` for rules if you want observe-only.

## 4. Known detection gaps worth calling out publicly
- Non-English attacks (the classifier is English-only; ~40% of deepset misses are German).
- Some indirect injections inside documents (e.g. an email asking to forward the inbox scored 0.20).
- Jailbreak-style role-play (the model card says it doesn't target jailbreaks; in-the-wild jailbreak recall is ~70%).
- **Recommendation:** list these as limitations in the README; they're honest and make the project more credible. A stretch fix is the LLM-as-judge layer for borderline scores (Section 9).

## 5. Is p95 latency good enough, or worth a speed pass?
Guards add **39 ms at p50** but **329 ms at p95** on benign prompts, because the DeBERTa classifier's cost grows steeply with prompt length (~490 ms at 400 tokens on this laptop). Thread tuning made no difference.
- **Recommendation:** present p50 + p95 honestly (the chart already does). If you want a better p95 story, the cheapest next step is trying ONNX Runtime's transformer optimizer or a smaller distilled model, re-running `make eval` to confirm accuracy holds (the int8 lesson).
- **Meanwhile:** nothing changed; numbers are what they are.

