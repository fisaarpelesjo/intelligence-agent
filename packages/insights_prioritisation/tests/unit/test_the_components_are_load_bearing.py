"""Removing a component changes the position — T012 (`SC-001`).

**A component whose removal changes nothing is either undeclared or decorative, and
both are findings.** So this file does not assert that the registry HAS two components:
it **orders findings** and asserts which one came first, then changes exactly one
component and asserts the order changed with it.

That distinction is the lesson `G-1` cost the `005` branch a cycle to learn, one file
away: *a check that describes a structure instead of driving a behaviour passes while
the behaviour rots.* A node asserting `len(DECLARED_COMPONENTS) == 2` would survive a
ranking that ignored the second one entirely.

## What the owner decided, and what each node here holds down

`nota = (magnitude * confidence, reach * confidence)`, compared **term by term**:
magnitude decides, reach breaks its ties, and there is no total anywhere. Confidence is
`completeness_ratio` — **completeness of the data, not certainty about the anomaly** —
and `None` refuses rather than standing in as 1.0.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from insights_prioritisation.contracts import (
    ComponentAbsence,
    PrioritisedFinding,
    PriorityComponent,
    PriorityContractViolation,
    PriorityReasonCode,
)
from insights_prioritisation.score import (
    CONFIDENCE_FACTOR_NAME,
    DECLARED_ORDER,
    confidence_of,
    rank_findings,
    rank_key,
    weigh,
)

pytestmark = pytest.mark.unit

INSTANT = datetime(2026, 8, 27, 4, 0, tzinfo=UTC)


def _placed(identifier: str, magnitude: str, reach: str) -> PrioritisedFinding:
    """One finding already placed, with both declared components carrying a value."""
    return PrioritisedFinding(
        finding_id=identifier,
        components=(
            PriorityComponent(
                name="magnitude", read_from="candidate_finding", value=Decimal(magnitude)
            ),
            PriorityComponent(name="reach", read_from="investigation", value=Decimal(reach)),
        ),
        reading_instant=INSTANT,
    )


class _Freshness:
    def __init__(self, ratio: float | None) -> None:
        self.completeness_ratio = ratio


class _Candidate:
    """The two attributes this feature reads off a candidate. Nothing else is touched."""

    def __init__(self, ratio: float | None) -> None:
        self.freshness = _Freshness(ratio)


def test_the_order_is_the_declared_order_and_not_alphabetical() -> None:
    """A premise, asserted so the nodes below cannot pass for the wrong reason."""
    assert DECLARED_ORDER == ("magnitude", "reach"), DECLARED_ORDER


def test_magnitude_decides_the_position() -> None:
    """**Driving the behaviour: two findings ordered, and the first one named.**"""
    ranked = rank_findings([_placed("small", "1.0", "9"), _placed("large", "5.0", "1")])
    assert [f.finding_id for f in ranked] == ["large", "small"]


def test_changing_only_magnitude_changes_the_position() -> None:
    """`SC-001` for the first component: remove its advantage and the order flips.

    Reach is held identical across both findings, so nothing but magnitude can explain
    the change — which is what makes this an assertion about magnitude rather than about
    ranking in general.
    """
    before = rank_findings([_placed("a", "1.0", "4"), _placed("b", "5.0", "4")])
    after = rank_findings([_placed("a", "9.0", "4"), _placed("b", "5.0", "4")])
    assert [f.finding_id for f in before] == ["b", "a"]
    assert [f.finding_id for f in after] == ["a", "b"], (
        "magnitude changed and the order did not; the first component is decorative"
    )


def test_changing_only_reach_changes_the_position_where_magnitude_ties() -> None:
    """`SC-001` for the second component, and the term-by-term rule at the same time.

    **Reach can only speak where magnitude ties**, which is what "compared term by term"
    means. Both findings carry the same magnitude here, so the position is reach's to
    decide — and if it decided nothing, reach would be declared and inert.
    """
    ranked = rank_findings([_placed("narrow", "3.0", "1"), _placed("broad", "3.0", "7")])
    assert [f.finding_id for f in ranked] == ["broad", "narrow"], (
        "reach changed and the order did not; the second component is decorative"
    )


def test_reach_cannot_overturn_magnitude() -> None:
    """The other half of term by term, and the half a sum would break.

    A composed score would let a large reach buy a position magnitude did not earn.
    Nine times a small magnitude still loses to a large one, because the second term is
    never consulted while the first differs.
    """
    ranked = rank_findings([_placed("huge_reach", "1.0", "99"), _placed("big", "2.0", "1")])
    assert [f.finding_id for f in ranked] == ["big", "huge_reach"]


def test_a_finding_missing_a_declared_component_is_not_ranked_lower_but_refused() -> None:
    """**Not ranked last — not ranked at all.**

    Ranking a finding by the components that happened to arrive orders findings by
    availability, which is the `005` defect this package was written against: an absence
    read as a value reported minus one hundred per cent instead of *incomplete day*.
    """
    partial = PrioritisedFinding(
        finding_id="partial",
        components=(
            PriorityComponent(
                name="magnitude", read_from="candidate_finding", value=Decimal("4.0")
            ),
        ),
        reading_instant=INSTANT,
    )
    with pytest.raises(PriorityContractViolation):
        rank_key(partial)


def test_confidence_multiplies_each_component_and_never_a_total() -> None:
    """`D-A2`: the factor lands on every term, and the terms stay separate."""
    components = (
        PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal("4")),
        PriorityComponent(name="reach", read_from="investigation", value=Decimal("10")),
    )
    weighted = weigh(components, Decimal("0.5"))
    assert [c.value for c in weighted] == [Decimal("2.0"), Decimal("5.0")]
    assert [c.name for c in weighted] == ["magnitude", "reach"], (
        "weighing collapsed the components into one term; D-A refuses a composed score"
    )


def test_a_weighted_component_says_what_weighted_it() -> None:
    """**`FR-005` forbids the silent answer, and this is where it would be silent.**

    `completeness_ratio` measures COMPLETENESS OF THE DATA, not certainty about the
    anomaly. The owner decided with that stated, so the output must carry the name of
    what was measured — calling it *"confidence"* while measuring completeness is the
    class of defect this feature exists to prevent.
    """
    weighted = weigh(
        (PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal("4")),),
        Decimal("0.25"),
    )
    assert weighted[0].weighted_by == CONFIDENCE_FACTOR_NAME
    assert CONFIDENCE_FACTOR_NAME == "data_completeness_ratio", (
        "the factor's name no longer says what was measured"
    )


def test_confidence_pushes_down_and_never_promotes() -> None:
    """`D-C`: a big doubtful finding DESCENDS and stays visible. It is not a veto.

    The bound is `001`'s, not ours: `completeness_ratio` is declared with `ge=0.0` and
    `le=1.0`, so a factor cannot exceed one and weighting cannot lift a finding above
    where it stood unweighted.
    """
    doubtful = weigh(
        (PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal("10")),),
        Decimal("0.2"),
    )
    weighted = doubtful[0].value
    # Narrowed rather than compared through an optional: `value` is `Decimal | None`, and
    # `None < Decimal` is not an ordering -- it is a `TypeError` waiting for the day a
    # component comes back absent here. Asserting presence first names that day.
    assert weighted is not None, "the weighted component lost its value entirely"
    assert weighted == Decimal("2.0")
    assert weighted < Decimal("10"), "confidence promoted a finding"
    assert doubtful[0].absence is None, "confidence vetoed a finding instead of lowering it"


def test_an_unmeasured_confidence_refuses_instead_of_assuming_one() -> None:
    """**`D-C1`, and it is the zero-substitution defect running the other way.**

    Assuming 1.0 promotes an unmeasured finding to full confidence in silence, and the
    output looks exactly like one where completeness was measured and found perfect.
    """
    assert confidence_of(_Candidate(None)) is None
    refused = weigh(
        (PriorityComponent(name="magnitude", read_from="candidate_finding", value=Decimal("4")),),
        None,
    )
    assert refused[0].value is None
    assert refused[0].absence is not None
    assert refused[0].absence.reason is PriorityReasonCode.PRIORITY_CONFIDENCE_NOT_MEASURED


def test_the_confidence_number_is_the_candidates_own_completeness() -> None:
    """Read, never recomputed — and converted through `str` so no precision is invented."""
    assert confidence_of(_Candidate(0.9)) == Decimal("0.9")
    assert confidence_of(object()) is None, "a finding with no freshness answered a number"


def test_an_already_absent_component_keeps_its_own_reason() -> None:
    """The more specific reason survives.

    *This component could not be obtained* says more than *the weight could not be
    applied*, and overwriting it would report a missing investigation as a missing
    freshness record.
    """
    absent = PriorityComponent(
        name="reach",
        read_from="investigation",
        # The contract's own type rather than a mapping the model would coerce: a dict passes
        # at runtime and says nothing about which fields the absence really carries.
        absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
    )
    carried = weigh((absent,), None)
    assert carried[0].absence is not None
    assert carried[0].absence.reason is PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE


def test_direction_does_not_participate_in_the_order() -> None:
    """**`D-A` made direction a FILTER, and a decision stays prose until a node holds it.**

    A fall and a rise do not compete inside one rule, so direction decides **which
    findings are compared at all** and never **which comes first**. The structural half
    is that it is not in the declared order; the behavioural half is that the key is
    built from the declared components and from nothing else, so no attribute of a
    finding outside that list can reach the comparison.
    """
    assert "direction" not in DECLARED_ORDER

    first = _placed("a", "3.0", "5")
    second = PrioritisedFinding(
        finding_id="b",
        components=first.components,
        reading_instant=INSTANT,
        caveats=("a caveat one carries and the other does not",),
    )
    assert rank_key(first) == rank_key(second), (
        "two findings with identical components ranked differently, so something "
        "outside the declared components is reaching the order"
    )


def test_the_cross_class_normalisation_is_named_in_the_output() -> None:
    """`D-B` chose *together, by z-score per metric*, and `FR-005` forbids the silent form.

    An ordering that mixes aggregation classes carries the basis by name, so a reader
    can check which scale produced the order they are shown.
    """
    from anomaly_investigation.contracts import AggregationClass

    from insights_prioritisation.contracts import Normalisation
    from insights_prioritisation.order import single_normalised_ordering
    from insights_prioritisation.score.rank import Z_SCORE_PER_METRIC

    basis = Normalisation(
        basis=Z_SCORE_PER_METRIC,
        covers=(AggregationClass.COUNT, AggregationClass.SNAPSHOT),
    )
    ordering = single_normalised_ordering(
        [(_placed("a", "3.0", "5"),)],
        normalisation=basis,
        classes_present=(AggregationClass.COUNT, AggregationClass.SNAPSHOT),
    )
    assert ordering.normalisation is not None
    assert ordering.normalisation.basis == "z_score_per_metric", (
        "the ordering does not say which scale it used, which is the silent answer FR-005 forbids"
    )


def test_the_ranking_would_notice_a_component_that_did_nothing() -> None:
    """**Proof this file bites**, rather than a claim that it does.

    A key built from magnitude alone — the shape of a decorative second component — is
    run through the same comparison, and the pair that reach separates comes back in the
    order it was given instead of reordered.
    """
    findings = [_placed("narrow", "3.0", "1"), _placed("broad", "3.0", "7")]

    def _magnitude(finding: PrioritisedFinding) -> Decimal:
        """The magnitude of one finding, refusing the absent case rather than sorting on it.

        `PriorityComponent.value` is `Decimal | None`, so a key function returning it directly
        sorts an optional -- which is not an ordering at all the moment one is absent. Here
        every finding is built with a magnitude, and saying so is what makes the key total.
        """
        value = next(c.value for c in finding.components if c.name == "magnitude")
        assert value is not None, f"{finding.finding_id} carries no magnitude to sort on"
        return value

    magnitude_only = sorted(findings, key=_magnitude, reverse=True)
    assert [f.finding_id for f in magnitude_only] == ["narrow", "broad"]
    assert [f.finding_id for f in rank_findings(findings)] == ["broad", "narrow"], (
        "the declared ranking agrees with a ranking that ignores reach, so this file "
        "cannot tell a load-bearing component from a decorative one"
    )
