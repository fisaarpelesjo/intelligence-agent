"""Resolved intent, terms and periods — T036 (FR-005, FR-006; SC-001).

Interpretation is **slot-filling over a governed vocabulary**. There are exactly
six slot kinds; filling them is all interpretation does. It produces no free
text, no derived concept and no identifier the catalog does not already declare.

Two design facts carry most of the weight here.

**A ``TermResolution`` carries a position, never the text.** Echoing the user's
words back would put question text into the answer, the logs and the audit
event, which `FR-053` forbids. The caller already holds the text and can
highlight the span from ``TermRef``.

**``ResolutionBasis`` is load-bearing.** `002`'s `§4.4.1` establishes that three
of `001`'s six dimensions declare ``permitted_values: open``, so a ``country`` or
``app_version`` term can be validated for governed type and shape only — there is
no set to test membership against. An open-text resolution must not be presented
with the same standing as an enumerated one, so the basis travels with it.

``ResolvedIntent.comparison`` is a forward reference to ``ComparisonIntent``,
which in turn needs ``ResolvedPeriod`` from this module. The cycle is real in the
data model, so it is resolved where pydantic expects: `comparison.py` rebuilds
``ResolvedIntent`` once both halves exist, and `contracts/__init__.py` imports
both so no import order can observe a half-built model.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from analytics_query.contracts.request import GovernedFilter
from pydantic import Field, StrictInt, model_validator

from ._base import InteractionModel
from .intake import DeclaredLanguage

if TYPE_CHECKING:
    from .comparison import ComparisonIntent

__all__ = [
    "GovernedInterval",
    "MatchKind",
    "PeriodConvention",
    "ResolutionBasis",
    "ResolvedIntent",
    "ResolvedPeriod",
    "SlotKind",
    "TermRef",
    "TermResolution",
]


class SlotKind(StrEnum):
    """The six slots interpretation fills, and the only six.

    A seventh would be a contract change: the closed set is what lets a
    clarification name its unresolved slot without a free-text field.
    """

    METRIC = "metric"
    DIMENSION = "dimension"
    DIMENSION_VALUE = "dimension_value"
    SOURCE = "source"
    PERIOD = "period"
    COMPARISON = "comparison"


class MatchKind(StrEnum):
    """**How** a term matched. Disclosed to the user (`FR-006`).

    Recording the match kind is what makes a misinterpretation visible rather
    than silent: "resolved via informal synonym" reads very differently from
    "resolved via canonical id", and the user is the one who can tell whether it
    was right.
    """

    CANONICAL_ID = "canonical_id"
    LABEL = "label"
    SYNONYM_FORMAL = "synonym_formal"
    SYNONYM_INFORMAL = "synonym_informal"
    SYNONYM_ABBREVIATION = "synonym_abbreviation"
    GLOSSARY_TERM = "glossary_term"
    PERIOD_EXPRESSION = "period_expression"


class ResolutionBasis(StrEnum):
    """What the resolution actually proved.

    ``OPEN_TEXT_SHAPE`` proves strictly less than ``ENUMERATED_MEMBERSHIP``: a
    country term that is merely shape-valid has not been shown to exist in the
    data, and the answer must not imply it has.
    """

    ENUMERATED_MEMBERSHIP = "enumerated_membership"
    OPEN_TEXT_SHAPE = "open_text_shape"
    GOVERNED_EXPRESSION = "governed_expression"


class TermRef(InteractionModel):
    """Where a term sat in the question. **Position and length, never the text.**

    Offering no text field is the mechanism for `FR-053`. A model that carried
    ``text: str`` alongside the offsets would put the span one assignment away
    from an audit event, and the prohibition would be a review note instead of a
    type.
    """

    start: StrictInt = Field(ge=0)
    length: StrictInt = Field(gt=0)


class TermResolution(InteractionModel):
    """One user term, resolved — or not — against the governed vocabulary."""

    term: TermRef
    slot: SlotKind
    resolved_to: str | None = None
    matched_via: MatchKind
    confidence_basis: ResolutionBasis


class PeriodConvention(InteractionModel):
    """The `D-18` convention a period was resolved under.

    Carried on the resolved period rather than looked up again at read time, so
    an answer states the convention that was actually applied. A convention
    resolved twice is a convention that can differ twice.
    """

    boundary_rule: str = Field(min_length=1)
    inclusivity: str = Field(min_length=1)
    week_start: str | None = None
    month_rule: str | None = None


class GovernedInterval(InteractionModel):
    """A concrete interval a governed boundary rule produced, with the zone it was produced in.

    Returned by `PeriodBoundaryResolverPort`, and it exists because the four things a period needs
    to be usable were previously spread across three owners: the dates were computed by whoever
    called `period.py`, the zone lived in `001`, and the inclusivity lived on the `D-18` entry. A
    caller assembling those three by hand is a caller who can assemble them inconsistently.

    ``timezone`` is **carried, never chosen**: a resolver reads it from `001`'s
    ``CANONICAL_TIMEZONE`` and this feature refuses any other value at the call site. A second
    business zone is not a configuration option, it is two answers to one question.

    ``inclusivity`` is the `D-18` entry's own declaration, carried across so a reader of the
    interval sees which convention produced its endpoints without resolving the vocabulary again.
    It is checked against the entry at the call site for the same reason: a resolver that could
    restate inclusivity would be a resolver that could overrule `D-18`.
    """

    start: date
    end: date
    timezone: str = Field(min_length=1)
    inclusivity: str = Field(min_length=1)

    @model_validator(mode="after")
    def _the_interval_orders(self) -> GovernedInterval:
        """An interval whose end precedes its start is refused here, not carried.

        `001`'s ``canonical_period`` refuses the same thing, and that refusal remains the authority
        on range validity (`R-8`). This one is earlier and cheaper: it stops an inverted interval
        from travelling far enough to be mistaken for a resolved one.
        """
        if self.end < self.start:
            raise ValueError(f"interval ends {self.end} before it starts {self.start}")
        return self


class ResolvedPeriod(InteractionModel):
    """A concrete date range, and the governed rule that produced it.

    **This feature performs no date arithmetic of its own.** It applies a `D-18`
    rule through `001`'s canonical-period machinery, so IANA resolution and the
    pre-2019 daylight-saving transitions stay `001`'s (`R-8`). What lives here is
    the *record* of that resolution, not a second implementation of it.

    ``expression`` is ``None`` when the caller gave explicit dates. When it is
    set, ``convention`` records which `D-18` entry governed the boundary — an
    expression absent from `D-18`, or one whose convention `D-18` does not
    declare, refuses instead of resolving under an assumption (`FR-010`).
    """

    start: date
    end: date
    expression: str | None = None
    reference_date: date
    convention: PeriodConvention | None = None
    resolved_by: str = Field(pattern=r"^(explicit_dates|governed_expression)$")

    @model_validator(mode="after")
    def _range_is_ordered(self) -> ResolvedPeriod:
        if self.end < self.start:
            raise ValueError("period end precedes period start")
        return self

    @model_validator(mode="after")
    def _a_governed_expression_names_its_rule(self) -> ResolvedPeriod:
        """A governed resolution must say which entry and which convention.

        Without both, the answer could not state what "semana passada" meant on
        that day, and the whole reason the vocabulary is governed would be
        unobservable to the reader.
        """
        if self.resolved_by == "governed_expression" and (
            self.expression is None or self.convention is None
        ):
            raise ValueError(
                "a governed period resolution must carry both its expression and its convention"
            )
        if self.resolved_by == "explicit_dates" and self.expression is not None:
            raise ValueError("explicit dates resolve no governed expression")
        return self


class ResolvedIntent(InteractionModel):
    """What the system understood the question to mean.

    Disclosed on **every** response — answers, clarifications and abstentions
    alike (`FR-038`). While every metric question refuses, this is the only
    observable output, and it is what lets a user tell a **misunderstanding**
    apart from a genuine **unavailability**.

    ``metrics`` may be empty on a partial intent carried by a clarification; a
    fully resolved intent carries at least one, and that requirement belongs to
    the resolution step (Phase 8), not to the shape.
    """

    metrics: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()
    filters: tuple[GovernedFilter, ...] = ()
    sources: tuple[str, ...] = ()
    period: ResolvedPeriod | None = None
    comparison: ComparisonIntent | None = None
    resolutions: tuple[TermResolution, ...] = ()
    language: DeclaredLanguage
    reference_date: date
    as_of: date | None = None
    catalog_release: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    vocabulary_version: str = Field(min_length=1)
