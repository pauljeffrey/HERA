"""Windowed numeric guard — a soft, informational pre-check near clinical anchor keywords.

This no longer excludes candidates from the funnel. Clinical notes often
state a constraint in prose without a clean number ("creatinine elevated",
"eGFR severely reduced") or with a spelled-out comparison ("LVEF greater
than 35%" instead of ">35%") — treating a guard miss as a hard filter risked
dropping genuinely eligible patients before the Tier 3 agent, which can read
the full note and reason about qualitative language, ever saw them. The
guard's evaluation is kept only for pipeline observability/logging; the
analysis agent (`agents/analysis_agent.py`, via its `validate` query type)
is the sole source of truth for whether a constraint is actually met.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.models.search import NumericalConstraint, NumericalOperator

logger = logging.getLogger(__name__)

NUMBER_RE = re.compile(r"(?<!\d)(-?\d+(?:\.\d+)?)(?!\d)")

# Spelled-out comparisons clinicians actually write instead of symbols —
# matched purely to widen the numbers we consider "near" a comparison,
# not to gate anything.
_NATURAL_LANGUAGE_NUMBER_RE = re.compile(
    r"(?:greater than|more than|above|over|exceeds?|at least|"
    r"less than|below|under|at most|up to|"
    r"equal to|equals?)\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConstraintEvaluation:
    parameter_name: str
    passed: bool
    observed_values: list[float]
    window_snippet: str


def _anchor_pattern(triggers: list[str]) -> re.Pattern[str]:
    escaped = [re.escape(t.strip()) for t in triggers if t.strip()]
    if not escaped:
        raise ValueError("triggers must not be empty")
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def _compare(value: float, constraint: NumericalConstraint) -> bool:
    op = constraint.operator
    target = constraint.target_value
    secondary = constraint.secondary_value

    if op == NumericalOperator.GT:
        return value > target
    if op == NumericalOperator.GTE:
        return value >= target
    if op == NumericalOperator.LT:
        return value < target
    if op == NumericalOperator.LTE:
        return value <= target
    if op == NumericalOperator.EQ:
        return abs(value - target) < 0.01
    if op == NumericalOperator.RANGE and secondary is not None:
        low, high = sorted((target, secondary))
        return low <= value <= high
    return False


def _extract_numbers(window: str, unit_regex: str | None) -> list[float]:
    values: list[float] = []
    if unit_regex:
        pattern = re.compile(
            rf"(?<!\d)(-?\d+(?:\.\d+)?)\s*(?:{unit_regex})",
            re.IGNORECASE,
        )
        values.extend(float(v) for v in pattern.findall(window))
    values.extend(float(v) for v in NUMBER_RE.findall(window))
    # Numbers following a spelled-out comparison ("LVEF greater than 35%")
    # even if outside the unit-regex match, in case the note uses words
    # instead of symbols.
    values.extend(float(v) for v in _NATURAL_LANGUAGE_NUMBER_RE.findall(window))
    return values


def evaluate_constraint(text: str, constraint: NumericalConstraint) -> ConstraintEvaluation:
    """Slice a localized window around each anchor before extracting numbers.
    Informational only — see module docstring."""
    anchor = _anchor_pattern(constraint.triggers)
    matches = list(anchor.finditer(text))
    if not matches:
        return ConstraintEvaluation(constraint.parameter_name, False, [], "")

    observed: list[float] = []
    snippet = ""
    for match in matches:
        start = max(0, match.start() - constraint.window_chars)
        end = min(len(text), match.end() + constraint.window_chars)
        window = text[start:end]
        snippet = snippet or window
        for value in _extract_numbers(window, constraint.unit_regex):
            observed.append(value)
            if _compare(value, constraint):
                return ConstraintEvaluation(constraint.parameter_name, True, observed, window)

    return ConstraintEvaluation(constraint.parameter_name, False, observed, snippet)


def evaluate_windowed_math_guard(
    text: str,
    constraints: list[NumericalConstraint],
) -> tuple[bool, list[ConstraintEvaluation]]:
    """`passed` is a soft signal (anchor mentioned + some number nearby, even
    if it didn't satisfy the comparison, or no number at all near a
    qualitative mention) — not a filter decision. Callers should log this,
    not exclude on it; final validation belongs to the analysis agent."""
    if not constraints:
        return True, []

    evaluations = [evaluate_constraint(text, c) for c in constraints]
    passed = any(item.passed or item.observed_values for item in evaluations)
    return passed, evaluations


def note_passes_guard(text: str, constraints: list[NumericalConstraint]) -> bool:
    passed, _ = evaluate_windowed_math_guard(text, constraints)
    return passed
