"""Generate the Bulwark Grafana dashboard JSON (observability/grafana/dashboards/bulwark.json).

Panels are written in Python so the dashboard stays reviewable; Grafana loads the generated
JSON via file provisioning. Re-run after editing:
    uv run python observability/grafana/build_dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "dashboards" / "bulwark.json"
DS = {"type": "prometheus", "uid": "prometheus"}

GREEN, AMBER, RED, CYAN = "#22C55E", "#F59E0B", "#EF4444", "#38BDF8"
MUTED, VIOLET, PINK = "#9CA3AF", "#A78BFA", "#F472B6"
VERDICT_COLORS = {"allowed": GREEN, "redacted": AMBER, "blocked": RED}
STEP_COLORS = {
    "rules": VIOLET,
    "classifier": CYAN,
    "pii_input": AMBER,
    "pii_output": PINK,
    "llm": MUTED,
}

_next_id = iter(range(1, 1000))


def target(expr: str, legend: str = "", instant: bool = False, fmt: str | None = None) -> dict:
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": "A"}
    if instant:
        t["instant"], t["range"] = True, False
    if fmt:
        t["format"] = fmt
    return t


def color_overrides(colors: dict[str, str]) -> list[dict]:
    return [
        {
            "matcher": {"id": "byName", "options": name},
            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}],
        }
        for name, color in colors.items()
    ]


def stat(title, expr, x, unit, color, decimals=None, desc=""):
    defaults = {"unit": unit, "color": {"mode": "fixed", "fixedColor": color}}
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "id": next(_next_id),
        "type": "stat",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": {"x": x, "y": 0, "w": 6, "h": 5},
        "targets": [target(expr, instant=True)],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "colorMode": "value",
            "graphMode": "none",
            "textMode": "value",
            "justifyMode": "center",
            "orientation": "auto",
            "text": {"valueSize": 56},
        },
    }


def timeseries(title, targets, pos, unit="short", stack=False, overrides=None, bars=False, desc=""):
    custom = {
        "drawStyle": "bars" if bars else "line",
        "lineWidth": 2,
        "fillOpacity": 70 if bars else 18,
        "gradientMode": "opacity",
        "showPoints": "never",
        "spanNulls": True,
        "stacking": {"mode": "normal" if stack else "none", "group": "A"},
        "axisBorderShow": False,
    }
    return {
        "id": next(_next_id),
        "type": "timeseries",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": pos,
        "targets": targets,
        "fieldConfig": {
            "defaults": {"unit": unit, "custom": custom, "color": {"mode": "palette-classic"}},
            "overrides": overrides or [],
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }


def bargauge(title, expr, legend, pos, unit="short", color=CYAN, fmt=None, desc=""):
    return {
        "id": next(_next_id),
        "type": "bargauge",
        "title": title,
        "description": desc,
        "datasource": DS,
        "gridPos": pos,
        "targets": [target(expr, legend, instant=True, fmt=fmt)],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "min": 0,
                "decimals": 0,
                "color": {"mode": "fixed", "fixedColor": color},
            },
            "overrides": [],
        },
        "options": {
            "orientation": "horizontal",
            "displayMode": "gradient",
            "showUnfilled": True,
            "valueMode": "color",
            "namePlacement": "left",
            "sizing": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
    }


def build() -> dict:
    rng = "[$__range]"
    panels = [
        stat(
            "Requests",
            f"sum(increase(bulwark_requests_total{rng}))",
            0,
            "short",
            CYAN,
            0,
            "Chat requests in the selected time range",
        ),
        stat(
            "Block rate",
            f'sum(increase(bulwark_requests_total{{verdict="blocked"}}{rng})) '
            f"/ sum(increase(bulwark_requests_total{rng}))",
            6,
            "percentunit",
            RED,
            1,
            "Share of requests blocked by any guard",
        ),
        stat(
            "p95 added latency",
            f"histogram_quantile(0.95, sum by (le) "
            f"(increase(bulwark_guard_overhead_seconds_bucket{rng})))",
            12,
            "s",
            AMBER,
            None,
            "95th percentile latency added by all guards (excludes LLM)",
        ),
        stat(
            "Cost today",
            "sum(increase(bulwark_cost_usd_total[24h]))",
            18,
            "currencyUSD",
            GREEN,
            4,
            "Upstream LLM spend over the last 24 hours",
        ),
        timeseries(
            "Requests per second by verdict",
            [
                target(
                    "sum by (verdict) (rate(bulwark_requests_total[$__rate_interval]))",
                    "{{verdict}}",
                )
            ],
            {"x": 0, "y": 5, "w": 12, "h": 9},
            "reqps",
            stack=True,
            bars=True,
            overrides=color_overrides(VERDICT_COLORS),
        ),
        timeseries(
            "Blocks by layer and reason",
            [
                target(
                    "sum by (layer, reason) (rate(bulwark_blocks_total[$__rate_interval]))",
                    "{{layer}} · {{reason}}",
                )
            ],
            {"x": 12, "y": 5, "w": 12, "h": 9},
            "reqps",
            stack=True,
        ),
        timeseries(
            "p95 latency per pipeline step",
            [
                target(
                    "histogram_quantile(0.95, sum by (le, step) "
                    "(rate(bulwark_step_latency_seconds_bucket[$__rate_interval])))",
                    "{{step}}",
                )
            ],
            {"x": 0, "y": 14, "w": 12, "h": 9},
            "s",
            overrides=color_overrides(STEP_COLORS),
            desc="Classifier and PII dominate guard cost; the LLM call dominates overall.",
        ),
        timeseries(
            "Added latency: guards p50 / p95",
            [
                target(
                    "histogram_quantile(0.50, sum by (le) "
                    "(rate(bulwark_guard_overhead_seconds_bucket[$__rate_interval])))",
                    "p50",
                ),
                target(
                    "histogram_quantile(0.95, sum by (le) "
                    "(rate(bulwark_guard_overhead_seconds_bucket[$__rate_interval])))",
                    "p95",
                ),
            ],
            {"x": 12, "y": 14, "w": 12, "h": 9},
            "s",
            overrides=color_overrides({"p50": CYAN, "p95": AMBER}),
        ),
        bargauge(
            "Classifier score distribution",
            f'sum by (le) (increase(bulwark_classifier_score_bucket{{le!="+Inf"}}{rng}))',
            "≤ {{le}}",
            {"x": 0, "y": 23, "w": 8, "h": 9},
            color=CYAN,
            fmt="heatmap",
            desc="Cumulative count of injection probabilities. Scores are near-binary.",
        ),
        bargauge(
            "PII redactions by entity",
            f"sum by (where, entity) (increase(bulwark_redactions_total{rng}))",
            "{{entity}} ({{where}})",
            {"x": 8, "y": 23, "w": 8, "h": 9},
            color=AMBER,
        ),
        timeseries(
            "Tokens per second",
            [
                target(
                    "sum by (direction) (rate(bulwark_tokens_total[$__rate_interval]))",
                    "{{direction}}",
                )
            ],
            {"x": 16, "y": 23, "w": 8, "h": 9},
            "short",
            overrides=color_overrides({"input": CYAN, "output": GREEN}),
        ),
    ]
    for p in panels:
        p["targets"] = [{**t, "refId": chr(65 + i)} for i, t in enumerate(p["targets"])]

    return {
        "uid": "bulwark",
        "title": "Bulwark · LLM Gateway",
        "tags": ["bulwark", "llm-security"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "graphTooltip": 1,
        "refresh": "5s",
        "style": "dark",
        "time": {"from": "now-15m", "to": "now"},
        "panels": panels,
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
