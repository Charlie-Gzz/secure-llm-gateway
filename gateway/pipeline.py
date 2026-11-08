"""The request pipeline: Rules -> Classifier -> PII (input) -> LLM -> PII (output).

Each stage is recorded as a `Step` so clients (and the playground) can see exactly
what happened, how long it took, and which layer made the final call.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from gateway import telemetry
from gateway.config import Policy
from gateway.cost import cost_usd
from gateway.guards.base import GuardResult
from gateway.schemas import ChatMessage, ChatRequest, GatewayInfo, Step, Usage
from gateway.upstreams import Upstream

# Roles whose text comes from the end user (untrusted) and must be screened.
UNTRUSTED_ROLES = {"user", "tool"}


class Pipeline:
    def __init__(
        self,
        policy: Policy,
        upstream: Upstream,
        rules=None,
        classifier=None,
        pii=None,
    ):
        self.policy = policy
        self.upstream = upstream
        self.rules = rules
        self.classifier = classifier
        self.pii = pii

    async def run(self, req: ChatRequest) -> tuple[dict[str, Any], GatewayInfo]:
        request_id = f"req_{uuid.uuid4().hex[:16]}"
        started = time.perf_counter()
        steps: list[Step] = []
        scores: dict[str, float] = {}
        redactions: list[dict[str, Any]] = []
        messages = [m.model_copy() for m in req.messages]
        untrusted = "\n".join(m.text() for m in messages if m.role in UNTRUSTED_ROLES)

        with telemetry.span("gateway.request", request_id=request_id):
            trace_id = telemetry.current_trace_id()

            # 1-2. Injection guards: rules first (cheap), then the classifier.
            for name, guard in (("rules", self.rules), ("classifier", self.classifier)):
                result = self._run_guard(name, guard, untrusted, steps)
                if result and result.score is not None:
                    scores[name] = result.score
                if result and result.status == "block":
                    return self._blocked(
                        request_id,
                        name,
                        result.reason,
                        steps,
                        scores,
                        redactions,
                        started,
                        trace_id,
                    )

            # 3. PII on the prompt.
            pii_in = self.policy.guards.pii_input
            if self.pii and pii_in.enabled:
                t0 = time.perf_counter()
                with telemetry.span("guard.pii_input"):
                    found = []
                    for m in messages:
                        if m.role in UNTRUSTED_ROLES and m.text():
                            clean, hits = self.pii.redact(
                                m.text(), pii_in.entities, pii_in.min_score
                            )
                            if hits:
                                m.content = clean
                                found.extend(hits)
                status = ("block" if pii_in.action == "block" else "redact") if found else "pass"
                steps.append(
                    Step(
                        name="pii_input",
                        status=status,
                        latency_ms=_ms(t0),
                        detail={"entities": _count(found)},
                    )
                )
                redactions += [
                    {"where": "input", "entity": e, "count": n} for e, n in _count(found).items()
                ]
                if status == "block":
                    return self._blocked(
                        request_id,
                        "pii_input",
                        "Prompt contains PII",
                        steps,
                        scores,
                        redactions,
                        started,
                        trace_id,
                    )
            else:
                steps.append(Step(name="pii_input", status="skip", latency_ms=0))

            # 4. Upstream LLM.
            max_tokens = min(
                req.max_completion_tokens or req.max_tokens or 10**9,
                self.policy.upstream.max_tokens,
            )
            t0 = time.perf_counter()
            with telemetry.span("upstream.llm", upstream=self.upstream.name):
                result = await self.upstream.complete(messages, max_tokens)
            steps.append(
                Step(
                    name="llm",
                    status="pass",
                    latency_ms=_ms(t0),
                    detail={"upstream": self.upstream.name, "model": result.model},
                )
            )
            answer = result.text

            # 5. PII on the answer.
            pii_out = self.policy.guards.pii_output
            if self.pii and pii_out.enabled:
                t0 = time.perf_counter()
                with telemetry.span("guard.pii_output"):
                    answer, hits = self.pii.redact(answer, pii_out.entities, pii_out.min_score)
                steps.append(
                    Step(
                        name="pii_output",
                        status="redact" if hits else "pass",
                        latency_ms=_ms(t0),
                        detail={"entities": _count(hits)},
                    )
                )
                redactions += [
                    {"where": "output", "entity": e, "count": n} for e, n in _count(hits).items()
                ]
            else:
                steps.append(Step(name="pii_output", status="skip", latency_ms=0))

        usage = Usage(
            prompt_tokens=result.input_tokens,
            completion_tokens=result.output_tokens,
            total_tokens=result.input_tokens + result.output_tokens,
        )
        info = GatewayInfo(
            request_id=request_id,
            verdict="redacted" if redactions else "allowed",
            decided_by=_first_redactor(steps),
            reason="PII redacted" if redactions else None,
            steps=steps,
            scores=scores,
            redactions=redactions,
            latency_ms=_latencies(steps, started),
            usage=usage,
            cost_usd=cost_usd(
                self.policy.pricing, result.model, usage.prompt_tokens, usage.completion_tokens
            ),
            upstream=self.upstream.name,
            model=result.model,
            trace_id=trace_id,
        )
        return _completion(request_id, result.model, answer, result.finish_reason, usage), info

    # -- helpers ---------------------------------------------------------------------

    def _run_guard(self, name: str, guard, text: str, steps: list[Step]) -> GuardResult | None:
        cfg = getattr(self.policy.guards, name)
        if guard is None or not cfg.enabled:
            steps.append(Step(name=name, status="skip", latency_ms=0))
            return None
        t0 = time.perf_counter()
        with telemetry.span(f"guard.{name}"):
            result = guard.check(text)
        if result.status == "block" and cfg.action != "block":
            result.status = "pass"  # policy says observe only
        detail = dict(result.detail)
        if result.reason:
            detail["reason"] = result.reason
        if result.score is not None:
            detail["score"] = round(result.score, 4)
        steps.append(Step(name=name, status=result.status, latency_ms=_ms(t0), detail=detail))
        return result

    def _blocked(self, request_id, layer, reason, steps, scores, redactions, started, trace_id):
        done = {s.name for s in steps}
        for name in ("rules", "classifier", "pii_input", "llm", "pii_output"):
            if name not in done:
                steps.append(Step(name=name, status="skip", latency_ms=0))
        info = GatewayInfo(
            request_id=request_id,
            verdict="blocked",
            decided_by=layer,
            reason=reason,
            steps=steps,
            scores=scores,
            redactions=redactions,
            latency_ms=_latencies(steps, started),
            upstream=self.upstream.name,
            model=self.upstream.model,
            trace_id=trace_id,
        )
        body = _completion(
            request_id, self.upstream.model, self.policy.blocked_message, "content_filter", Usage()
        )
        return body, info


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 3)


def _count(hits: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for h in hits:
        counts[h["entity"]] = counts.get(h["entity"], 0) + 1
    return counts


def _latencies(steps: list[Step], started: float) -> dict[str, float]:
    out = {s.name: s.latency_ms for s in steps if s.status != "skip"}
    out["guards"] = round(sum(v for k, v in out.items() if k != "llm"), 3)
    out["total"] = _ms(started)
    return out


def _first_redactor(steps: list[Step]) -> str | None:
    return next((s.name for s in steps if s.status == "redact"), None)


def _completion(request_id: str, model: str, text: str, finish: str, usage: Usage) -> dict:
    return {
        "id": f"chatcmpl-{request_id.removeprefix('req_')}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish,
            }
        ],
        "usage": usage.model_dump(),
    }


__all__ = ["Pipeline", "ChatMessage"]
