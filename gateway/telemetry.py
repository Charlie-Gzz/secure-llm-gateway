"""Observability: OpenTelemetry traces (one span per pipeline step) and Prometheus metrics.

Tracing is exported over OTLP only when OTEL_EXPORTER_OTLP_ENDPOINT is set, so local runs
and tests stay quiet. Metrics are always collected and served at /metrics.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram

from gateway.schemas import GatewayInfo

SERVICE_NAME = "bulwark-gateway"
tracer = trace.get_tracer("bulwark")

# -- Prometheus metrics ------------------------------------------------------------------

LATENCY_BUCKETS = (0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

REQUESTS = Counter("bulwark_requests_total", "Chat requests by verdict", ["verdict", "upstream"])
BLOCKS = Counter(
    "bulwark_blocks_total", "Blocked requests by layer and reason", ["layer", "reason"]
)
REDACTIONS = Counter("bulwark_redactions_total", "PII entities redacted", ["where", "entity"])
STEP_LATENCY = Histogram(
    "bulwark_step_latency_seconds", "Latency per pipeline step", ["step"], buckets=LATENCY_BUCKETS
)
GUARD_OVERHEAD = Histogram(
    "bulwark_guard_overhead_seconds",
    "Latency added by all guards combined (excludes the LLM call)",
    buckets=LATENCY_BUCKETS,
)
REQUEST_LATENCY = Histogram(
    "bulwark_request_latency_seconds", "End-to-end gateway latency", buckets=LATENCY_BUCKETS
)
TOKENS = Counter("bulwark_tokens_total", "Tokens processed", ["direction", "model"])
COST = Counter("bulwark_cost_usd_total", "Upstream spend in USD", ["model"])
CLASSIFIER_SCORE = Histogram(
    "bulwark_classifier_score",
    "Distribution of classifier injection probabilities",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0),
)


def record_metrics(info: GatewayInfo) -> None:
    REQUESTS.labels(info.verdict, info.upstream).inc()
    if info.verdict == "blocked":
        BLOCKS.labels(info.decided_by or "unknown", _reason_label(info)).inc()
    for r in info.redactions:
        REDACTIONS.labels(r["where"], r["entity"]).inc(r["count"])
    for step in info.steps:
        if step.status != "skip":
            STEP_LATENCY.labels(step.name).observe(step.latency_ms / 1000)
    GUARD_OVERHEAD.observe(info.latency_ms.get("guards", 0) / 1000)
    REQUEST_LATENCY.observe(info.latency_ms.get("total", 0) / 1000)
    if "classifier" in info.scores:
        CLASSIFIER_SCORE.observe(info.scores["classifier"])
    TOKENS.labels("input", info.model).inc(info.usage.prompt_tokens)
    TOKENS.labels("output", info.model).inc(info.usage.completion_tokens)
    COST.labels(info.model).inc(info.cost_usd)


def _reason_label(info: GatewayInfo) -> str:
    """Low-cardinality reason: the rule id for rules, the layer name otherwise."""
    for step in info.steps:
        if step.name == info.decided_by and step.name == "rules":
            matched = step.detail.get("matched") or ["unknown"]
            return matched[0]
    return info.decided_by or "unknown"


# -- Tracing ---------------------------------------------------------------------------


def setup_tracing(otlp_endpoint: str | None) -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
        )
    trace.set_tracer_provider(provider)


@contextmanager
def span(name: str, **attributes: Any):
    with tracer.start_as_current_span(name) as s:
        for key, value in attributes.items():
            s.set_attribute(key, value)
        yield s


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def annotate(s, info: GatewayInfo) -> None:
    """Attach the final verdict to the request span so it is searchable in Jaeger."""
    s.set_attribute("bulwark.verdict", info.verdict)
    s.set_attribute("bulwark.decided_by", info.decided_by or "")
    s.set_attribute("bulwark.cost_usd", info.cost_usd)
    s.set_attribute("bulwark.tokens.input", info.usage.prompt_tokens)
    s.set_attribute("bulwark.tokens.output", info.usage.completion_tokens)
    for name, score in info.scores.items():
        s.set_attribute(f"bulwark.score.{name}", score)
