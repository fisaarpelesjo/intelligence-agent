"""A rule applied to the wrong aggregation class — T021 (`FR-010`, `SC-006`).

`004` measured the three classes as not interchangeable. Averaging across them is
the failure this refusal exists to make unreachable, and **naming the class the
rule was written for** is what makes the refusal actionable: *"wrong class"* alone
sends an operator to guess which of the three was meant.
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
from anomaly_investigation.detect import ThresholdOutcome, ThresholdVerdict, assess_threshold

pytestmark = pytest.mark.unit


def _rule(*, aggregation: AggregationClass) -> Rule:
    return Rule(
        rule_id="trials_drop",
        metric="trials",
        method=DetectionMethod.PERCENTAGE_CHANGE,
        aggregation_class=aggregation,
        formula_id="period_over_period",
        threshold=Decimal("10"),
        tolerance=Decimal("0.01"),
        period="july_2026",
        baseline_period="june_2026",
    )


@pytest.mark.parametrize(
    ("written_for", "observed_as"),
    [
        (AggregationClass.COUNT, AggregationClass.RATIO),
        (AggregationClass.RATIO, AggregationClass.SNAPSHOT),
        (AggregationClass.SNAPSHOT, AggregationClass.COUNT),
    ],
)
def test_a_rule_applied_to_another_class_is_refused(
    written_for: AggregationClass, observed_as: AggregationClass
) -> None:
    """Refused, **and the refusal names the class it was written for** (`SC-006`)."""
    outcome = assess_threshold(
        _rule(aggregation=written_for), observed=Decimal("99"), observed_class=observed_as
    )
    assert outcome.verdict is ThresholdVerdict.REFUSED
    assert outcome.reason_code is AnomalyReasonCode.ANOMALY_RULE_AGGREGATION_CLASS_MISMATCH
    assert outcome.written_for is written_for


def test_the_matching_class_is_not_refused() -> None:
    """Without this, the refusals above would pass over a function that refuses
    everything."""
    outcome = assess_threshold(
        _rule(aggregation=AggregationClass.COUNT),
        observed=Decimal("99"),
        observed_class=AggregationClass.COUNT,
    )
    assert outcome.verdict is ThresholdVerdict.CROSSED


def test_a_class_mismatch_reports_no_numbers() -> None:
    """The comparison did not run, so there is nothing to report about it.

    Reporting an observed value beside a refusal invites a reader to use it, and
    that value was never compared to anything.
    """
    outcome = assess_threshold(
        _rule(aggregation=AggregationClass.COUNT),
        observed=Decimal("99"),
        observed_class=AggregationClass.RATIO,
    )
    assert outcome.observed is None
    assert outcome.threshold is None


def test_a_class_mismatch_must_name_the_class() -> None:
    """The type refuses the incomplete refusal, rather than a reviewer noticing it."""
    with pytest.raises(ValidationError):
        ThresholdOutcome(
            rule_id="r",
            verdict=ThresholdVerdict.REFUSED,
            reason_code=AnomalyReasonCode.ANOMALY_RULE_AGGREGATION_CLASS_MISMATCH,
        )
