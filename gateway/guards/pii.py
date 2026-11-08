"""PII guard: Microsoft Presidio finds personal data and replaces it with typed placeholders.

"My SSN is 536-22-8714" becomes "My SSN is <US_SSN>" before it ever reaches the LLM,
and the same check runs on the model's answer on the way back.
"""

from __future__ import annotations

import logging

import spacy.util
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

log = logging.getLogger("bulwark.pii")

SPACY_MODELS = ("en_core_web_lg", "en_core_web_md", "en_core_web_sm")


def _pick_spacy_model() -> str:
    for name in SPACY_MODELS:
        if spacy.util.is_package(name):
            return name
    raise RuntimeError("No spaCy English model installed; run `make setup`")


class PiiGuard:
    def __init__(self):
        self.spacy_model = _pick_spacy_model()
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": self.spacy_model}],
            }
        )
        self.analyzer = AnalyzerEngine(
            nlp_engine=provider.create_engine(), supported_languages=["en"]
        )
        self.anonymizer = AnonymizerEngine()
        log.info("PII guard ready (spaCy model: %s)", self.spacy_model)

    def redact(self, text: str, entities: list[str], min_score: float) -> tuple[str, list[dict]]:
        """Return (redacted_text, findings). Findings never include the raw PII value."""
        if not text.strip():
            return text, []
        results = self.analyzer.analyze(
            text=text, language="en", entities=entities, score_threshold=min_score
        )
        if not results:
            return text, []
        redacted = self.anonymizer.anonymize(text=text, analyzer_results=results).text
        findings = [{"entity": r.entity_type, "score": round(r.score, 2)} for r in results]
        return redacted, findings
