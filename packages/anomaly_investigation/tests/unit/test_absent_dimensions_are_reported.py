"""Zero segments, and the investigation still reports — T027 (`FR-011`).

**This is why `Investigation` is an entity and not a set.** A set with no members
reports nothing, and `FR-011` requires reporting the *absence* of declared
dimensions rather than inventing one.

**And the absence is not a refusal.** We looked, and there was nothing declared to
look at — so the code is the namespace's single `ALLOW_WITH_CAVEAT`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from anomaly_investigation.contracts import (
    ANOMALY_REASON_CODE_OUTCOME,
    REQUIRED_CAUSALITY_WARNING,
    AnomalyReasonCode,
    ClaimType,
    Investigation,
    Outcome,
    ReconciliationVerdict,
    SegmentContribution,
    SourceValue,
)
from anomaly_investigation.investigate import investigate

pytestmark = pytest.mark.unit


def _segment() -> SegmentContribution:
    return SegmentContribution(
        dimension="game",
        segment_label=SourceValue(text="Fortnite", origin="game"),
        value=Decimal("10"),
        contribution=Decimal("10"),
        claim_type=ClaimType.CORRELATION,
    )


def test_no_declared_dimension_still_emits_an_investigation() -> None:
    """The requirement, literally: it reports rather than returning nothing."""
    outcome = investigate(
        "trials_drop",
        declared_dimensions=(),
        contributions=(),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.investigation.rule_id == "trials_drop"
    assert outcome.investigation.dimensions_declared == ()
    assert outcome.investigation.contributions == ()
    assert outcome.investigation.causality_warning == REQUIRED_CAUSALITY_WARNING


def test_the_absence_is_named_by_its_own_code() -> None:
    outcome = investigate(
        "trials_drop",
        declared_dimensions=(),
        contributions=(),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.reason_code is AnomalyReasonCode.ANOMALY_NO_DIMENSION_DECLARED


def test_the_absence_is_a_caveat_and_not_a_refusal() -> None:
    """**Nothing was refused.** We looked and there was nothing declared to look
    at, which is why this is the namespace's one `ALLOW_WITH_CAVEAT`.

    Classifying it `DENY` would tell an operator that something was blocked.
    """
    outcome = ANOMALY_REASON_CODE_OUTCOME[AnomalyReasonCode.ANOMALY_NO_DIMENSION_DECLARED]
    assert outcome is Outcome.ALLOW_WITH_CAVEAT


def test_an_empty_investigation_is_not_attempted_rather_than_reconciled() -> None:
    """`RECONCILED` over an empty set is **vacuously true** — agreement with nobody.

    The contract refuses any other verdict here, so this is belt and braces: the
    module must not even try to produce one.
    """
    outcome = investigate(
        "trials_drop",
        declared_dimensions=(),
        contributions=(),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.investigation.reconciliation is ReconciliationVerdict.NOT_ATTEMPTED
    assert outcome.investigation.residual is None


def test_the_contract_refuses_an_empty_investigation_that_claims_agreement() -> None:
    with pytest.raises(ValidationError):
        Investigation(
            rule_id="trials_drop",
            reconciliation=ReconciliationVerdict.RECONCILED,
            claim_type=ClaimType.CORRELATION,
            causality_warning=REQUIRED_CAUSALITY_WARNING,
        )


def test_contributions_without_a_declared_dimension_are_impossible() -> None:
    """A segment belongs to a dimension the catalog declared.

    The module never has to decide what a contribution with no dimension would
    mean, because the contract makes it unconstructible.
    """
    with pytest.raises(ValidationError):
        Investigation(
            rule_id="trials_drop",
            contributions=(_segment(),),
            reconciliation=ReconciliationVerdict.NOT_ATTEMPTED,
            claim_type=ClaimType.CORRELATION,
            causality_warning=REQUIRED_CAUSALITY_WARNING,
        )


def test_a_declared_dimension_with_segments_is_the_ordinary_case() -> None:
    """The refusals above would be vacuous if nothing satisfied the shape."""
    outcome = investigate(
        "trials_drop",
        declared_dimensions=("game",),
        contributions=(_segment(),),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.investigation.dimensions_declared == ("game",)
    assert outcome.reason_code is None


def test_a_dimension_declared_with_no_segments_found_still_reports() -> None:
    """The catalog declared a dimension and the warehouse returned no rows for it.

    **Different from no dimension declared**, and the difference matters: one says
    *nobody defined a breakdown*, the other says *the breakdown came back empty*.
    Neither invents a segment.
    """
    outcome = investigate(
        "trials_drop",
        declared_dimensions=("game",),
        contributions=(),
        total_movement=Decimal("10"),
        tolerance=Decimal("0.01"),
    )
    assert outcome.investigation.dimensions_declared == ("game",)
    assert outcome.investigation.contributions == ()
    assert outcome.investigation.reconciliation is ReconciliationVerdict.NOT_ATTEMPTED
    assert outcome.reason_code is None
