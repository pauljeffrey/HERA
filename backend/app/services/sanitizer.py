"""PII/PHI sanitizer layer — strips identifiers before external API calls."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import get_settings

# Lightweight fallback when Presidio is unavailable (showcase / dev).
_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")
_MRN_PATTERN = re.compile(r"\b(?:MRN|Patient ID)[:\s#]*[\w-]+\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.\w+\b")
_DOB_PATTERN = re.compile(r"\b(?:DOB|Date of Birth)[:\s]*[\d/-]+\b", re.IGNORECASE)


@dataclass
class SanitizationResult:
    sanitized_text: str
    replacements: list[dict[str, str]] = field(default_factory=list)


def _presidio_sanitize(text: str) -> SanitizationResult | None:
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        from presidio_anonymizer.entities import OperatorConfig
    except ImportError:
        return None

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    results = analyzer.analyze(text=text, language="en")
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators={"DEFAULT": OperatorConfig("replace", {"new_value": "<PHI>"})},
    )
    replacements = [
        {"entity": r.entity_type, "start": r.start, "end": r.end}
        for r in results
    ]
    return SanitizationResult(sanitized_text=anonymized.text, replacements=replacements)


def _regex_sanitize(text: str) -> SanitizationResult:
    replacements: list[dict[str, str]] = []
    sanitized = text

    for pattern, token, label in [
        (_NAME_PATTERN, "Jane Doe", "PERSON"),
        (_MRN_PATTERN, "MRN: <REDACTED>", "MRN"),
        (_PHONE_PATTERN, "<PHONE>", "PHONE"),
        (_EMAIL_PATTERN, "<EMAIL>", "EMAIL"),
        (_DOB_PATTERN, "DOB: <REDACTED>", "DOB"),
    ]:
        if pattern.search(sanitized):
            replacements.append({"entity": label, "pattern": pattern.pattern})
            sanitized = pattern.sub(token, sanitized)

    return SanitizationResult(sanitized_text=sanitized, replacements=replacements)


def sanitize_clinical_text(text: str) -> SanitizationResult:
    """Pass unstructured clinical text through PII/PHI sanitizer before external APIs."""
    settings = get_settings()
    if settings.presidio_enabled:
        result = _presidio_sanitize(text)
        if result is not None:
            return result
    return _regex_sanitize(text)
