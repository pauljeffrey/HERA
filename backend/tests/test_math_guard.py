"""Tests for windowed math guard."""

from app.models.search import NumericalConstraint, NumericalOperator
from app.services.funnel.math_guard import evaluate_windowed_math_guard, note_passes_guard


def test_lvef_window_matches_near_anchor_not_unrelated_number():
    text = (
        "Patient heart rate is 85 bpm. History of heart failure. "
        "Current LVEF is 28% on repeat echocardiogram."
    )
    constraint = NumericalConstraint(
        parameter_name="LVEF",
        triggers=["lvef", "ejection fraction"],
        operator=NumericalOperator.LTE,
        target_value=35,
        unit_regex=r"%|percent",
        window_chars=80,
    )
    passed, evaluations = evaluate_windowed_math_guard(text, [constraint])
    assert passed
    assert evaluations[0].observed_values


def test_guard_reports_but_does_not_exclude_value_outside_threshold():
    """The guard is informational only (see math_guard module docstring) — a
    value that fails the comparison still yields a soft `note_passes_guard`
    pass (something relevant was found near the anchor), while the
    per-constraint evaluation still records that it didn't satisfy the
    comparison. Final validation belongs to the analysis agent."""
    text = "Echo shows LVEF 42% with mild symptoms."
    constraint = NumericalConstraint(
        parameter_name="LVEF",
        triggers=["lvef"],
        operator=NumericalOperator.LTE,
        target_value=35,
        unit_regex=r"%",
    )
    passed, evaluations = evaluate_windowed_math_guard(text, [constraint])
    assert passed  # soft signal: something relevant was observed
    assert not evaluations[0].passed  # but 42 does not satisfy <=35
    assert 42.0 in evaluations[0].observed_values
    assert note_passes_guard(text, [constraint])
