"""Claims are built behind a port, and what comes back is checked (owner item A).

Step 16 assembles an answer from claims and nothing built them: `ask()` passed `claims=()` against
`AnalyticsAnswer.claims` requiring at least one, so **no question could be answered through that
entry point**, whatever the governed content said. The sixth seam closed it.

## What is asserted here

That a claim naming something the plan did not authorise and the result did not label refuses;
that a unit no column declared refuses; that legitimate subjects — an authorised metric, an
authorised dimension, a label the result itself carried — are accepted; and that the guard reads
its allowlist
off the plan and the result rather than accepting one.

## Why the fabrication check is the important one

The port receives the plan, the result and the claim classes. It does **not** receive the question
text, so a constructor cannot read what the user typed. `assert_claims_are_authorised` is what makes
that structurally observable instead of a rule somebody remembers: a subject smuggled in from
anywhere else fails the allowlist, whatever its source.

An empty result is not tested for a bespoke refusal here, and that is deliberate: it produces no
claims, and an answer with no claims is refused by the contract. The refusal already exists and a
second one would be a second place for it to stop being raised.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.contracts.result import (
    AnalyticsResult,
    Completeness,
    ResultCell,
    ResultColumn,
    ResultRow,
)

from analytics_interaction.answer.claims_port import assert_claims_are_authorised
from analytics_interaction.contracts._base import ContractViolation, LocalizedRef
from analytics_interaction.contracts.answer import AnswerClaim, ClaimClass
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode

pytestmark = pytest.mark.unit

METRIC = "installs"
DIMENSION = "platform"
UNIT = "installs"

PLAN = AnalyticsQuery(
    metrics=(METRIC,),
    dimensions=(DIMENSION,),
    date_range=DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)),
)

RESULT = AnalyticsResult(
    columns=(
        ResultColumn(identifier=DIMENSION, unit="label", is_metric=False),
        ResultColumn(identifier=METRIC, unit=UNIT, is_metric=True),
    ),
    rows=(
        ResultRow(labels=("android",), cells=(ResultCell(value=Decimal(18432)),)),
        ResultRow(labels=("ios",), cells=(ResultCell(value=Decimal(12105)),)),
    ),
    completeness=Completeness.COMPLETE,
)

EMPTY_RESULT = AnalyticsResult(
    columns=(ResultColumn(identifier=METRIC, unit=UNIT, is_metric=True),),
    rows=(),
    completeness=Completeness.EMPTY,
)


def _ref() -> LocalizedRef:
    return LocalizedRef(code="test.claim", language="pt-BR", content_version="test-only")


def _factual(subject: str, *, unit: str | None = UNIT, value: int = 1) -> AnswerClaim:
    return AnswerClaim(
        claim_class=ClaimClass.FACTUAL_RESULT,
        subject=subject,
        value=Decimal(value),
        unit=unit,
        message=_ref(),
    )


def _limitation(subject: str) -> AnswerClaim:
    return AnswerClaim(claim_class=ClaimClass.LIMITATION, subject=subject, message=_ref())


def _check(*claims: AnswerClaim, result: AnalyticsResult = RESULT) -> None:
    assert_claims_are_authorised(claims, plan=PLAN, result=result)


class TestASubjectMustBeTraceable:
    """The allowlist is the plan's identifiers plus the labels the result carried. Nothing else."""

    def test_an_authorised_metric_is_accepted(self) -> None:
        _check(_factual(METRIC))

    def test_an_authorised_dimension_is_accepted(self) -> None:
        """An identifier the plan authorised, whether or not the result labelled it."""
        _check(_limitation(DIMENSION))

    def test_a_label_the_result_carried_is_accepted(self) -> None:
        """Row labels are result content, not plan content, and both are legitimate sources."""
        _check(_factual("android"), _factual("ios"))

    def test_a_fabricated_subject_refuses(self) -> None:
        """A subject from neither source is a fabricated identifier."""
        with pytest.raises(ContractViolation) as raised:
            _check(_factual("windows_phone"))
        assert raised.value.code is InterpretationReasonCode.IDENTIFIER_FABRICATED

    def test_a_span_of_a_question_cannot_arrive_as_a_subject(self) -> None:
        """The property the check exists for, stated as the case it prevents.

        The port never receives the question, so this cannot happen by construction; the assertion
        is what makes the absence observable rather than argued.
        """
        with pytest.raises(ContractViolation) as raised:
            _check(_limitation("quantas instalacoes tivemos em julho de 2026"))
        assert raised.value.code is InterpretationReasonCode.IDENTIFIER_FABRICATED

    def test_a_label_absent_from_this_result_refuses_even_if_plausible(self) -> None:
        """`ios` is a real platform, absent from *this* result, so not claimable from it."""
        with pytest.raises(ContractViolation) as raised:
            _check(_factual("ios"), result=EMPTY_RESULT)
        assert raised.value.code is InterpretationReasonCode.IDENTIFIER_FABRICATED

    def test_one_bad_claim_among_good_ones_still_refuses(self) -> None:
        """Nothing partial is released, so the whole tuple refuses rather than being filtered."""
        with pytest.raises(ContractViolation):
            _check(_factual("android"), _factual("windows_phone"), _factual("ios"))


class TestAUnitMustBeDeclaredByTheResult:
    """A number in a unit no column declared is a number whose meaning was chosen afterwards."""

    def test_a_declared_metric_unit_is_accepted(self) -> None:
        _check(_factual("android", unit=UNIT))

    def test_an_undeclared_unit_refuses(self) -> None:
        with pytest.raises(ContractViolation) as raised:
            _check(_factual("android", unit="sessions"))
        assert raised.value.code is InterpretationReasonCode.IDENTIFIER_FABRICATED

    def test_a_claim_carrying_no_unit_is_accepted(self) -> None:
        """`LIMITATION` and `INTERPRETATION` carry no unit, and absence is not a violation."""
        _check(_limitation(METRIC))

    def test_a_dimension_column_unit_is_declared_too(self) -> None:
        """The dimension column declares `label`, so a claim may present it.

        Asserted because the allowlist is built from **every** column rather than the metric ones:
        reading only metric columns would refuse a legitimate claim about a labelled figure.
        """
        _check(_factual("android", unit="label"))


class TestTheAllowlistIsReadAndNotSupplied:
    """A caller that supplied the allowlist would be a caller that could widen it."""

    def test_an_empty_claim_tuple_is_accepted(self) -> None:
        """Nothing to check is not a failure. Assembly is what refuses an answer with no claims."""
        _check()

    def test_the_plan_alone_does_not_authorise_a_label(self) -> None:
        """Swapping in a result with no rows removes the labels, and the same claim then refuses.

        This is the assertion that the result is genuinely read: if the allowlist came from the plan
        only, the two calls below would agree.
        """
        _check(_factual("android"))
        with pytest.raises(ContractViolation):
            _check(_factual("android"), result=EMPTY_RESULT)

    def test_the_plan_is_genuinely_read(self) -> None:
        """A metric this plan does not carry refuses, so the plan is not being ignored either."""
        with pytest.raises(ContractViolation):
            _check(_limitation("sessions"))
