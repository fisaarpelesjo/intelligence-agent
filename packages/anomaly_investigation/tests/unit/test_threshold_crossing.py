"""Crossing, and not crossing — T020 (`FR-001`).

The positive and negative results of a comparison that **ran**. The two refusal
cases live in their own files, because the task ledger promised three artefacts
and a promise kept only where convenient is not a promise -- the repository's
artifact guard caught exactly that when these were written as one file.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from anomaly_investigation.contracts import (
    AggregationClass,
    AnomalyReasonCode,
    DetectionMethod,
    Rule,
)
from anomaly_investigation.detect import (
    GOVERNED_METHODS,
    ThresholdOutcome,
    ThresholdVerdict,
    assess_threshold,
    method_or_refusal,
)

pytestmark = pytest.mark.unit


def _rule(
    *,
    threshold: str = "10",
    aggregation: AggregationClass = AggregationClass.COUNT,
    method: DetectionMethod = DetectionMethod.PERCENTAGE_CHANGE,
) -> Rule:
    return Rule(
        rule_id="trials_drop",
        metric="trials",
        method=method,
        aggregation_class=aggregation,
        formula_id="period_over_period",
        threshold=Decimal(threshold),
        tolerance=Decimal("0.01"),
        period="july_2026",
        baseline_period="june_2026",
    )


# --------------------------------------------------------------------------- #
# T020 -- crossing, and not crossing
# --------------------------------------------------------------------------- #


def test_a_movement_over_the_threshold_crosses() -> None:
    outcome = assess_threshold(
        _rule(), observed=Decimal("12"), observed_class=AggregationClass.COUNT
    )
    assert outcome.verdict is ThresholdVerdict.CROSSED
    assert outcome.observed == Decimal("12")
    assert outcome.threshold == Decimal("10")


def test_a_movement_under_the_threshold_does_not_cross() -> None:
    outcome = assess_threshold(
        _rule(), observed=Decimal("3"), observed_class=AggregationClass.COUNT
    )
    assert outcome.verdict is ThresholdVerdict.DID_NOT_CROSS
    assert outcome.reason_code is None


def test_the_threshold_is_a_magnitude_so_a_drop_crosses_too() -> None:
    """A rule about *movement* fires on a fall as well as a rise.

    Stated as its own test because the alternative — comparing the signed value —
    would make every downward movement invisible, and a KPI that only ever falls
    would read as permanently quiet.
    """
    outcome = assess_threshold(
        _rule(), observed=Decimal("-12"), observed_class=AggregationClass.COUNT
    )
    assert outcome.verdict is ThresholdVerdict.CROSSED


def test_the_boundary_is_inclusive_and_that_is_a_decision() -> None:
    """Exactly at the threshold crosses.

    Written down because a boundary nobody stated is a boundary somebody will
    change by accident: a rule saying *"alert at 10%"* is read by an operator as
    *"10% alerts"*.
    """
    outcome = assess_threshold(
        _rule(), observed=Decimal("10"), observed_class=AggregationClass.COUNT
    )
    assert outcome.verdict is ThresholdVerdict.CROSSED


# --------------------------------------------------------------------------- #
# The outcome defends itself
# --------------------------------------------------------------------------- #


def test_a_refusal_without_a_reason_is_refused_by_the_type() -> None:
    with pytest.raises(ValidationError):
        ThresholdOutcome(rule_id="r", verdict=ThresholdVerdict.REFUSED)


def test_a_comparison_that_ran_reports_both_numbers() -> None:
    with pytest.raises(ValidationError):
        ThresholdOutcome(rule_id="r", verdict=ThresholdVerdict.CROSSED, observed=Decimal("1"))


def test_a_class_mismatch_must_name_the_class() -> None:
    with pytest.raises(ValidationError):
        ThresholdOutcome(
            rule_id="r",
            verdict=ThresholdVerdict.REFUSED,
            reason_code=AnomalyReasonCode.ANOMALY_RULE_AGGREGATION_CLASS_MISMATCH,
        )


# --------------------------------------------------------------------------- #
# The governed method list
# --------------------------------------------------------------------------- #


def test_the_governed_methods_are_the_baselines_eight() -> None:
    assert len(GOVERNED_METHODS) == 8
    assert DetectionMethod.PERCENTAGE_CHANGE in GOVERNED_METHODS


def test_a_method_outside_the_list_is_refused_by_name() -> None:
    resolved, reason = method_or_refusal("bayesian_change_point")
    assert resolved is None
    assert reason is AnomalyReasonCode.ANOMALY_RULE_METHOD_NOT_GOVERNED


def test_a_governed_method_resolves() -> None:
    resolved, reason = method_or_refusal("previous_month")
    assert resolved is DetectionMethod.PREVIOUS_MONTH
    assert reason is None
