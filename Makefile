# Bulwark: common tasks. Everything runs through uv so no manual venv activation is needed.
# On Windows without GNU make, `mingw32-make <target>` works the same way.

PORT ?= 8000

.PHONY: setup run test lint fmt traffic loadtest eval eval-cost assets gif models up down

setup:          ## Install deps (incl. spaCy model) and download the ONNX classifier
	uv sync
	uv run python scripts/export_classifier.py

run:            ## Run the gateway locally on :8000
	uv run uvicorn gateway.main:app --host 0.0.0.0 --port $(PORT)

test:           ## Run the test suite (mock upstream, no network)
	uv run pytest -q

lint:           ## Lint and format-check
	uv run ruff check .
	uv run ruff format --check .

fmt:            ## Auto-fix lint and format
	uv run ruff check --fix .
	uv run ruff format .

traffic:        ## Send a realistic mix of benign + attack traffic to a running gateway
	uv run python scripts/traffic.py

loadtest:       ## Locust load test (1-64 users) against a running mock gateway -> eval/results/load_test.json
	uv run python scripts/load_test.py

eval:           ## Regenerate all evaluation numbers from scratch
	uv run python eval/run_eval.py

eval-cost:      ## Small real-API cost check (<=100 requests; needs ANTHROPIC_API_KEY)
	uv run python eval/cost_check.py

assets:         ## Regenerate charts, diagram, and screenshots into assets/
	uv run python scripts/make_charts.py
	uv run python scripts/make_diagram.py
	uv run python scripts/screenshots.py

gif:            ## Record the playground GIF for the README (needs the stack + ffmpeg)
	uv run python scripts/record_gif.py

models:         ## Download + export the ONNX classifier
	uv run python scripts/export_classifier.py

up:             ## Start gateway + OTel Collector + Jaeger + Prometheus + Grafana
	docker compose up -d --build

down:
	docker compose down
