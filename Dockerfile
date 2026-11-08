# syntax=docker/dockerfile:1
# Bulwark gateway image: Python 3.12 + uv, with the ONNX classifier and spaCy model baked in.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 1. Dependencies (cached layer; includes the spaCy en_core_web_lg wheel).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 2. Classifier weights (~740 MB). Drop the HF download cache so it isn't stored twice.
COPY scripts/export_classifier.py scripts/
RUN python scripts/export_classifier.py && rm -rf /root/.cache/huggingface

# 3. App code.
COPY gateway gateway
COPY ui ui
COPY policy.yaml ./

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
