"""Runtime settings (from environment / .env) and the YAML policy."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
PRODUCT_NAME = "Bulwark"

Action = Literal["allow", "redact", "block"]


class UpstreamPolicy(BaseModel):
    model: str
    max_tokens: int = 1024
    effort: str = "low"
    timeout_s: float = 60


class Price(BaseModel):
    input: float  # USD per 1M input tokens
    output: float  # USD per 1M output tokens


class GuardPolicy(BaseModel):
    enabled: bool = True
    action: Action = "block"


class ClassifierPolicy(GuardPolicy):
    threshold: float = 0.9
    max_length: int = 512


class PiiPolicy(GuardPolicy):
    action: Action = "redact"
    min_score: float = 0.5
    entities: list[str] = Field(default_factory=list)


class Guards(BaseModel):
    rules: GuardPolicy = GuardPolicy()
    classifier: ClassifierPolicy = ClassifierPolicy()
    pii_input: PiiPolicy = PiiPolicy()
    pii_output: PiiPolicy = PiiPolicy()


class Policy(BaseModel):
    upstream: UpstreamPolicy
    pricing: dict[str, Price]
    guards: Guards = Guards()
    blocked_message: str = "Blocked by policy."

    @classmethod
    def load(cls, path: Path) -> Policy:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Settings:
    upstream: str  # "mock" or "anthropic"
    anthropic_api_key: str
    policy_path: Path
    db_path: Path
    mock_latency_ms: int
    classifier_enabled: bool
    pii_enabled: bool
    otel_endpoint: str | None
    model_dir: Path
    jaeger_url: str
    grafana_url: str


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    return Settings(
        upstream=os.getenv("UPSTREAM", "mock").strip().lower(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        policy_path=Path(os.getenv("POLICY_PATH", ROOT / "policy.yaml")),
        db_path=Path(os.getenv("DB_PATH", ROOT / "data" / "gateway.db")),
        mock_latency_ms=int(os.getenv("MOCK_LATENCY_MS", "150")),
        classifier_enabled=_flag("CLASSIFIER_ENABLED", True),
        pii_enabled=_flag("PII_ENABLED", True),
        otel_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or None,
        model_dir=Path(os.getenv("MODEL_DIR", ROOT / "models")),
        jaeger_url=os.getenv("PUBLIC_JAEGER_URL", "http://localhost:16686"),
        grafana_url=os.getenv("PUBLIC_GRAFANA_URL", "http://localhost:3000"),
    )
