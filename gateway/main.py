"""Bulwark gateway: FastAPI app exposing an OpenAI-compatible chat endpoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from gateway.config import PRODUCT_NAME, Policy, get_settings
from gateway.guards.classifier import ClassifierGuard
from gateway.guards.pii import PiiGuard
from gateway.guards.rules import RulesGuard
from gateway.pipeline import Pipeline
from gateway.schemas import ChatRequest
from gateway.store import RequestStore
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
    log.info("%s ready: upstream=%s", PRODUCT_NAME, app.state.pipeline.upstream.name)
    yield
    app.state.store.close()


app = FastAPI(title=f"{PRODUCT_NAME} LLM Gateway", version="0.1.0", lifespan=lifespan)


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
    if body.stream:
        raise HTTPException(400, "Streaming is not supported by this gateway yet.")
    pipeline: Pipeline = request.app.state.pipeline
    try:
        completion, info = await pipeline.run(body)
    except UpstreamError as e:
        raise HTTPException(502, str(e)) from e

    request.app.state.store.record(info)
    completion["gateway"] = info.model_dump()
    return JSONResponse(completion, headers={"X-Gateway-Verdict": info.verdict})
