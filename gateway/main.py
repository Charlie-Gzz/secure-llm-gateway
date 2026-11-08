"""Bulwark gateway: FastAPI app exposing an OpenAI-compatible chat endpoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from gateway.config import PRODUCT_NAME, Policy, get_settings
from gateway.pipeline import Pipeline
from gateway.schemas import ChatRequest
from gateway.store import RequestStore
from gateway.upstreams import UpstreamError, build_upstream

log = logging.getLogger("bulwark")


def build_pipeline(settings, policy: Policy) -> Pipeline:
    return Pipeline(policy=policy, upstream=build_upstream(settings, policy))


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
