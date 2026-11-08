"""Bulwark gateway: FastAPI app exposing an OpenAI-compatible chat endpoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from gateway import telemetry
from gateway.config import PRODUCT_NAME, ROOT, Policy, get_settings
from gateway.guards.classifier import ClassifierGuard
from gateway.guards.pii import PiiGuard
from gateway.guards.rules import RulesGuard
from gateway.limits import Limits, start_of_day_utc
from gateway.pipeline import Pipeline
from gateway.schemas import ChatRequest
from gateway.store import RequestStore
from gateway.streaming import sse
from gateway.upstreams import UpstreamError, build_upstream

log = logging.getLogger("bulwark")


def build_pipeline(settings, policy: Policy) -> Pipeline:
    """Load every guard once. A guard that fails to load is disabled, not fatal."""
    rules = RulesGuard() if policy.guards.rules.enabled else None

    classifier = None
    if settings.classifier_enabled and policy.guards.classifier.enabled:
        try:
            cfg = policy.guards.classifier
            classifier = ClassifierGuard(
                settings.model_dir / "prompt-injection", cfg.threshold, cfg.max_length
            )
            classifier.score("warm up")  # first ONNX run allocates; keep it off the request path
        except Exception as e:
            log.warning("Classifier disabled (rules only): %s", e)

    pii = None
    if settings.pii_enabled and (
        policy.guards.pii_input.enabled or policy.guards.pii_output.enabled
    ):
        try:
            pii = PiiGuard()
            pii.redact("warm up 555-0100", ["PHONE_NUMBER"], 0.4)
        except Exception as e:
            log.warning("PII guard disabled: %s", e)

    return Pipeline(
        policy=policy,
        upstream=build_upstream(settings, policy),
        rules=rules,
        classifier=classifier,
        pii=pii,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    policy = Policy.load(settings.policy_path)
    app.state.settings = settings
    app.state.policy = policy
    app.state.pipeline = build_pipeline(settings, policy)
    app.state.store = RequestStore(settings.db_path)
    app.state.limits = Limits.from_env()
    log.info("%s ready: upstream=%s", PRODUCT_NAME, app.state.pipeline.upstream.name)
    yield
    app.state.store.close()


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
telemetry.setup_tracing(get_settings().otel_endpoint)
app = FastAPI(title=f"{PRODUCT_NAME} LLM Gateway", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(
    app, excluded_urls="healthz,metrics", exclude_spans=["receive", "send"]
)


app.mount("/ui", StaticFiles(directory=ROOT / "ui"), name="ui")


@app.get("/", include_in_schema=False)
async def playground():
    return FileResponse(ROOT / "ui" / "index.html")


@app.get("/config")
async def public_config(request: Request):
    """What the playground needs to render its header and links."""
    settings = request.app.state.settings
    pipeline: Pipeline = request.app.state.pipeline
    return {
        "product": PRODUCT_NAME,
        "upstream": pipeline.upstream.name,
        "model": pipeline.upstream.model,
        "classifier_threshold": request.app.state.policy.guards.classifier.threshold,
        "jaeger_url": settings.jaeger_url,
        "grafana_url": settings.grafana_url,
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
async def healthz(request: Request):
    pipeline: Pipeline = request.app.state.pipeline
    return {
        "status": "ok",
        "product": PRODUCT_NAME,
        "upstream": pipeline.upstream.name,
        "model": pipeline.upstream.model,
        "guards": {
            "rules": pipeline.rules is not None,
            "classifier": pipeline.classifier is not None,
            "pii": pipeline.pii is not None,
        },
    }


@app.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest, request: Request):
    limits: Limits = request.app.state.limits
    limits.check_rate(request.client.host if request.client else "unknown")
    limits.check_size("".join(m.text() for m in body.messages))
    limits.check_spend(request.app.state.store.summary(since_ts=start_of_day_utc())["cost_usd"])
    pipeline: Pipeline = request.app.state.pipeline
    if body.stream:
        return await _stream(body, pipeline, request.app.state.store)
    try:
        completion, info = await pipeline.run(body)
    except UpstreamError as e:
        raise HTTPException(502, str(e)) from e

    request.app.state.store.record(info)
    completion["gateway"] = info.model_dump()
    return JSONResponse(completion, headers={"X-Gateway-Verdict": info.verdict})


async def _stream(body: ChatRequest, pipeline: Pipeline, store: RequestStore):
    """Server-sent events in OpenAI's format. Input guards finish before the first byte, so a
    blocked prompt never reaches the model and the verdict header is known. The header holds
    the input verdict; the final chunk's `gateway` field has the full one (incl. output PII)."""
    prepared = await pipeline.prepare(body)
    include_usage = bool((body.stream_options or {}).get("include_usage"))

    async def events():
        async for event in pipeline.stream(prepared, include_usage, on_done=store.record):
            yield sse(event)

    headers = {
        "X-Gateway-Verdict": prepared.input_verdict,
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # stop reverse proxies from buffering the stream
    }
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)
