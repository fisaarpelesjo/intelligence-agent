"""The governed interval comes from a port, and the port's answer is checked (owner item B).

Step 7 used to be handed the interval as a pair of dates the caller had computed. The only caller is
`ask()`, so "the caller computes it" meant the calendar arithmetic would live in `interact.py` —
which `R-8` forbids, and which is why the owner authorized a resolver port instead.

## What is asserted here

That the resolver's answer becomes the resolved period; that the **two things a resolver may not
decide** are refused rather than accepted — the business time zone and the `D-18` inclusivity; that
an unknown boundary rule is the resolver's refusal to raise and not this feature's to guess; and
that an interval which does not order is refused before it can be mistaken for a resolution.

## What is deliberately not asserted here

**No month length.** Every interval below is written out. A test that computed July's last day would
be a test with a calendar in it, and the whole point of the port is that this package has none.

Every vocabulary is built in the test. Nothing reads `interpretation_governance/`, which carries
`instances: []` and stays so — a resolver cannot help a question whose expression is not governed,
and `test_period_in_question.py` covers that refusal.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.periods.canonical import CANONICAL_TIMEZONE

from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intent import GovernedInterval, PeriodConvention
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.governance.schemas import (
    ContentApproval,
    PeriodExpression,
    PeriodVocabulary,
)
from analytics_interaction.interpretation.period import resolve_period_in_question

pytestmark = pytest.mark.unit

_APPROVAL = ContentApproval(
    approver_role="test-only-no-approver",
    evidence_ref="test-only-no-evidence",
    approved_on=date(2026, 1, 1),
)

QUESTION = "quantas instalacoes tivemos em julho de 2026 por plataforma"
REFERENCE = date(2026, 8, 1)
ON = date(2026, 8, 18)

#: July 2026, written out. See the module docstring for why nothing here derives it.
JULY_START = date(2026, 7, 1)
JULY_END = date(2026, 7, 31)


def _july(rule: str = "named_calendar_range") -> PeriodExpression:
    return PeriodExpression(
        id="july_2026",
        surface_forms=("julho de 2026",),
        boundary_rule=rule,
        inclusivity="inclusive_both",
    )


def _vocabulary(*expressions: PeriodExpression) -> PeriodVocabulary:
    return PeriodVocabulary(
        version="test-vocabulary-not-approved",
        effective_from=date(2026, 1, 1),
        approval=_APPROVAL,
        expressions=expressions,
    )


def _resolver(
    *,
    start: date = JULY_START,
    end: date = JULY_END,
    answers_in: str | None = None,
    inclusivity: str | None = None,
):
    """A resolver returning a stated interval, so each case varies exactly one thing.

    `answers_in` overrides the zone the resolver *answers* with, and it is a separate name from the
    `timezone` the port hands **in** on purpose: the first attempt shadowed the parameter with a
    default, the caller's explicit `timezone=` won, and the override silently did nothing. The two
    directions need two names.
    """

    def resolve(
        *,
        expression: PeriodExpression,
        reference_date: date,
        timezone: str,
        convention: PeriodConvention,
    ) -> GovernedInterval:
        del reference_date, convention
        return GovernedInterval(
            start=start,
            end=end,
            timezone=answers_in if answers_in is not None else timezone,
            inclusivity=inclusivity if inclusivity is not None else expression.inclusivity,
        )

    return resolve


def _resolve(**kwargs: object):
    return resolve_period_in_question(
        QUESTION,
        reference_date=REFERENCE,
        vocabulary=_vocabulary(_july()),
        resolver=_resolver(**kwargs),  # pyright: ignore[reportArgumentType]
        on=ON,
    )


class TestTheResolverProducesTheResolvedPeriod:
    """Owner item B: the full range reaches the resolved period, not a single day."""

    def test_the_whole_named_range_is_resolved(self) -> None:
        """The owner's stated requirement, asserted as the literal dates he stated."""
        period = _resolve()
        assert (period.start, period.end) == (JULY_START, JULY_END)

    def test_the_governed_expression_and_rule_are_recorded(self) -> None:
        """An answer states which entry and which convention produced its boundaries."""
        period = _resolve()
        assert period.expression == "july_2026"
        assert period.resolved_by == "governed_expression"
        assert period.convention is not None
        assert period.convention.boundary_rule == "named_calendar_range"
        assert period.convention.inclusivity == "inclusive_both"

    def test_the_reference_date_is_carried_and_not_the_interval(self) -> None:
        """The reference date is a separate fact from the range, and both are kept."""
        period = _resolve()
        assert period.reference_date == REFERENCE
        assert period.start != REFERENCE

    def test_a_single_day_interval_is_still_valid(self) -> None:
        """Nothing requires a range to be wide. A one-day interval resolves to one day."""
        period = _resolve(start=JULY_START, end=JULY_START)
        assert (period.start, period.end) == (JULY_START, JULY_START)

    def test_two_resolutions_of_one_question_agree(self) -> None:
        """Determinism, asserted rather than assumed: nothing here reads a clock."""
        assert _resolve() == _resolve()


class TestTheResolverCannotDecideTheTwoGovernedFacts:
    """The zone and the inclusivity are checked, because a resolver is deployment code."""

    def test_another_time_zone_refuses(self) -> None:
        """A second business zone would move every boundary day somewhere.

        `America/Sao_Paulo` is what `001` declares once. A resolver answering in `UTC` is refused
        rather than silently normalised, because normalising it would hide that the deployment and
        the catalog disagree.
        """
        with pytest.raises(ContractViolation) as raised:
            _resolve(answers_in="UTC")
        assert raised.value.code is InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED

    def test_restating_the_inclusivity_refuses(self) -> None:
        """Inclusivity is the vocabulary's declaration; a resolver may carry it, never change it."""
        with pytest.raises(ContractViolation) as raised:
            _resolve(inclusivity="exclusive_end")
        assert raised.value.code is InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED

    def test_the_canonical_zone_is_the_one_the_catalog_declares(self) -> None:
        """Guards the assertion above: it would pass trivially if the constant were something else.

        Named against `001`'s constant rather than the string, so a change there is visible here
        instead of turning this file into two disagreeing copies of a time zone.
        """
        assert CANONICAL_TIMEZONE == "America/Sao_Paulo"


class TestAnIntervalThatCannotBeGovernedRefuses:
    """Unknown rules and impossible ranges refuse. Neither is resolved under an assumption."""

    def test_an_interval_that_does_not_order_refuses(self) -> None:
        """End before start is refused on construction, before anything can carry it.

        `001`'s `canonical_period` refuses the same thing and remains the authority on range
        validity. This refusal is earlier, which is why the type raises rather than this module.
        """
        with pytest.raises(ValueError, match="ends 2026-07-01 before it starts 2026-07-31"):
            _resolve(start=JULY_END, end=JULY_START)

    def test_a_resolver_refusal_is_carried_and_not_converted(self) -> None:
        """A resolver that has no calendar for a rule refuses, and the refusal is not swallowed.

        This is the property that keeps an unimplemented convention from looking implemented: the
        refusal travels out of step 7 as the resolver raised it.
        """

        def refusing(
            *,
            expression: PeriodExpression,
            reference_date: date,
            timezone: str,
            convention: PeriodConvention,
        ) -> GovernedInterval:
            del expression, reference_date, timezone, convention
            raise ContractViolation(
                InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED,
                "no calendar for this boundary rule",
            )

        with pytest.raises(ContractViolation) as raised:
            resolve_period_in_question(
                QUESTION,
                reference_date=REFERENCE,
                vocabulary=_vocabulary(_july()),
                resolver=refusing,
                on=ON,
            )
        assert raised.value.code is InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED

    def test_the_resolver_is_never_reached_for_an_ungoverned_expression(self) -> None:
        """Step 7 refuses before asking: a resolver cannot rescue a period `D-18` does not carry."""
        called: list[object] = []

        def recording(
            *,
            expression: PeriodExpression,
            reference_date: date,
            timezone: str,
            convention: PeriodConvention,
        ) -> GovernedInterval:
            called.append(expression)  # pragma: no cover - reaching this is the failure
            raise AssertionError("the resolver was consulted for an ungoverned expression")

        with pytest.raises(ContractViolation) as raised:
            resolve_period_in_question(
                "quantas instalacoes por plataforma",
                reference_date=REFERENCE,
                vocabulary=_vocabulary(_july()),
                resolver=recording,
                on=ON,
            )
        assert raised.value.code is InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED
        assert called == []

    def test_an_empty_vocabulary_refuses_before_the_resolver(self) -> None:
        """The shipped state. `D-18` carries `instances: []`, and a resolver does not substitute."""
        with pytest.raises(ContractViolation) as raised:
            resolve_period_in_question(
                QUESTION,
                reference_date=REFERENCE,
                vocabulary=_vocabulary(),
                resolver=_resolver(),  # pyright: ignore[reportArgumentType]
                on=ON,
            )
        assert raised.value.code is InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED

    def test_a_rule_declaring_a_convention_it_does_not_carry_still_refuses(self) -> None:
        """The pre-existing convention check is unchanged by the port.

        A month-relative rule with no `month_rule` refuses. `PeriodExpression` enforces it on
        construction, so this builds the model unvalidated to reach the check in `period.py` — the
        same technique the older period suite uses for the same reason.
        """
        expression = PeriodExpression.model_construct(
            id="last_month",
            surface_forms=("mes passado",),
            boundary_rule="month_relative",
            inclusivity="inclusive_both",
            week_start=None,
            month_rule=None,
        )
        # The vocabulary validates its entries too, so it is constructed unvalidated as well. Both
        # refusals are correct and neither is what this case is about: the point is that the check
        # inside `period.py` still fires for an entry that reached it another way.
        vocabulary = PeriodVocabulary.model_construct(
            version="test-vocabulary-not-approved",
            effective_from=date(2026, 1, 1),
            approval=_APPROVAL,
            expressions=(expression,),
        )
        with pytest.raises(ContractViolation) as raised:
            resolve_period_in_question(
                "quantas instalacoes tivemos no mes passado",
                reference_date=REFERENCE,
                vocabulary=vocabulary,
                resolver=_resolver(),  # pyright: ignore[reportArgumentType]
                on=ON,
            )
        assert raised.value.code is InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED
