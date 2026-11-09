# Questions for Charlie

Each question includes my recommendation and what I did in the meantime.

## 1. ~~API key~~ (resolved 2026-11-08)
Charlie decided the project stays on the mock upstream by default: it's for learning and showcasing, not for offering as a service. The docs now present "runs offline, no key needed" as a feature. The Claude upstream remains implemented, and `make eval-cost` stays available as an optional check of the cost estimates.

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
Guards add **36 ms at p50** but **294 ms at p95** on benign prompts, because the DeBERTa classifier's cost grows steeply with prompt length (~490 ms at 400 tokens on this laptop). Thread tuning doesn't change single-request latency (4 threads = all cores), though it did double throughput under load (see the load test).
- **Recommendation:** present p50 + p95 honestly (the chart already does). If you want a better p95 story, the cheapest next step is trying ONNX Runtime's transformer optimizer or a smaller distilled model, re-running `make eval` to confirm accuracy holds (the int8 lesson).
- **Meanwhile:** nothing changed; numbers are what they are.

## 6. ~~Should the judge read more traffic?~~ (resolved 2026-11-08)
**Decision (Charlie):** keep the recommended borderline-only setting. The README tells the "confidently wrong" story, and the options below stay documented for later.

On borderline scores only (the setting I fixed before seeing results), the Qwen3Guard judge sees 1% of traffic and lifts recall 84.3% → 84.8%. Run on **every** prompt the classifier allows, it reaches **86.9% with no new false positives**, but then ~55% of requests wait ~1 s for it on CPU.
- **Recommendation:** keep the borderline setting as the default and tell the story ("the classifier is confidently wrong, so uncertainty-based escalation has a ceiling"). If you want the +2.6 pts, the two cheap paths are (a) run the judge *in parallel* with the upstream call and drop the answer if it flags (latency hidden behind a real LLM's ~1–3 s; costs tokens on blocked requests), or (b) cache the judge's ~300-token policy prefix (KV cache) so each call only processes the user text, likely several times faster.
- **Meanwhile:** setting `guards.judge.band: [0.0, 0.90]` in `policy.yaml` turns on the "all allowed traffic" mode today.
