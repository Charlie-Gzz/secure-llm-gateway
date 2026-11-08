"""Turn eval/results/results.json into portfolio charts (PNG 1600px + SVG) and one Plotly page.

    uv run python scripts/make_charts.py      (part of `make assets`)

Style: Bulwark dark theme, one axis per panel, takeaway titles, selective direct labels.
Series colors were checked with a CVD validator against the dark panel color (#131A26):
cyan / orange / violet pass lightness, chroma, colorblind separation, and contrast checks.
Status colors (green/amber/red) are reserved for verdicts and not used for series.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results" / "results.json"
LOAD_TEST = ROOT / "eval" / "results" / "load_test.json"
OUT = ROOT / "assets" / "charts"

BG, PANEL, LINE, INK, MUTED = "#0B0F17", "#131A26", "#1F2937", "#E5E7EB", "#9CA3AF"
CYAN, ORANGE, VIOLET = "#0C93CF", "#D95926", "#9085E9"
CONFIG_COLORS = {"rules only": VIOLET, "classifier only": ORANGE, "rules + classifier": CYAN}
CONFIGS = list(CONFIG_COLORS)
SOURCE_LABELS = {
    "deepset": "deepset",
    "gandalf": "Gandalf (Lakera)",
    "jailbreak_wild": "In-the-wild jailbreaks",
    "holdout": "Hand-written holdout",
}


def setup_style() -> str:
    """Register bundled Inter / JetBrains Mono if present; fall back to the default sans."""
    family = "sans-serif"
    for ttf in (ROOT / "assets" / "fonts").glob("*.ttf"):
        font_manager.fontManager.addfont(str(ttf))
        if ttf.name.startswith("Inter"):
            family = "Inter"
    plt.rcParams.update(
        {
            "font.family": family,
            "font.size": 13,
            "text.color": INK,
            "figure.facecolor": BG,
            "axes.facecolor": PANEL,
            "savefig.facecolor": BG,
            "axes.edgecolor": LINE,
            "axes.labelcolor": MUTED,
            "axes.titlecolor": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.grid": True,
            "grid.color": LINE,
            "grid.linewidth": 0.8,
            "axes.axisbelow": True,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.frameon": False,
            "legend.fontsize": 12,
            "svg.fonttype": "none",
        }
    )
    return family


def title(fig, text: str, subtitle: str) -> None:
    fig.text(0.04, 0.955, text, fontsize=21, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.885, subtitle, fontsize=13, color=MUTED, va="top")


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=160)  # 10in x 160dpi = 1600px wide
    fig.savefig(OUT / f"{name}.svg")
    plt.close(fig)
    print(f"  {name}.png / .svg")


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def bars(ax, labels, values, colors, fmt, horizontal=False):
    """Thin rounded bars with value labels in ink color (never series color)."""
    if horizontal:
        rects = ax.barh(labels, values, color=colors, height=0.55, edgecolor=PANEL, linewidth=2)
    else:
        rects = ax.bar(labels, values, color=colors, width=0.55, edgecolor=PANEL, linewidth=2)
    for r, v in zip(rects, values, strict=True):
        if horizontal:
            ax.text(
                r.get_width(),
                r.get_y() + r.get_height() / 2,
                f"  {fmt(v)}",
                va="center",
                ha="left",
                color=INK,
                fontsize=13,
                fontweight="semibold",
            )
        else:
            ax.text(
                r.get_x() + r.get_width() / 2,
                r.get_height(),
                fmt(v),
                va="bottom",
                ha="center",
                color=INK,
                fontsize=13,
                fontweight="semibold",
            )
    return rects


# -- charts -------------------------------------------------------------------------


def ablation(res: dict) -> None:
    cfg = res["configs"]
    rules_r, clf_r = cfg["rules only"]["recall"], cfg["classifier only"]["recall"]
    ratio = clf_r / rules_r if rules_r else float("inf")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 5.6))
    fig.subplots_adjust(left=0.07, right=0.97, top=0.74, bottom=0.12, wspace=0.28)
    colors = [CONFIG_COLORS[c] for c in CONFIGS]
    labels = ["Rules", "Classifier", "Rules +\nclassifier"]
    bars(a1, labels, [cfg[c]["recall"] for c in CONFIGS], colors, pct)
    a1.set_ylim(0, 1.12)
    a1.set_title("Recall on attacks (higher is better)", loc="left", fontsize=14, pad=12)
    bars(a2, labels, [cfg[c]["fpr"] for c in CONFIGS], colors, lambda v: pct(v, 2))
    a2.set_ylim(0, max(0.01, max(cfg[c]["fpr"] for c in CONFIGS) * 1.35))
    a2.set_title("False positives on benign (lower is better)", loc="left", fontsize=14, pad=12)
    for ax in (a1, a2):
        ax.yaxis.set_major_formatter(lambda v, _: pct(v, 0 if v >= 0.1 else 1))
        ax.grid(axis="x", visible=False)
    title(
        fig,
        f"The classifier catches {ratio:.1f}× more attacks than rules alone",
        f"{cfg['rules + classifier']['attacks']:,} public attacks, "
        f"{cfg['rules + classifier']['benign']:,} benign prompts · separate scales per panel",
    )
    save(fig, "ablation")


def latency(res: dict) -> None:
    lat = res["latency_ms_benign"]
    layers = ["rules", "pii", "classifier", "total guards"]
    names = ["Rules", "PII (Presidio)", "Classifier (ONNX)", "All guards"]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.subplots_adjust(left=0.2, right=0.9, top=0.74, bottom=0.12)
    y = range(len(layers))
    p50 = [lat[k]["p50"] for k in layers]
    p95 = [lat[k]["p95"] for k in layers]
    ax.barh(
        [i + 0.18 for i in y],
        p50,
        height=0.32,
        color=CYAN,
        label="p50",
        edgecolor=PANEL,
        linewidth=2,
    )
    ax.barh(
        [i - 0.18 for i in y],
        p95,
        height=0.32,
        color=VIOLET,
        label="p95",
        edgecolor=PANEL,
        linewidth=2,
    )
    for i in y:
        ax.text(p95[i], i - 0.18, f"  {p95[i]:.1f} ms", va="center", color=INK, fontsize=12)
        ax.text(p50[i], i + 0.18, f"  {p50[i]:.1f} ms", va="center", color=MUTED, fontsize=12)
    ax.set_yticks(list(y), names)
    ax.invert_yaxis()
    ax.set_xlabel("milliseconds on CPU (lower is better)")
    ax.set_xlim(0, max(p95) * 1.25)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper right")
    total, typical = lat["total guards"]["p95"], lat["total guards"]["p50"]
    title(
        fig,
        f"Guards add {typical:.0f} ms to a typical prompt, {total:.0f} ms at p95",
        "Latency per layer on benign prompts · p95 is long (~400-token) prompts · laptop CPU",
    )
    save(fig, "latency")


def precision_recall(res: dict) -> None:
    sweep = res["threshold_sweep"]
    thr = [s["threshold"] for s in sweep]
    xs = list(range(len(thr)))
    chosen = res["threshold"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 5.6), gridspec_kw={"width_ratios": [3, 2]})
    fig.subplots_adjust(left=0.07, right=0.97, top=0.74, bottom=0.21, wspace=0.25)
    a1.plot(
        xs, [s["precision"] for s in sweep], color=CYAN, lw=2, marker="o", ms=7, label="Precision"
    )
    a1.plot(xs, [s["recall"] for s in sweep], color=ORANGE, lw=2, marker="o", ms=7, label="Recall")
    a2.plot(xs, [s["fpr"] for s in sweep], color=VIOLET, lw=2, marker="o", ms=7, label="FPR")
    ci = thr.index(chosen) if chosen in thr else None
    for ax in (a1, a2):
        ax.set_xticks(xs, [str(t) for t in thr], rotation=45)
        ax.set_xlabel("classifier threshold")
        ax.grid(axis="x", visible=False)
        if ci is not None:
            ax.axvline(ci, color=MUTED, lw=1, ls="--")
    a1.set_ylim(min(s["recall"] for s in sweep) - 0.08, 1.02)
    a1.yaxis.set_major_formatter(lambda v, _: pct(v, 0))
    a1.set_title("Precision and recall", loc="left", fontsize=14, pad=12)
    a1.legend(loc="lower left")
    a2.yaxis.set_major_formatter(lambda v, _: pct(v, 1))
    a2.set_ylim(0, max(s["fpr"] for s in sweep) * 1.3 + 1e-4)
    a2.set_title("False-positive rate", loc="left", fontsize=14, pad=12)
    if ci is not None:
        s = sweep[ci]
        a1.annotate(
            f"chosen {chosen}\nP {pct(s['precision'])} · R {pct(s['recall'])}",
            (ci, s["recall"]),
            xytext=(10, -46),
            textcoords="offset points",
            color=INK,
            fontsize=11,
        )
    pr = sweep[ci] if ci is not None else sweep[-1]
    title(
        fig,
        f"At threshold {chosen}, {pct(pr['precision'])} of blocks are real attacks",
        "Rules + classifier on all public sets · dashed line = threshold in policy.yaml",
    )
    save(fig, "precision_recall")


def cost(res: dict) -> None:
    c = res["cost"]
    labels = ["LLM spend (Claude Haiku)", "Guard compute (CPU)", "Saved by blocking attacks"]
    values = [c["llm_usd_per_1k"], c["guard_compute_usd_per_1k"], c["saved_by_blocking_usd_per_1k"]]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.subplots_adjust(left=0.29, right=0.9, top=0.74, bottom=0.14)
    bars(ax, labels, values, [CYAN, VIOLET, ORANGE], lambda v: f"${v:.4f}", horizontal=True)
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.3)
    ax.set_xlabel("USD per 1,000 requests")
    ax.grid(axis="y", visible=False)
    ratio = c["saved_by_blocking_usd_per_1k"] / max(c["guard_compute_usd_per_1k"], 1e-9)
    title(
        fig,
        f"Guards pay for themselves: blocking saves {ratio:.0f}× their compute cost",
        f"Per 1K requests · {c['model']} at policy.yaml prices · 20% attack mix · "
        f"{c['avg_input_tokens']:.0f} in / {c['assumed_output_tokens']} out tokens",
    )
    save(fig, "cost_per_1k")


def recall_by_source(res: dict) -> None:
    src = [s for s in SOURCE_LABELS if res["by_source"].get(s, {}).get("attacks")]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.subplots_adjust(left=0.07, right=0.97, top=0.74, bottom=0.17)
    width = 0.24
    for i, cfgname in enumerate(CONFIGS):
        xs = [j + (i - 1) * width for j in range(len(src))]
        vals = [res["by_source"][s][cfgname] for s in src]
        ax.bar(
            xs,
            vals,
            width=width,
            color=CONFIG_COLORS[cfgname],
            label=cfgname,
            edgecolor=PANEL,
            linewidth=2,
        )
        if cfgname == "rules + classifier":  # label the shipped config only
            for x, v in zip(xs, vals, strict=True):
                ax.text(
                    x,
                    v + 0.015,
                    pct(v, 0),
                    ha="center",
                    color=INK,
                    fontsize=12,
                    fontweight="semibold",
                )
    ax.set_xticks(
        range(len(src)),
        [f"{SOURCE_LABELS[s]}\n{res['by_source'][s]['attacks']} attacks" for s in src],
    )
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_formatter(lambda v, _: pct(v, 0))
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.13), ncol=3)
    hold = res["generalization"]
    title(
        fig,
        f"{pct(hold['holdout_recall'], 0)} recall on hand-written attacks it never saw",
        "Recall by attack source · labels show the shipped config (rules + classifier)",
    )
    save(fig, "recall_by_source")


# -- interactive page ---------------------------------------------------------------


def load_test() -> None:
    """Throughput and p95 latency vs concurrent users, before vs after (scripts/load_test.py)."""
    if not LOAD_TEST.exists():
        print("  load_test skipped (run scripts/load_test.py first)")
        return
    runs = {k: v for k, v in json.loads(LOAD_TEST.read_text())["runs"].items()}
    if not runs:
        return
    colors = [ORANGE, CYAN, VIOLET]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 5.6))
    fig.subplots_adjust(left=0.07, right=0.97, top=0.72, bottom=0.2, wspace=0.25)
    for (label, run), color in zip(runs.items(), colors, strict=False):
        steps = run["steps"]
        users = [s["users"] for s in steps]
        a1.plot(users, [s["rps"] for s in steps], color=color, lw=2, marker="o", ms=7, label=label)
        a2.plot(users, [s["p95_ms"] for s in steps], color=color, lw=2, marker="o", ms=7)
        a1.annotate(
            f"{steps[-1]['rps']:.0f}",
            (users[-1], steps[-1]["rps"]),
            xytext=(6, -4),
            textcoords="offset points",
            color=INK,
            fontsize=12,
            fontweight="semibold",
        )
        a2.annotate(
            f"{steps[-1]['p95_ms'] / 1000:.1f} s",
            (users[-1], steps[-1]["p95_ms"]),
            xytext=(-8, 8),
            textcoords="offset points",
            ha="right",
            color=INK,
            fontsize=12,
            fontweight="semibold",
        )
    # What throughput would be with no queueing: users / (think time + unloaded response time).
    first = next(iter(runs.values()))
    think = sum(first["think_time_s"]) / 2
    unloaded = first["steps"][0]["p50_ms"] / 1000
    users = [s["users"] for s in first["steps"]]
    a1.plot(
        users,
        [u / (think + unloaded) for u in users],
        color=MUTED,
        lw=1,
        ls=":",
        label="no queueing (ideal)",
    )
    for ax in (a1, a2):
        ax.set_xscale("log", base=2)
        ax.set_xticks(users, [str(u) for u in users])
        ax.minorticks_off()
        ax.set_xlabel("concurrent chat users")
        ax.grid(axis="x", visible=False)
    a1.set_ylim(0, max(u / (think + unloaded) for u in users) * 1.08)
    a1.set_title("Throughput (requests/s)", loc="left", fontsize=14, pad=12)
    a2.set_ylim(0, None)
    a2.yaxis.set_major_formatter(lambda v, _: f"{v / 1000:.1f} s" if v >= 1000 else f"{v:.0f} ms")
    a2.set_title("p95 response time", loc="left", fontsize=14, pad=12)
    fig.legend(loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.0))
    peak = {k: max(s["rps"] for s in r["steps"]) for k, r in runs.items()}
    names = list(peak)
    if len(names) > 1 and peak[names[-1]] > peak[names[0]] * 1.1:
        headline = (
            f"Moving guards off the event loop lifts capacity "
            f"from {peak[names[0]]:.0f} to {peak[names[-1]]:.0f} req/s"
        )
    else:
        headline = f"One gateway process handles ~{max(peak.values()):.0f} req/s with all guards on"
    title(
        fig,
        headline,
        f"Locust, closed loop, {think:.0f} s think time · mock LLM "
        f"(~{unloaded * 1000:.0f} ms) · 68% benign / 12% PII / 20% attacks · laptop CPU",
    )
    save(fig, "load_test")


def plotly_page(res: dict) -> None:
    layout = dict(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=PANEL,
        font=dict(family="Inter, sans-serif", color=INK, size=13),
        margin=dict(l=60, r=30, t=70, b=60),
        height=440,
        hoverlabel=dict(bgcolor=PANEL, bordercolor=LINE, font_color=INK),
    )
    axis = dict(gridcolor=LINE, zeroline=False, linecolor=LINE)
    figs = []
    cfg = res["configs"]

    f = make_subplots(
        rows=1, cols=2, subplot_titles=("Recall on attacks", "False positives on benign")
    )
    for c in CONFIGS:
        f.add_bar(
            x=[c],
            y=[cfg[c]["recall"]],
            marker_color=CONFIG_COLORS[c],
            name=c,
            legendgroup=c,
            row=1,
            col=1,
            hovertemplate=f"{c}<br>recall %{{y:.1%}}<extra></extra>",
        )
        f.add_bar(
            x=[c],
            y=[cfg[c]["fpr"]],
            marker_color=CONFIG_COLORS[c],
            name=c,
            legendgroup=c,
            showlegend=False,
            row=1,
            col=2,
            hovertemplate=f"{c}<br>FPR %{{y:.2%}}<extra></extra>",
        )
    f.update_yaxes(tickformat=".0%", **axis)
    f.update_layout(title="Ablation: rules vs classifier vs both", **layout)
    figs.append(f)

    lat = res["latency_ms_benign"]
    layers = ["rules", "pii", "classifier", "total guards"]
    f = go.Figure()
    for q, color in (("p50", CYAN), ("p95", VIOLET)):
        f.add_bar(
            y=layers,
            x=[lat[k][q] for k in layers],
            orientation="h",
            name=q,
            marker_color=color,
            hovertemplate="%{y}: %{x:.1f} ms<extra>" + q + "</extra>",
        )
    f.update_layout(title="Latency per layer (ms, benign prompts)", barmode="group", **layout)
    f.update_xaxes(**axis)
    f.update_yaxes(autorange="reversed", **axis)
    figs.append(f)

    sweep = res["threshold_sweep"]
    f = make_subplots(rows=1, cols=2, subplot_titles=("Precision & recall", "False-positive rate"))
    thr = [str(s["threshold"]) for s in sweep]
    for key, color, col in (("precision", CYAN, 1), ("recall", ORANGE, 1), ("fpr", VIOLET, 2)):
        f.add_scatter(
            x=thr,
            y=[s[key] for s in sweep],
            mode="lines+markers",
            name=key,
            line=dict(color=color, width=2),
            marker=dict(size=8),
            row=1,
            col=col,
            hovertemplate=f"threshold %{{x}}<br>{key} %{{y:.2%}}<extra></extra>",
        )
    f.update_yaxes(tickformat=".1%", **axis)
    f.update_xaxes(title="classifier threshold", type="category", **axis)
    f.update_layout(title="Threshold sweep (rules + classifier)", hovermode="x unified", **layout)
    figs.append(f)

    src = [s for s in SOURCE_LABELS if res["by_source"].get(s, {}).get("attacks")]
    f = go.Figure()
    for c in CONFIGS:
        f.add_bar(
            x=[SOURCE_LABELS[s] for s in src],
            y=[res["by_source"][s][c] for s in src],
            name=c,
            marker_color=CONFIG_COLORS[c],
            hovertemplate="%{x}<br>" + c + ": %{y:.1%}<extra></extra>",
        )
    f.update_layout(title="Recall by attack source", barmode="group", **layout)
    f.update_yaxes(tickformat=".0%", **axis)
    f.update_xaxes(**axis)
    figs.append(f)

    c = res["cost"]
    f = go.Figure(
        go.Bar(
            y=["LLM spend", "Guard compute", "Saved by blocking"],
            x=[
                c["llm_usd_per_1k"],
                c["guard_compute_usd_per_1k"],
                c["saved_by_blocking_usd_per_1k"],
            ],
            orientation="h",
            marker_color=[CYAN, VIOLET, ORANGE],
            hovertemplate="%{y}: $%{x:.4f} per 1K requests<extra></extra>",
        )
    )
    f.update_layout(title="Cost per 1K requests (USD)", **layout)
    f.update_xaxes(tickprefix="$", **axis)
    f.update_yaxes(autorange="reversed", **axis)
    figs.append(f)

    divs = "\n".join(
        f'<section class="card">{fig.to_html(full_html=False, include_plotlyjs=(i == 0) and "cdn")}'
        "</section>"
        for i, fig in enumerate(figs)
    )
    h = res["headline"]["sentence"]
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bulwark Eval Results</title>
<link rel="stylesheet"
 href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap">
<style>
 body{{background:{BG};color:{INK};font-family:Inter,sans-serif;margin:0;padding:32px 16px}}
 main{{max-width:1100px;margin:0 auto}} h1{{font-size:28px;margin:0 0 6px}}
 p{{color:{MUTED};margin:0 0 24px}} .card{{background:{PANEL};border:1px solid {LINE};
 border-radius:16px;padding:8px;margin-bottom:20px;overflow:hidden}}
</style></head><body><main>
<h1>Bulwark evaluation</h1><p>{h} Generated {res["generated_at"]}.</p>
{divs}
</main></body></html>"""
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print("  index.html (interactive)")


def main() -> None:
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    family = setup_style()
    print(f"Rendering charts to {OUT} (font: {family})")
    for chart in (ablation, latency, precision_recall, cost, recall_by_source):
        chart(res)
    load_test()
    plotly_page(res)


if __name__ == "__main__":
    main()
