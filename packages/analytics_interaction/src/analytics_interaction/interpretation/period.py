"""Period resolution — T076 (FR-009, FR-010; SC-017, SC-018).

A `D-18` expression rule, applied to the caller's ``reference_date``, through
`001`'s canonical-period machinery.

**This module performs no date arithmetic of its own.** Not one ``timedelta``,
not one month-end calculation, not one week-boundary rule. IANA resolution and
the pre-2019 daylight-saving transitions are `001`'s (`R-8`), and a second
implementation of "what does last week mean" would eventually disagree with the
first — on exactly the days that are hardest to notice.

**Two refusals, and they are different facts.**

| Condition | Code |
|---|---|
| The expression is absent from `D-18` | ``PERIOD_EXPRESSION_NOT_GOVERNED`` |
| The expression exists but `D-18` declares no convention for it |
  ``PERIOD_CONVENTION_UNDECLARED`` |

Neither is ever approximated to the nearest known expression. "semana passada"
with no governed week convention does not become "the last seven days" — that
would be this library deciding a reporting standard, and it would change every
weekly number in the product.

**`D-18` is unavailable in the shipped repository**, so every expression reaches
the first refusal. Explicit dates still resolve, because they need no vocabulary:
a caller who supplies a start and an end has already said what they mean.
"""

from __future__ import annotations

import unicodedata
from datetime import date

from semantic_catalog.periods.canonical import (
    CANONICAL_TIMEZONE,
    CanonicalPeriod,
    canonical_period,
)

from ..contracts._base import ContractViolation, build
from ..contracts.intent import GovernedInterval, PeriodConvention, ResolvedPeriod
from ..contracts.reason_codes import InterpretationReasonCode
from ..governance.schemas import PeriodExpression, PeriodVocabulary
from ..segmentation import QuestionSpan, segment
from .boundary_port import PeriodBoundaryResolverPort

__all__ = [
    "locate_expression",
    "normalise_surface",
    "resolve_explicit_period",
    "resolve_expression",
    "resolve_governed_period",
    "resolve_period_in_question",
]


def _convention_of(expression: PeriodExpression) -> PeriodConvention:
    """Carry the `D-18` convention onto the resolved period, unchanged.

    Recorded on the period rather than looked up again at read time, so an
    answer states the convention that was actually applied. A convention
    resolved twice is a convention that can differ twice.
    """
    return build(
        PeriodConvention,
        boundary_rule=expression.boundary_rule,
        inclusivity=expression.inclusivity,
        week_start=expression.week_start,
        month_rule=expression.month_rule,
    )


def resolve_expression(surface: str, vocabulary: PeriodVocabulary) -> PeriodExpression:
    """The `D-18` entry a pt-BR phrasing names, or refuse.

    Matched against the entry's authored ``surface_forms`` and its ``id``, both
    exactly. **No nearest match, no fuzzy match, no normalisation of the
    caller's phrasing** — an expression absent from the vocabulary is absent,
    and approximating it would resolve a period nobody governed.

    Iteration is over the vocabulary's declared order, so two runs over the same
    instance produce the same entry.
    """
    for expression in vocabulary.expressions:
        if surface == expression.id or surface in expression.surface_forms:
            return expression

    raise ContractViolation(
        InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED,
        "the period expression is absent from the governed vocabulary and is "
        "never approximated to the nearest listed one",
    )


def normalise_surface(text: str) -> str:
    """The one input normalisation, applied to **both** sides of every comparison.

    Defined once and named, because `F12`'s correction needs a normalisation and a second ad hoc one
    would eventually disagree with the first. `demo_catalog` in the harness already did `strip` plus
    `lower` for catalog surfaces, so before this function the catalog comparison and the period
    comparison diverged; a caller that wants one rule now has one to reach for.

    Four transformations, and each answers one thing the owner's item 2 asks for:

    * **case** — `casefold`, not `lower`, because `lower` leaves some pairs unequal that a reader
      would call the same word;
    * **accents** — decompose to `NFD` and drop the combining marks, so `julho` and `jùlho` compare
      equal without a table of substitutions authored here;
    * **outer spaces** — stripped;
    * **inner spacing** — runs of whitespace collapse to one space, so `julho  de  2026` and
      `julho de 2026` are the same surface.

    **Punctuation is deliberately not handled here.** It never reaches this function, because
    :func:`~analytics_interaction.segmentation.tokens` treats every Unicode `P*` character as a
    token boundary, so a trailing `?` is outside every span before a comparison happens. Handling it
    twice would let the two rules drift.

    This changes no governed value. It normalises the **comparison**, and the expression that is
    resolved is still the one `D-18` authored, returned unchanged.
    """
    decomposed = unicodedata.normalize("NFD", text)
    unmarked = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(unicodedata.normalize("NFC", unmarked).casefold().split())


def locate_expression(
    text: str, vocabulary: PeriodVocabulary
) -> tuple[PeriodExpression, QuestionSpan]:
    """The governed expression a question **contains**, and where it sits. This is `F12`.

    Before this function, step 7 handed the *whole question* to :func:`resolve_expression`, which
    compares by exact equality. No input could satisfy both halves of a question: a text that was
    itself a period surface carried no metric, and a text carrying a metric was not a period
    surface. That is the wall `F12` names, and why every analytical question refused at step 7.

    ## What it reuses rather than reinvents

    :func:`~analytics_interaction.segmentation.segment` — the same spans step 6 resolves terms over.
    Three properties come free from that reuse and are not re-implemented here:

    * **Token alignment.** A span begins and ends at a token boundary, so `julho` never matches
      inside `julhoxyz`. The mandatory token-boundary case is a property of the segmenter.
    * **Punctuation never joins.** `julho, agosto` cannot produce the span `julho agosto`.
    * **Longest first, stable.** The most specific span is offered before the shorter one it
      contains, so `julho de 2026` wins over `julho`, and two runs over one question agree.

    ## What it decides, and what it refuses to decide

    It decides **which authored expression a span names**, by comparing under
    :func:`normalise_surface`. It decides nothing about dates: the range still comes from the
    governed rule, through the ``boundaries`` this module is handed.

    Ambiguity is a refusal, not a choice. If spans name **more than one distinct expression**, this
    raises ``INTENT_AMBIGUOUS`` — an existing governed code, because inventing a period-specific
    ambiguity code would be authoring a governed value. Picking the first of two periods would
    answer a question the sender did not ask.

    ``id`` is still compared **exactly**. It is the machine-facing name under
    `^[a-z][a-z0-9_]*$`, not something a person types, and case-folding an identifier would let two
    distinct ids collide.
    """
    matched: list[tuple[PeriodExpression, QuestionSpan]] = []
    seen: set[str] = set()
    for span in segment(text):
        normalised = normalise_surface(span.surface)
        for expression in vocabulary.expressions:
            names_it = span.surface == expression.id or any(
                normalised == normalise_surface(form) for form in expression.surface_forms
            )
            if names_it and expression.id not in seen:
                seen.add(expression.id)
                matched.append((expression, span))

    if not matched:
        raise ContractViolation(
            InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED,
            "no governed period expression occurs in the question, and one is never "
            "approximated to the nearest listed entry",
        )
    if len(matched) > 1:
        raise ContractViolation(
            InterpretationReasonCode.INTENT_AMBIGUOUS,
            "the question names more than one governed period expression; the period is "
            "never chosen for the sender",
        )
    return matched[0]


def resolve_governed_period(
    surface: str,
    *,
    reference_date: date,
    vocabulary: PeriodVocabulary,
    boundaries: tuple[date, date],
    on: date,
) -> ResolvedPeriod:
    """Resolve a governed expression to an explicit range.

    ``boundaries`` is the start and end **the governed rule produced**, computed
    by `001`'s canonical-period machinery and passed in. This function does not
    compute it and cannot: it has no week-start table, no month-end rule and no
    calendar of its own. Passing it in is what keeps the arithmetic where `R-8`
    puts it.

    The convention is re-asserted here rather than trusted from construction: an
    expression whose week or month rule `D-18` does not declare refuses
    ``PERIOD_CONVENTION_UNDECLARED`` rather than resolving under an assumption.
    ``PeriodExpression`` already enforces it, so reaching this branch means an
    entry arrived without passing through the contract.
    """
    expression = resolve_expression(surface, vocabulary)
    return _resolved_from(expression, reference_date=reference_date, boundaries=boundaries, on=on)


def resolve_period_in_question(
    text: str,
    *,
    reference_date: date,
    vocabulary: PeriodVocabulary,
    resolver: PeriodBoundaryResolverPort,
    on: date,
) -> ResolvedPeriod:
    """Resolve the governed period a **question contains**. The `F12` entry point.

    Same contract as :func:`resolve_governed_period` in every respect except two: which text it is
    given, and where the interval comes from. That one takes a surface the caller already isolated
    and a pair of dates the caller already computed; this one takes the whole question, finds the
    surface inside it with :func:`locate_expression`, and asks ``resolver`` for the interval.

    Both are kept. The surface-level function is the narrower operation, it is public API, and its
    exact-match promise is asserted by `003`'s own unit suite; replacing it would widen a documented
    contract instead of adding to it.

    **``boundaries`` became ``resolver`` on 2026-08-20**, on owner instruction. Handing the pair in
    made the caller compute it, and the only caller was ``ask()``, so the arithmetic would have
    landed in `interact.py` — which is exactly what `R-8` forbids and what the authorization named.
    The resolver is deployment code, it delegates the calendar to `001`, and this function checks
    its answer rather than trusting it: see :func:`_interval_for`.
    """
    expression, _span = locate_expression(text, vocabulary)
    interval = _interval_for(expression, reference_date=reference_date, resolver=resolver)
    return _resolved_from(
        expression,
        reference_date=reference_date,
        boundaries=(interval.start, interval.end),
        on=on,
    )


def _interval_for(
    expression: PeriodExpression,
    *,
    reference_date: date,
    resolver: PeriodBoundaryResolverPort,
) -> GovernedInterval:
    """Ask the resolver for the interval, then check the two things it may not decide.

    The zone and the inclusivity are checked rather than trusted because a resolver is supplied by
    the deployment. Neither check is a formality:

    * a resolver answering in another zone would put a second business time zone in the repository,
      and every boundary day would differ by one somewhere;
    * a resolver restating inclusivity would let deployment code overrule a `D-18` declaration,
      which is the same class of override the convention check below already refuses.

    Both refuse ``PERIOD_CONVENTION_UNDECLARED``: in both cases the convention actually applied is
    not the one the governed vocabulary declares, which is what that code says. Ordering is not
    checked here — ``GovernedInterval`` refuses an inverted interval on construction and `001`
    refuses it again, so a third copy would be a third place for it to stop being refused.
    """
    interval = resolver(
        expression=expression,
        reference_date=reference_date,
        timezone=CANONICAL_TIMEZONE,
        convention=_convention_of(expression),
    )
    if interval.timezone != CANONICAL_TIMEZONE:
        raise ContractViolation(
            InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED,
            "the boundary resolver answered in a time zone the catalog does not declare as "
            "canonical; the business zone has one source and it is not this answer",
        )
    if interval.inclusivity != expression.inclusivity:
        raise ContractViolation(
            InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED,
            "the boundary resolver restated the inclusivity the governed vocabulary declares; "
            "the convention is the vocabulary's to state and never the resolver's",
        )
    return interval


def _resolved_from(
    expression: PeriodExpression,
    *,
    reference_date: date,
    boundaries: tuple[date, date],
    on: date,
) -> ResolvedPeriod:
    """The half both governed entry points share: assert the convention, then resolve.

    Extracted rather than duplicated. Two copies of the convention check would be two places for a
    `PERIOD_CONVENTION_UNDECLARED` refusal to stop being raised, and only one of them would be the
    one a reader checked.

    The convention is re-asserted here rather than trusted from construction: an expression whose
    week or month rule `D-18` does not declare refuses ``PERIOD_CONVENTION_UNDECLARED`` rather than
    resolving under an assumption. ``PeriodExpression`` already enforces it, so reaching this branch
    means an entry arrived without passing through the contract.
    """
    rule = expression.boundary_rule.lower()
    if ("week" in rule and expression.week_start is None) or (
        "month" in rule and expression.month_rule is None
    ):
        raise ContractViolation(
            InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED,
            "the governed vocabulary declares no boundary convention for this "
            "expression; it is never resolved under an assumed one",
        )

    start, end = boundaries
    canonical = canonical_period(start, end, on=on)
    return build(
        ResolvedPeriod,
        start=canonical.requested_start,
        end=canonical.requested_end,
        expression=expression.id,
        reference_date=reference_date,
        convention=_convention_of(expression),
        resolved_by="governed_expression",
    )


def resolve_explicit_period(
    start: date, end: date, *, reference_date: date, on: date
) -> ResolvedPeriod:
    """Resolve a caller-supplied range. No vocabulary needed.

    Explicit dates carry their own meaning, so `D-18` being unavailable does not
    block them — that separation is deliberate, and it is why a question with
    real dates still works today while "semana passada" refuses.

    Still routed through `001`'s ``canonical_period`` so the canonical zone and
    the completeness classification are the same ones every other consumer sees.
    """
    canonical: CanonicalPeriod = canonical_period(start, end, on=on)
    return build(
        ResolvedPeriod,
        start=canonical.requested_start,
        end=canonical.requested_end,
        expression=None,
        reference_date=reference_date,
        convention=None,
        resolved_by="explicit_dates",
    )
