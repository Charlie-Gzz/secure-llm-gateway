"""Record the playground clicking through four examples and save it as assets/playground.gif.

Needs the stack running and ffmpeg on PATH.

    uv run python scripts/record_gif.py [--gateway http://localhost:8000]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "playground.gif"
SIZE = {"width": 1280, "height": 800}
SEQUENCE = ["normal", "ignore", "roleplay", "ssn"]


def record(gateway: str, video_dir: Path) -> Path:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport=SIZE,
            color_scheme="dark",
            record_video_dir=str(video_dir),
            record_video_size=SIZE,
        )
        page = ctx.new_page()
        page.goto(gateway)
        page.wait_for_selector('button[data-example="normal"]')
        page.wait_for_timeout(1200)
        for ex in SEQUENCE:
            page.hover(f'button[data-example="{ex}"]')
            page.wait_for_timeout(500)
            page.click(f'button[data-example="{ex}"]')
            page.wait_for_function("!document.querySelector('#send').disabled")
            page.wait_for_timeout(2200)  # let viewers read the inspector
        video = page.video.path()
        ctx.close()
        browser.close()
    return Path(video)


def to_gif(video: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH")
    filters = "fps=10,scale=800:-1:flags=lanczos"
    palette = video.with_suffix(".png")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            f"{filters},palettegen=max_colors=128:stats_mode=diff",
            str(palette),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-i",
            str(palette),
            "-lavfi",
            f"{filters} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
            str(OUT),
        ],
        check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="http://localhost:8000")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        video = record(args.gateway, Path(tmp))
        to_gif(video)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
