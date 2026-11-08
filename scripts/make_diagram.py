"""Render the architecture diagram as SVG (fonts embedded) and PNG, in the Bulwark dark palette.

    uv run python scripts/make_diagram.py      (part of `make assets`)

Output: assets/diagram/architecture.svg and architecture.png (2x, 3200px wide).
"""

from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "diagram"
FONTS = ROOT / "assets" / "fonts"

BG, PANEL, LINE, INK, MUTED = "#0B0F17", "#131A26", "#1F2937", "#E5E7EB", "#9CA3AF"
GREEN, AMBER, RED, CYAN = "#22C55E", "#F59E0B", "#EF4444", "#38BDF8"
W, H = 1600, 860


def font_face() -> str:
    faces = []
    for fname, family, weight in (
        ("Inter-Regular.ttf", "Inter", 400),
        ("Inter-SemiBold.ttf", "Inter", 600),
        ("Inter-Bold.ttf", "Inter", 700),
        ("JetBrainsMono-Regular.ttf", "JetBrains Mono", 400),
    ):
        path = FONTS / fname
        if path.exists():
            data = base64.b64encode(path.read_bytes()).decode()
            faces.append(
                f"@font-face{{font-family:'{family}';font-weight:{weight};"
                f"src:url(data:font/ttf;base64,{data}) format('truetype');}}"
            )
    return "\n".join(faces)


def box(x, y, w, h, title, sub="", stroke=LINE, fill=PANEL, title_color=INK, dashed=False):
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    cy = y + h / 2
    t_y, s_y = (cy - 4, cy + 18) if sub else (cy + 6, 0)
    sub_svg = f'<text x="{x + w / 2}" y="{s_y}" class="sub">{sub}</text>' if sub else ""
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="2"{dash}/>'
        f'<text x="{x + w / 2}" y="{t_y}" class="title" fill="{title_color}">{title}</text>'
        f"{sub_svg}"
    )


def arrow(d, color=MUTED, dashed=False, label="", lx=0, ly=0, marker="arr"):
    dash = ' stroke-dasharray="7 6"' if dashed else ""
    lbl = f'<text x="{lx}" y="{ly}" class="edge" fill="{color}">{label}</text>' if label else ""
    return (
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2"{dash} '
        f'marker-end="url(#{marker})"/>{lbl}'
    )


def step_num(x, y, n):
    return (
        f'<circle cx="{x}" cy="{y}" r="13" fill="{CYAN}"/>'
        f'<text x="{x}" y="{y + 5}" class="num">{n}</text>'
    )


def build_svg() -> str:
    parts = [
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        '<text x="60" y="72" class="h1">Bulwark architecture</text>',
        '<text x="60" y="104" class="lead">A drop-in proxy: every request passes layered guards '
        "before and after the model, and every step is traced and measured.</text>",
        # Gateway container
        f'<rect x="290" y="150" width="900" height="420" rx="22" fill="#0F1520" '
        f'stroke="{CYAN}" stroke-opacity="0.45" stroke-width="2"/>',
        '<image href="data:image/svg+xml;base64,{logo}" x="312" y="166" width="30" height="30"/>',
        f'<text x="352" y="188" class="label" fill="{CYAN}">Bulwark gateway · FastAPI</text>',
        # Client
        box(60, 210, 170, 286, "Client", "OpenAI SDK · UI", stroke="#334155"),
        # Row A: input guards
        box(320, 220, 200, 92, "Rules", "regex · ~0.1 ms", stroke=CYAN),
        box(560, 220, 220, 92, "Classifier", "DeBERTa-v3 · ONNX", stroke=CYAN),
        box(820, 220, 200, 92, "PII · prompt", "Presidio redact", stroke=CYAN),
        # Upstream
        box(1250, 220, 290, 92, "Upstream LLM", "Claude Haiku 5.5 · or mock", stroke="#475569"),
        # Row B
        box(
            360,
            410,
            280,
            92,
            "Response + verdict",
            "gateway field + header",
            stroke="#475569",
        ),
        box(820, 410, 200, 92, "PII · answer", "Presidio redact", stroke=CYAN),
        # Telemetry row
        box(290, 680, 210, 84, "OTel Collector", "OTLP gRPC"),
        box(540, 680, 160, 84, "Jaeger", "traces"),
        box(760, 680, 180, 84, "Prometheus", "scrapes /metrics"),
        box(980, 680, 160, 84, "Grafana", "dashboard"),
        box(1250, 680, 220, 84, "SQLite", "request log + cost"),
        # Main flow
        arrow("M230 266 L314 266", INK),
        arrow("M520 266 L554 266", INK),
        arrow("M780 266 L814 266", INK),
        arrow("M1020 266 L1244 266", INK, label="clean prompt", lx=1132, ly=254),
        arrow("M1395 312 L1395 456 L1026 456", INK, label="model answer", lx=1250, ly=444),
        arrow("M820 456 L646 456", INK),
        arrow("M360 456 L236 456", INK, label="answer", lx=298, ly=444),
        # Block branches
        arrow(
            "M420 312 L420 404", RED, dashed=True, marker="arr-red", label="block", lx=380, ly=364
        ),
        arrow(
            "M610 312 L610 404", RED, dashed=True, marker="arr-red", label="block", lx=652, ly=364
        ),
        # Telemetry
        arrow("M395 570 L395 674", MUTED, dashed=True, label="traces", lx=440, ly=630),
        arrow("M500 722 L534 722", MUTED),
        arrow("M850 674 L850 570", MUTED, dashed=True, label="metrics", lx=898, ly=630),
        arrow("M940 722 L974 722", MUTED),
        arrow(
            "M1150 570 L1150 640 L1360 640 L1360 674",
            MUTED,
            dashed=True,
            label="log + cost",
            lx=1255,
            ly=628,
        ),
        # Step numbers
        step_num(320, 220, 1),
        step_num(560, 220, 2),
        step_num(820, 220, 3),
        step_num(1250, 220, 4),
        step_num(820, 410, 5),
        # Legend
        f'<line x1="60" y1="812" x2="96" y2="812" stroke="{INK}" stroke-width="2.2"/>',
        '<text x="106" y="817" class="legend">request path</text>',
        f'<line x1="250" y1="812" x2="286" y2="812" stroke="{RED}" stroke-width="2.2" '
        'stroke-dasharray="7 6"/>',
        '<text x="296" y="817" class="legend">blocked: never reaches the model</text>',
        f'<line x1="560" y1="812" x2="596" y2="812" stroke="{MUTED}" stroke-width="2.2" '
        'stroke-dasharray="7 6"/>',
        '<text x="606" y="817" class="legend">observability</text>',
    ]
    logo = base64.b64encode((ROOT / "ui" / "logo.svg").read_bytes()).decode()
    body = "\n".join(parts).replace("{logo}", logo)
    style = f"""{font_face()}
text{{font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
.h1{{font-size:34px;font-weight:700;fill:{INK}}}
.lead{{font-size:17px;fill:{MUTED}}}
.title{{font-size:19px;font-weight:600;text-anchor:middle}}
.sub{{font-size:14px;fill:{MUTED};text-anchor:middle;font-family:'JetBrains Mono',monospace}}
.label{{font-size:17px;font-weight:600}}
.edge{{font-size:13px;text-anchor:middle;font-weight:600}}
.num{{font-size:14px;font-weight:700;fill:{BG};text-anchor:middle}}
.legend{{font-size:14px;fill:{MUTED}}}"""
    defs = (
        f'<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="{INK}"/></marker>'
        f'<marker id="arr-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="{RED}"/></marker>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
        f'height="{H}" role="img" aria-label="Bulwark architecture diagram">'
        f"<defs><style>{style}</style>{defs}</defs>\n{body}\n</svg>\n"
    )


def to_png(svg_path: Path, png_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        page.goto(svg_path.resolve().as_uri())
        page.wait_for_timeout(300)
        page.screenshot(path=str(png_path), full_page=False)
        browser.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    svg = OUT / "architecture.svg"
    svg.write_text(build_svg(), encoding="utf-8")
    to_png(svg, OUT / "architecture.png")
    print(f"wrote {svg} and architecture.png")


if __name__ == "__main__":
    main()
