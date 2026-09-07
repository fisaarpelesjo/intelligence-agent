"""The contracts refuse a candidate without its evidence — T012 (`FR-005`, `FR-009`).

Five entities, no behaviour. What is asserted here is that **the shapes refuse**,
because `FR-005` says a candidate without its evidence *must not be produced* — and
a requirement enforced by review is a requirement enforced sometimes.

The other half is `FR-009`: **a run with zero candidates is a completed run**, and
it must stay distinguishable from a run that failed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from analytics_interaction.comparison.direction import Direction
from analytics_interaction.contracts import DerivedFigure
from analytics_query.contracts.comparable_window import ComparableWindow
from pydantic import ValidationError
from semantic_catalog.freshness.external import CompletenessStatus, FreshnessRecord

from anomaly_investigation.contracts import (
    REQUIRED_CAUSALITY_WARNING,
    AggregationClass,
    AnomalyReasonCode,
    CandidateFinding,
    ClaimType,
    DetectionMethod,
    Investigation,
    Outcome,
    ReconciliationVerdict,
    Rule,
    Run,
    RunOutcome,
    SegmentContribution,
    SourceValue,
    Withholding,
    anomaly_outcome_for,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


def _window(start: str = "2026-07-01", end: str = "2026-07-31") -> ComparableWindow:
    return ComparableWindow(
        start=datetime.fromisoformat(start).date(),
        end=datetime.fromisoformat(end).date(),
        reason="catalog-resolved window",
        sources=("semantic.trials",),
    )


def _freshness(status: CompletenessStatus = CompletenessStatus.COMPLETE) -> FreshnessRecord:
    return FreshnessRecord(source="trials", status=status, observed_at=AT)


def _figure() -> DerivedFigure:
    return DerivedFigure(
        value=Decimal("523"),
        unit="count",
        derived_from=("trials_july", "trials_june"),
        basis="period_over_period",
    )


def _candidate(**overrides: object) -> CandidateFinding:
    data: dict[str, object] = {
        "rule_id": "trials_drop",
        "figure": _figure(),
        "baseline_value": Decimal("470"),
        "direction": Direction.INCREASE,
        "primary_window": _window(),
        "baseline_window": _window("2026-06-01", "2026-06-30"),
        "freshness": _freshness(),
        "claim_type": ClaimType.TEMPORAL_ASSOCIATION,
        "causality_warning": REQUIRED_CAUSALITY_WARNING,
    }
    data.update(overrides)
    return CandidateFinding(**data)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# A candidate cannot exist without its evidence
# --------------------------------------------------------------------------- #


def test_a_complete_candidate_is_constructible() -> None:
    """The negative tests below would pass over a shape nothing can satisfy."""
    candidate = _candidate()
    assert candidate.rule_id == "trials_drop"
    assert candidate.figure.derived_from == ("trials_july", "trials_june")


@pytest.mark.parametrize(
    "missing",
    [
        "rule_id",
        "figure",
        "baseline_value",
        "direction",
        "primary_window",
        "baseline_window",
        "freshness",
        "claim_type",
        "causality_warning",
    ],
)
def test_every_field_is_required(missing: str) -> None:
    """No default anywhere. **A candidate with a hole where its proof should be is
    not a weaker candidate — it is not a candidate.**"""
    data = {
        "rule_id": "trials_drop",
        "figure": _figure(),
        "baseline_value": Decimal("470"),
        "direction": Direction.INCREASE,
        "primary_window": _window(),
        "baseline_window": _window("2026-06-01", "2026-06-30"),
        "freshness": _freshness(),
        "claim_type": ClaimType.TEMPORAL_ASSOCIATION,
        "causality_warning": REQUIRED_CAUSALITY_WARNING,
    }
    del data[missing]
    with pytest.raises(ValidationError):
        CandidateFinding(**data)  # type: ignore[arg-type]


def test_a_candidate_carries_no_score_and_no_narrative() -> None:
    """`FR-013` as a structural property, not a review rule.

    Scoring, ranking and narrating are pipeline steps 6 to 9 and belong to the
    owner's item 7. ``extra="forbid"`` is what makes adding one here fail rather
    than pass unnoticed.
    """
    for field in ("score", "severity", "summary", "title", "cause"):
        with pytest.raises(ValidationError):
            _candidate(**{field: "anything"})


@pytest.mark.parametrize("wrong", ["", "Os dados podem indicar associação temporal.", "  "])
def test_the_warning_is_compared_by_equality(wrong: str) -> None:
    """A paraphrase is refused, and so is a prefix.

    This feature **transports** the sentence. The moment a check accepted
    something close, the feature would be composing it.
    """
    with pytest.raises(ValidationError):
        _candidate(causality_warning=wrong)


def test_the_warning_is_refused_even_when_the_governed_text_is_inside_it() -> None:
    """Containment is not equality, and this is the case that separates them."""
    with pytest.raises(ValidationError):
        _candidate(causality_warning=f"Atenção: {REQUIRED_CAUSALITY_WARNING}")


# --------------------------------------------------------------------------- #
# A run with zero candidates is a completed run
# --------------------------------------------------------------------------- #


def test_zero_candidates_is_a_completed_run() -> None:
    run = Run(run_id="r1", instant=AT, outcome=RunOutcome.COMPLETED)
    assert run.candidates == ()
    assert run.outcome is RunOutcome.COMPLETED


def test_quiet_and_withheld_are_not_the_same_silence() -> None:
    """`SC-002` made structural: *"nothing moved"* and *"we could not tell"* are
    different lists, and a reader can tell which happened."""
    run = Run(
        run_id="r2",
        instant=AT,
        rules_considered=("quiet_rule", "stale_rule"),
        quiet=("quiet_rule",),
        withholdings=(
            Withholding(
                rule_id="stale_rule",
                reason_code=AnomalyReasonCode.ANOMALY_FRESHNESS_STALE,
                freshness=_freshness(CompletenessStatus.DELAYED),
            ),
        ),
        outcome=RunOutcome.COMPLETED,
    )
    assert run.quiet == ("quiet_rule",)
    assert run.withholdings[0].reason_code is AnomalyReasonCode.ANOMALY_FRESHNESS_STALE


def test_a_completed_run_accounts_for_every_rule_it_considered() -> None:
    """A rule that vanishes from the report reads as *"nothing moved"*.

    That is the one inference this feature must never let a reader make by
    accident, so the shape refuses the run rather than the reader having to notice.
    """
    with pytest.raises(ValidationError):
        Run(
            run_id="r3",
            instant=AT,
            rules_considered=("considered_but_never_reported",),
            outcome=RunOutcome.COMPLETED,
        )


def test_a_failed_run_is_exempt_from_accounting() -> None:
    """It stopped. Claiming it can account for every rule would be the false half."""
    run = Run(
        run_id="r4",
        instant=AT,
        rules_considered=("never_reached",),
        outcome=RunOutcome.FAILED,
    )
    assert run.outcome is RunOutcome.FAILED


# --------------------------------------------------------------------------- #
# The investigation reports absence rather than inventing agreement
# --------------------------------------------------------------------------- #


def test_no_declared_dimension_forces_not_attempted() -> None:
    """``RECONCILED`` over an empty set is **vacuously true** — agreement with nobody."""
    empty = Investigation(
        rule_id="trials_drop",
        reconciliation=ReconciliationVerdict.NOT_ATTEMPTED,
        claim_type=ClaimType.CORRELATION,
        causality_warning=REQUIRED_CAUSALITY_WARNING,
    )
    assert empty.dimensions_declared == ()
    assert empty.contributions == ()

    with pytest.raises(ValidationError):
        Investigation(
            rule_id="trials_drop",
            reconciliation=ReconciliationVerdict.RECONCILED,
            claim_type=ClaimType.CORRELATION,
            causality_warning=REQUIRED_CAUSALITY_WARNING,
        )


def test_a_verdict_not_attempted_carries_no_residual() -> None:
    with pytest.raises(ValidationError):
        Investigation(
            rule_id="trials_drop",
            reconciliation=ReconciliationVerdict.NOT_ATTEMPTED,
            residual=Decimal("1"),
            claim_type=ClaimType.CORRELATION,
            causality_warning=REQUIRED_CAUSALITY_WARNING,
        )


def test_a_suppressed_segment_carries_no_value() -> None:
    """**A suppressed cell is not a zero**, and it is not a number either.

    Allowing both would let a caller read the figure and ignore the flag, which is
    how a suppression becomes a movement.
    """
    ok = SegmentContribution(
        dimension="platform",
        segment_label=SourceValue(text="iOS", origin="platform"),
        suppressed=True,
        contribution=Decimal("0.4"),
        claim_type=ClaimType.CORRELATION,
    )
    assert ok.value is None

    with pytest.raises(ValidationError):
        SegmentContribution(
            dimension="platform",
            segment_label=SourceValue(text="iOS", origin="platform"),
            value=Decimal("12"),
            suppressed=True,
            contribution=Decimal("0.4"),
            claim_type=ClaimType.CORRELATION,
        )


def test_source_text_travels_as_a_value_and_is_never_edited() -> None:
    """A label carrying causal language is still delivered — as a named field's value."""
    label = SourceValue(text="queda causada por mudança de preço", origin="product")
    segment = SegmentContribution(
        dimension="product",
        segment_label=label,
        value=Decimal("3"),
        contribution=Decimal("0.9"),
        claim_type=ClaimType.CORRELATION,
    )
    assert segment.segment_label.text == "queda causada por mudança de preço"
    assert segment.segment_label.origin == "product"


# --------------------------------------------------------------------------- #
# The rule, and the namespace
# --------------------------------------------------------------------------- #


def test_a_rule_states_its_own_tolerance_and_a_finite_threshold() -> None:
    rule = Rule(
        rule_id="trials_drop",
        metric="trials",
        method=DetectionMethod.PERCENTAGE_CHANGE,
        aggregation_class=AggregationClass.COUNT,
        formula_id="period_over_period",
        threshold=Decimal("10"),
        tolerance=Decimal("0.01"),
        period="july_2026",
        baseline_period="june_2026",
    )
    assert rule.method is DetectionMethod.PERCENTAGE_CHANGE

    with pytest.raises(ValidationError):
        Rule(
            rule_id="nan_rule",
            metric="trials",
            method=DetectionMethod.ABSOLUTE_CHANGE,
            aggregation_class=AggregationClass.COUNT,
            formula_id="period_over_period",
            threshold=Decimal("NaN"),
            tolerance=Decimal("0"),
            period="july_2026",
            baseline_period="june_2026",
        )


def test_detection_methods_are_the_baselines_closed_eight() -> None:
    assert len(DetectionMethod) == 8


def test_every_reason_code_has_an_outcome() -> None:
    """A code missing from the map would default to nothing readable."""
    assert len(AnomalyReasonCode) == 19
    for code in AnomalyReasonCode:
        assert anomaly_outcome_for(code) in set(Outcome)
