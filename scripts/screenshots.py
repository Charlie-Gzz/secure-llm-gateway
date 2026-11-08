"""Capture portfolio screenshots with headless Chromium (Playwright).

Needs the stack running (`docker compose up -d`). Captures:
  assets/screenshots/playground-<example>.png   one per example button
  assets/screenshots/playground-hero.png        a short conversation (README hero)
  assets/screenshots/grafana.png                the Bulwark dashboard (after sending traffic)
  assets/screenshots/jaeger-trace.png           one request's trace

    uv run python scripts/screenshots.py [--gateway URL] [--grafana URL] [--jaeger URL]
                                         [--no-traffic] [--only playground|grafana|jaeger]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "screenshots"
VIEWPORT = {"width": 1600, "height": 1000}
EXAMPLES = ["normal", "ignore", "ssn", "roleplay", "indirect", "contact"]


def wait_for(url: str, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    sys.exit(f"{url} is not reachable; start the stack with `docker compose up -d`")


def click_example(page: Page, example: str) -> str:
    before = page.locator("#verdict").get_attribute("data-verdict-seq") or ""
    page.click(f'button[data-example="{example}"]')
    page.wait_for_function(
        "prev => document.querySelector('#verdict').dataset.verdict && "
        "!document.querySelector('#send').disabled && "
        "document.querySelector('#verdict').dataset.verdictSeq !== prev",
        arg=before,
    )
    page.wait_for_timeout(400)  # let fade-in animations finish
    return page.locator("#verdict").get_attribute("data-verdict")


def playground(page: Page, gateway: str) -> None:
    for ex in EXAMPLES:
        page.goto(gateway)
        page.wait_for_selector(f'button[data-example="{ex}"]')
        verdict = click_example(page, ex)
        page.screenshot(path=OUT / f"playground-{ex}.png")
        print(f"  playground-{ex}.png ({verdict})")

    page.goto(gateway)
    page.wait_for_selector('button[data-example="normal"]')
    for ex in ("normal", "ssn", "roleplay"):
        click_example(page, ex)
    page.screenshot(path=OUT / "playground-hero.png")
    print("  playground-hero.png")


def grafana(page: Page, url: str, gateway: str, send_traffic: bool) -> None:
    if send_traffic:
        print("  sending traffic so the dashboard has data...")
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "traffic.py"),
                "--url",
                gateway,
                "--requests",
                "400",
                "--rps",
                "12",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        time.sleep(12)  # two Prometheus scrapes
    page.set_viewport_size({"width": 1600, "height": 1330})  # fit all three panel rows
    page.goto(f"{url}/d/bulwark/bulwark?orgId=1&kiosk&from=now-5m&to=now&refresh=")
    page.wait_for_selector(
        "[data-testid='data-testid Panel header Requests'], .react-grid-layout", timeout=30000
    )
    page.wait_for_timeout(6000)
    page.screenshot(path=OUT / "grafana.png")
    print("  grafana.png")


def jaeger(page: Page, url: str, gateway: str) -> None:
    body = httpx.post(
        f"{gateway}/v1/chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Here is my SSN: 536-22-8714. Please fill in the tax form.",
                }
            ]
        },
        timeout=30,
    ).json()
    trace_id = body["gateway"]["trace_id"]
    time.sleep(5)  # batch export + collector flush
    page.set_viewport_size({"width": 1600, "height": 560})  # the trace is short; skip empty space
    page.goto(f"{url}/trace/{trace_id}")
    page.wait_for_selector("text=gateway.request", timeout=30000)
    page.wait_for_timeout(1500)
    page.screenshot(path=OUT / "jaeger-trace.png")
    print(f"  jaeger-trace.png (trace {trace_id[:12]}…)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="http://localhost:8000")
    ap.add_argument("--grafana", default="http://localhost:3000")
    ap.add_argument("--jaeger", default="http://localhost:16686")
    ap.add_argument("--no-traffic", action="store_true")
    ap.add_argument("--only", choices=["playground", "grafana", "jaeger"])
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    wait_for(f"{args.gateway}/healthz")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2, color_scheme="dark")
        page = ctx.new_page()
        if args.only in (None, "playground"):
            playground(page, args.gateway)
        if args.only in (None, "grafana"):
            wait_for(args.grafana)
            grafana(page, args.grafana, args.gateway, not args.no_traffic)
        if args.only in (None, "jaeger"):
            wait_for(args.jaeger)
            jaeger(page, args.jaeger, args.gateway)
        browser.close()


if __name__ == "__main__":
    main()
