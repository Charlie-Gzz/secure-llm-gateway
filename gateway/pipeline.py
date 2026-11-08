"""The request pipeline: Rules -> Classifier -> PII (input) -> LLM -> PII (output).

Each stage is recorded as a `Step` (and an OpenTelemetry span) so clients, the playground,
and Jaeger can all see what happened, how long it took, and which layer made the call.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from gateway import telemetry
from gateway.config import Policy, guard_workers
from gateway.cost import cost_usd
from gateway.schemas import ChatRequest, GatewayInfo, Step, Usage
from gateway.upstreams import Upstream

STEP_ORDER = ("rules", "classifier", "pii_input", "llm", "pii_output")
UNTRUSTED_ROLES = {"user", "tool"}  # end-user text; system/developer prompts are trusted


@dataclass
class StepRecord:
    """Filled in by the code inside a `_step` block."""

    status: str = "pass"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Run:
    """Everything collected while one request moves through the pipeline."""

    request_id: str
    started: float
    trace_id: str | None = None
    steps: list[Step] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    redactions: list[dict[str, Any]] = field(default_factory=list)
    prompt_redacted: str | None = None

    def redacted(self, where: str, hits: list[dict]) -> dict[str, int]:
        counts = _count(hits)
        self.redactions += [{"where": where, "entity": e, "count": n} for e, n in counts.items()]
        return counts


class Pipeline:
    def __init__(self, policy: Policy, upstream: Upstream, rules=None, classifier=None, pii=None):
        self.policy = policy
        self.upstream = upstream
        self.rules = rules
        self.classifier = classifier
        self.pii = pii
        # CPU-bound guards (classifier, Presidio) run in a small thread pool so they don't block
        # the event loop while other requests wait on the upstream. Sizing: config.guard_workers.
        self._pool = ThreadPoolExecutor(guard_workers(), thread_name_prefix="guard")

    async def _offload(self, fn, *args):
        """Run a CPU-bound guard call in the guard pool (keeps contextvars, e.g. the trace)."""
        ctx = contextvars.copy_context()
        call = functools.partial(ctx.run, fn, *args)
        return await asyncio.get_running_loop().run_in_executor(self._pool, call)

    async def run(self, req: ChatRequest) -> tuple[dict[str, Any], GatewayInfo]:
        run = Run(request_id=f"req_{uuid.uuid4().hex[:16]}", started=time.perf_counter())
        with telemetry.span("gateway.request", **{"bulwark.request_id": run.request_id}) as root:
            run.trace_id = telemetry.current_trace_id()
            body, info = await self._process(req, run)
            telemetry.annotate(root, info)
        telemetry.record_metrics(info)
        return body, info

    async def _process(self, req: ChatRequest, run: Run) -> tuple[dict[str, Any], GatewayInfo]:
        guards = self.policy.guards
        messages = [m.model_copy() for m in req.messages]
        untrusted = "\n".join(m.text() for m in messages if m.role in UNTRUSTED_ROLES)

        # 1-2. Injection guards: cheap rules first, then the classifier.
        for name, guard in (("rules", self.rules), ("classifier", self.classifier)):
            cfg = getattr(guards, name)
            if guard is None or not cfg.enabled:
                continue
            with self._step(run, name) as rec:
                # Rules take ~0.1 ms: a thread hop would cost more than it saves.
                if name == "rules":
                    result = guard.check(untrusted)
                else:
                    result = await self._offload(guard.check, untrusted)
                blocking = result.status == "block" and cfg.action == "block"
                rec.status = "block" if blocking else "pass"
                rec.detail = {**result.detail, "reason": result.reason}
                if result.score is not None:
                    run.scores[name] = result.score
                    rec.detail["score"] = round(result.score, 4)
            if blocking:
                return self._blocked(run, name, result.reason)

        # 3. PII on the prompt: redact in place before anything leaves the gateway.
        if self.pii and guards.pii_input.enabled:
            cfg = guards.pii_input
            with self._step(run, "pii_input") as rec:
                found: list[dict] = []
                for m in messages:
                    if m.role in UNTRUSTED_ROLES and m.text():
                        clean, hits = await self._offload(
                            self.pii.redact, m.text(), cfg.entities, cfg.min_score
                        )
                        if hits:
                            m.content, found = clean, found + hits
                if found:
                    rec.status = "block" if cfg.action == "block" else "redact"
                rec.detail = {"entities": run.redacted("input", found)}
                if found:
                    last_user = next((m for m in reversed(messages) if m.role == "user"), None)
                    run.prompt_redacted = last_user.text() if last_user else None
            if rec.status == "block":
                return self._blocked(run, "pii_input", "Prompt contains PII")

        # 4. Upstream LLM.
        max_tokens = min(
            req.max_completion_tokens or req.max_tokens or self.policy.upstream.max_tokens,
            self.policy.upstream.max_tokens,
        )
        with self._step(run, "llm") as rec:
            result = await self.upstream.complete(messages, max_tokens)
            rec.detail = {"upstream": self.upstream.name, "model": result.model}
        answer = result.text

        # 5. PII on the answer.
        if self.pii and guards.pii_output.enabled:
            cfg = guards.pii_output
            with self._step(run, "pii_output") as rec:
                answer, hits = await self._offload(
                    self.pii.redact, answer, cfg.entities, cfg.min_score
                )
                rec.status = "redact" if hits else "pass"
                rec.detail = {"entities": run.redacted("output", hits)}

        usage = Usage(
            prompt_tokens=result.input_tokens,
            completion_tokens=result.output_tokens,
            total_tokens=result.input_tokens + result.output_tokens,
        )
        redactor = next((s.name for s in run.steps if s.status == "redact"), None)
        info = self._info(
            run,
            verdict="redacted" if run.redactions else "allowed",
            decided_by=redactor,
            reason="PII redacted" if run.redactions else None,
            usage=usage,
            model=result.model,
        )
        body = _completion(run.request_id, result.model, answer, result.finish_reason, usage)
        return body, info

    # -- helpers ---------------------------------------------------------------------

    @contextmanager
    def _step(self, run: Run, name: str):
        """Time a step, wrap it in a span, and append it to the run."""
        rec = StepRecord()
        t0 = time.perf_counter()
        with telemetry.span(f"step.{name}") as s:
            yield rec
            s.set_attribute("bulwark.status", rec.status)
            for key, value in rec.detail.items():
                if isinstance(value, str | int | float | bool):
                    s.set_attribute(f"bulwark.{key}", value)
        run.steps.append(Step(name=name, status=rec.status, latency_ms=_ms(t0), detail=rec.detail))

    def _blocked(self, run: Run, layer: str, reason: str | None):
        info = self._info(run, verdict="blocked", decided_by=layer, reason=reason)
        body = _completion(
            run.request_id, info.model, self.policy.blocked_message, "content_filter", Usage()
        )
        return body, info

    def _info(self, run: Run, *, usage: Usage | None = None, model: str | None = None, **kw):
        usage = usage or Usage()
        model = model or self.upstream.model
        # Show every stage in a fixed order; ones that never ran are "skip".
        ran = {s.name: s for s in run.steps}
        steps = [ran.get(n) or Step(name=n, status="skip", latency_ms=0) for n in STEP_ORDER]
        latency = {s.name: s.latency_ms for s in run.steps}
        latency["guards"] = round(sum(v for k, v in latency.items() if k != "llm"), 3)
        latency["total"] = _ms(run.started)
        return GatewayInfo(
            request_id=run.request_id,
            steps=steps,
            scores=run.scores,
            redactions=run.redactions,
            prompt_redacted=run.prompt_redacted,
            latency_ms=latency,
            usage=usage,
            cost_usd=cost_usd(
                self.policy.pricing, model, usage.prompt_tokens, usage.completion_tokens
            ),
            upstream=self.upstream.name,
            model=model,
            trace_id=run.trace_id,
            **kw,
        )


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 3)


def _count(hits: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for h in hits:
        counts[h["entity"]] = counts.get(h["entity"], 0) + 1
    return counts


def _completion(request_id: str, model: str, text: str, finish: str, usage: Usage) -> dict:
    """An OpenAI `chat.completion` object."""
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
