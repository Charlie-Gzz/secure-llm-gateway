"""Step a Locust load test through concurrency levels and save throughput + latency per step.

Needs a running gateway (e.g. `docker compose up -d`). Writes eval/results/load_test.json;
`scripts/make_charts.py` turns it into assets/charts/load_test.{png,svg}.

    uv run python scripts/load_test.py [--host http://localhost:8000] [--users 1,4,8,16,32,64]
                                       [--seconds 40] [--label baseline]
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "eval" / "results" / "load_test.json"
LOCUSTFILE = ROOT / "scripts" / "locustfile.py"


def run_step(host: str, users: int, seconds: int, tmp: Path) -> dict:
    prefix = tmp / f"u{users}"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(LOCUSTFILE),
            "--host",
            host,
            "--headless",
            "--users",
            str(users),
            "--spawn-rate",
            str(users),  # all users start at once...
            "--reset-stats",  # ...and stats start after spawning, so ramp-up isn't counted
            "--run-time",
            f"{seconds}s",
            "--csv",
            str(prefix),
            "--only-summary",
            "--loglevel",
            "WARNING",
        ],
        check=False,  # locust exits 1 if any request failed; we record failures instead
        capture_output=True,
        text=True,
    )
    if not Path(f"{prefix}_stats.csv").exists():
        sys.exit("locust produced no stats:\n" + proc.stderr[-2000:])
    with open(f"{prefix}_stats.csv", encoding="utf-8") as f:
        rows = {r["Name"]: r for r in csv.DictReader(f)}

    def stats(r: dict) -> dict:
        return {
            "requests": int(r["Request Count"]),
            "failures": int(r["Failure Count"]),
            "rps": float(r["Requests/s"]),
            "p50_ms": float(r["50%"]),
            "p95_ms": float(r["95%"]),
            "p99_ms": float(r["99%"]),
        }

    step = {"users": users, **stats(rows["Aggregated"])}
    step["by_category"] = {n: stats(rows[n]) for n in ("benign", "pii", "attack") if n in rows}
    return step


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="http://localhost:8000")
    ap.add_argument("--users", default="1,4,8,16,32,64")
    ap.add_argument("--seconds", type=int, default=40)
    ap.add_argument("--label", default="current", help="name for this run in load_test.json")
    args = ap.parse_args()

    health = httpx.get(f"{args.host}/healthz", timeout=10).json()
    if health.get("upstream") != "mock":
        sys.exit("Refusing to load-test a real upstream (it would spend money). Use UPSTREAM=mock.")

    levels = [int(u) for u in args.users.split(",")]
    steps = []
    with tempfile.TemporaryDirectory() as tmp:
        for users in levels:
            t0 = time.time()
            step = run_step(args.host, users, args.seconds, Path(tmp))
            steps.append(step)
            print(
                f"{users:>3} users  {step['rps']:6.1f} req/s  p50 {step['p50_ms']:6.0f} ms  "
                f"p95 {step['p95_ms']:6.0f} ms  failures {step['failures']}  "
                f"({time.time() - t0:.0f}s)"
            )

    data = json.loads(OUT.read_text()) if OUT.exists() else {"runs": {}}
    data["runs"][args.label] = {
        "steps": steps,
        "seconds_per_step": args.seconds,
        "think_time_s": [0.5, 1.5],
        "gateway": health,
        "machine": f"{platform.system()} {platform.machine()}, load generator on the same machine",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    OUT.write_text(json.dumps(data, indent=2))
    print(f"wrote {OUT} (run '{args.label}')")


if __name__ == "__main__":
    main()
