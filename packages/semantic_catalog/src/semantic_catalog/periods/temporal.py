"""Resolve a temporal expression to explicit bounds. Deterministic, clock injected (`R-8`).

Authorized by the owner on 2026-08-20, in the master authorization for trials, purchases and
flexible periods. It lives in `001` because `R-8` puts date arithmetic and IANA resolution here,
and because `CANONICAL_TIMEZONE` is already declared here exactly once.

## What this module is for, and what it deliberately is not

A model reads a question and says **which** temporal expression it found. This module decides **what
dates that means**. The split is the whole design:

* a model may name `last_month`; it may not compute that February has 28 days;
* every bound below comes from calendar arithmetic over `date` objects, never from a constant. There
  is no `timedelta(days=30)` standing in for a month and no `365` standing in for a year, because
  both are wrong twice a year and once every four years respectively.

**The clock is a parameter.** `now` is passed in, and nothing here reads it. A period whose value
depends on when the test ran is not a period, and the owner's order is explicit: the reference
instant is captured once, at the message boundary, and never re-read during one execution.

## The half-open convention, and why every bound is exclusive at the end

Every window is `[start_inclusive, end_exclusive)`. A question says "entre 1 de julho e 20 de
agosto", meaning both; a query that filters `date < end` and a query that filters `date <= end`
differ by exactly one day of data, and the difference is invisible in a result. So the inclusive
reading is done **once**, here, at parse time — `end_exclusive` is the day *after* the last day the
sender meant — and every consumer downstream compares with `<`.

`label_pt_br` and `resolution_rule` travel with the window for the same reason a `ResolvedPeriod`
carries its convention upstream: an answer must be able to state which rule produced its numbers,
and a rule looked up twice is a rule that can differ twice.

## The week starts on Monday, and that is a declared MVP convention

Nothing in this repository's governed content declares a week start. ISO-8601 says Monday and pt-BR
business reporting usually agrees, so this module uses Monday — and says so in `resolution_rule` on
every weekly window, so an answer discloses the convention it applied rather than implying an
approval that does not exist. **This is a demonstration convention, not approved governed content.**

## Ambiguity refuses. It never guesses.

`TemporalAmbiguity` is raised for an expression that has more than one defensible reading — a month
with no year when the reference instant does not settle it, a bare "último período", an inverted
range. The caller turns that into a clarification question. Guessing here would put a confident
number under a question nobody asked, which is the failure the owner's order names first.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from .canonical import CANONICAL_TIMEZONE

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "Alignment",
    "Granularity",
    "ResolvedComparison",
    "ResolvedWindow",
    "TemporalAmbiguity",
    "TemporalIntent",
    "TemporalKind",
    "add_months",
    "resolve_comparison",
    "resolve_window",
]


class TemporalAmbiguity(ValueError):  # noqa: N818 - a refusal, not a defect
    """The expression has more than one defensible reading, so nothing is resolved.

    A `ValueError` subclass because an unresolvable expression *is* a bad value, and callers that
    already handle `ValueError` from `canonical_period` keep working. Distinct so a caller can turn
    exactly this into a clarification question instead of an error message.
    """


class TemporalKind(StrEnum):
    """What shape of answer the question asks for."""

    SINGLE_PERIOD = "single_period"
    RANGE = "range"
    COMPARISON = "comparison"


class Granularity(StrEnum):
    """The calendar unit a window is expressed in.

    ``ROLLING`` is the odd one and it is named rather than folded into ``DAY``: "últimos 7 dias"
    is a window that moves with the reference instant, and an answer that called it a day would
    lose the fact that repeating the question tomorrow gives different bounds.
    """

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    ROLLING = "rolling"


class Alignment(StrEnum):
    """Whether two compared windows can be read side by side.

    Reported, never enforced: a comparison of a partial month against a whole one is a legitimate
    question and a misleading answer, so the answer must carry the warning rather than the
    comparison being refused.
    """

    SAME_LENGTH = "same_length"
    DIFFERENT_LENGTH = "different_length"
    PARTIAL_AGAINST_COMPLETE = "partial_against_complete"


@dataclass(frozen=True)
class ResolvedWindow:
    """One window with explicit bounds. **Half open**: `[start_inclusive, end_exclusive)`.

    Named `ResolvedWindow` rather than the owner's `ResolvedPeriod` for one reason, stated so the
    vocabulary difference is not mistaken for a design difference: `analytics_interaction` already
    publishes a `ResolvedPeriod` with different fields — inclusive `end`, a `D-18` expression id, a
    convention — and two types with one name would be read as one type. This is the owner's
    `ResolvedPeriod`; the fields are the ones he listed.
    """

    start_inclusive: date
    end_exclusive: date
    granularity: Granularity
    label_pt_br: str
    resolution_rule: str
    timezone: str = CANONICAL_TIMEZONE

    def __post_init__(self) -> None:
        if self.end_exclusive <= self.start_inclusive:
            raise TemporalAmbiguity(
                f"a window must cover at least one day; got start {self.start_inclusive} and "
                f"exclusive end {self.end_exclusive}"
            )

    @property
    def days(self) -> int:
        """Day count. Exact because it counts dates, not hours — DST cannot move it."""
        return (self.end_exclusive - self.start_inclusive).days

    @property
    def last_day(self) -> date:
        """The last day the sender meant. The inclusive reading, recovered for display only."""
        return self.end_exclusive - timedelta(days=1)

    def covers(self, day: date) -> bool:
        return self.start_inclusive <= day < self.end_exclusive

    def is_complete_at(self, now: datetime) -> bool:
        """Whether the window has fully elapsed at ``now``.

        A window whose end has not arrived is **partial**, and an answer that compared a partial
        window against a complete one without saying so would be comparing three weeks with four.
        """
        return self.end_exclusive <= now.date()


@dataclass(frozen=True)
class ResolvedComparison:
    """Two independent windows, and how comparable they are."""

    primary: ResolvedWindow
    comparison: ResolvedWindow
    alignment: Alignment


@dataclass(frozen=True)
class TemporalIntent:
    """What a model may say about time, before anything is computed.

    Every field is either a closed-set token or an integer. There is no date here, and that is the
    point: a model that could hand over a date could hand over the wrong one, and nothing downstream
    would know. It names a rule; this module applies it.

    ``expression`` is the rule token — ``today``, ``yesterday``, ``last_month``, ``last_n_days`` and
    so on. ``amount`` carries the N of a rolling window. ``year``, ``month`` and ``day`` carry an
    absolute date's parts, each one optional so a bare year or a bare month-and-year is expressible.
    ``original_expression`` is the sender's own words, carried for the audit trail and **never**
    parsed here.
    """

    kind: TemporalKind
    expression: str
    granularity: Granularity
    amount: int | None = None
    year: int | None = None
    month: int | None = None
    day: int | None = None
    end_year: int | None = None
    end_month: int | None = None
    end_day: int | None = None
    comparison_expression: str | None = None
    comparison_year: int | None = None
    comparison_month: int | None = None
    comparison_day: int | None = None
    original_expression: str = ""


# --------------------------------------------------------------------------------------------------
# Calendar arithmetic. Everything below counts calendar units, never fixed day counts.
# --------------------------------------------------------------------------------------------------


def add_months(anchor: date, months: int) -> date:
    """Move ``anchor`` by whole calendar months, clamping the day to the target month's length.

    Public because it is the one piece of arithmetic every monthly rule here needs, and because a
    second copy of it somewhere else is how 31 January plus one month becomes 3 March.

    Clamping is the documented behaviour: 31 January plus one month is 28 February, or 29 in a leap
    year. That is what a reader of a monthly report expects, and it is why `monthrange` is consulted
    rather than a fixed table.
    """
    zero_based = anchor.month - 1 + months
    year = anchor.year + zero_based // 12
    month = zero_based % 12 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return date(year, month, day)


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _next_month_start(year: int, month: int) -> date:
    return _month_start(year + 1, 1) if month == 12 else _month_start(year, month + 1)


def _week_start(day: date) -> date:
    """The Monday of ``day``'s week. See the module docstring for why Monday."""
    return day - timedelta(days=day.weekday())


def _quarter_of(month: int) -> int:
    return (month - 1) // 3 + 1


# --------------------------------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------------------------------

#: Rules that need no year, month or day: the reference instant settles them completely.
_RELATIVE_RULES = frozenset(
    {
        "today",
        "yesterday",
        "day_before_yesterday",
        "this_week",
        "last_week",
        "this_month",
        "last_month",
        "this_quarter",
        "last_quarter",
        "this_year",
        "last_year",
    }
)

#: Rules that need ``amount``.
_ROLLING_RULES = frozenset({"last_n_days", "last_n_weeks", "last_n_months", "last_n_years"})

#: Rules that need at least a year.
_ABSOLUTE_RULES = frozenset({"absolute_day", "absolute_month", "absolute_year", "absolute_range"})

_MONTHS_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _month_label(year: int, month: int) -> str:
    return f"{_MONTHS_PT[month - 1]} de {year}"


def resolve_window(intent: TemporalIntent, *, now: datetime) -> ResolvedWindow:
    """The window one temporal intent names, or refuse.

    ``now`` must be timezone aware. An aware instant is what makes "today" a fact rather than a
    guess about which side of midnight the caller is on, and a naive one is refused rather than
    assumed to be local.
    """
    if now.tzinfo is None:
        raise TemporalAmbiguity(
            "the reference instant carries no time zone, so 'today' has no single meaning"
        )

    rule = intent.expression
    today = now.date()

    if rule in _RELATIVE_RULES:
        return _resolve_relative(rule, today=today)
    if rule in _ROLLING_RULES:
        return _resolve_rolling(rule, intent, today=today)
    if rule in _ABSOLUTE_RULES:
        return _resolve_absolute(rule, intent)
    raise TemporalAmbiguity(
        f"no resolution rule is declared for the expression {rule!r}; an unknown rule is refused "
        "rather than approximated by a nearby one"
    )


def _resolve_relative(rule: str, *, today: date) -> ResolvedWindow:
    """The eleven rules the reference instant settles on its own."""
    if rule == "today":
        return ResolvedWindow(
            today,
            today + timedelta(days=1),
            Granularity.DAY,
            "hoje",
            "civil day containing the reference instant",
        )
    if rule == "yesterday":
        start = today - timedelta(days=1)
        return ResolvedWindow(
            start, today, Granularity.DAY, "ontem", "the civil day before the reference day"
        )
    if rule == "day_before_yesterday":
        start = today - timedelta(days=2)
        return ResolvedWindow(
            start,
            start + timedelta(days=1),
            Granularity.DAY,
            "anteontem",
            "the second civil day before the reference day",
        )
    if rule == "this_week":
        start = _week_start(today)
        return ResolvedWindow(
            start,
            start + timedelta(days=7),
            Granularity.WEEK,
            "esta semana",
            "Monday to Sunday of the reference week; MVP convention, not approved content",
        )
    if rule == "last_week":
        start = _week_start(today) - timedelta(days=7)
        return ResolvedWindow(
            start,
            start + timedelta(days=7),
            Granularity.WEEK,
            "semana passada",
            "Monday to Sunday of the previous civil week; MVP convention, not approved content",
        )
    if rule == "this_month":
        start = _month_start(today.year, today.month)
        return ResolvedWindow(
            start,
            _next_month_start(today.year, today.month),
            Granularity.MONTH,
            "este mês",
            "the civil month containing the reference day",
        )
    if rule == "last_month":
        previous = add_months(_month_start(today.year, today.month), -1)
        return ResolvedWindow(
            previous,
            _month_start(today.year, today.month),
            Granularity.MONTH,
            f"{_month_label(previous.year, previous.month)} (mês passado)",
            "the whole previous civil month",
        )
    if rule == "this_quarter":
        first_month = (_quarter_of(today.month) - 1) * 3 + 1
        start = _month_start(today.year, first_month)
        return ResolvedWindow(
            start,
            add_months(start, 3),
            Granularity.QUARTER,
            f"{_quarter_of(today.month)}º trimestre de {today.year}",
            "the three civil months of the quarter containing the reference day",
        )
    if rule == "last_quarter":
        first_month = (_quarter_of(today.month) - 1) * 3 + 1
        current = _month_start(today.year, first_month)
        start = add_months(current, -3)
        return ResolvedWindow(
            start,
            current,
            Granularity.QUARTER,
            f"{_quarter_of(start.month)}º trimestre de {start.year}",
            "the three civil months of the previous quarter",
        )
    if rule == "this_year":
        return ResolvedWindow(
            date(today.year, 1, 1),
            date(today.year + 1, 1, 1),
            Granularity.YEAR,
            "este ano",
            "the civil year containing the reference day",
        )
    # `last_year` is the only rule left; the membership check above guarantees it.
    return ResolvedWindow(
        date(today.year - 1, 1, 1),
        date(today.year, 1, 1),
        Granularity.YEAR,
        f"{today.year - 1} (ano passado)",
        "the whole previous civil year",
    )


def _resolve_rolling(rule: str, intent: TemporalIntent, *, today: date) -> ResolvedWindow:
    """Windows that move with the reference instant. ``N`` must be present and positive."""
    amount = intent.amount
    if amount is None or amount <= 0:
        raise TemporalAmbiguity(
            f"{rule!r} needs a positive count and none was given; 'os últimos dias' does not say "
            "how many"
        )

    end = today + timedelta(days=1)  # rolling windows include today, per the owner's rule
    if rule == "last_n_days":
        return ResolvedWindow(
            end - timedelta(days=amount),
            end,
            Granularity.ROLLING,
            f"últimos {amount} dias",
            f"{amount} civil days ending today, today included",
        )
    if rule == "last_n_weeks":
        return ResolvedWindow(
            end - timedelta(weeks=amount),
            end,
            Granularity.ROLLING,
            f"últimas {amount} semanas",
            f"{amount} times seven civil days ending today, today included",
        )
    if rule == "last_n_months":
        return ResolvedWindow(
            add_months(end, -amount),
            end,
            Granularity.ROLLING,
            f"últimos {amount} meses",
            f"{amount} calendar months back from tomorrow; never {amount} times thirty days",
        )
    # `last_n_years`
    return ResolvedWindow(
        add_months(end, -12 * amount),
        end,
        Granularity.ROLLING,
        f"últimos {amount} anos",
        f"{amount} calendar years back from tomorrow; leap days included by calendar arithmetic",
    )


def _resolve_absolute(rule: str, intent: TemporalIntent) -> ResolvedWindow:
    """Dates the sender stated. A missing year is ambiguity, never the current one."""
    year = intent.year
    if year is None:
        raise TemporalAmbiguity(
            "an absolute date needs a year, and the current one is not assumed: 'julho' without a "
            "year could mean this July or any other"
        )

    if rule == "absolute_year":
        return ResolvedWindow(
            date(year, 1, 1),
            date(year + 1, 1, 1),
            Granularity.YEAR,
            str(year),
            "the whole named civil year",
        )

    if rule == "absolute_month":
        month = _checked_month(intent.month, "absolute_month")
        return ResolvedWindow(
            _month_start(year, month),
            _next_month_start(year, month),
            Granularity.MONTH,
            _month_label(year, month),
            "the whole named civil month",
        )

    if rule == "absolute_day":
        month = _checked_month(intent.month, "absolute_day")
        day = _checked_day(year, month, intent.day)
        start = date(year, month, day)
        return ResolvedWindow(
            start,
            start + timedelta(days=1),
            Granularity.DAY,
            f"{day} de {_month_label(year, month)}",
            "the single named civil day",
        )

    # `absolute_range`: both ends stated, and the sender's inclusive reading is converted once.
    return _resolve_range(intent, year)


def _resolve_range(intent: TemporalIntent, year: int) -> ResolvedWindow:
    """ "entre X e Y", with the end made exclusive here and nowhere else."""
    end_year = intent.end_year if intent.end_year is not None else year
    start_month = intent.month
    end_month = intent.end_month

    if start_month is None and end_month is None:
        # "entre 2025 e 2026": whole years, both included.
        if end_year < year:
            raise TemporalAmbiguity(f"the range ends in {end_year}, before it starts in {year}")
        return ResolvedWindow(
            date(year, 1, 1),
            date(end_year + 1, 1, 1),
            Granularity.YEAR,
            f"{year} a {end_year}",
            "whole civil years, both ends included, converted to an exclusive end",
        )

    start_month = _checked_month(start_month, "absolute_range")
    end_month = _checked_month(
        end_month if end_month is not None else start_month, "absolute_range"
    )

    if intent.day is None and intent.end_day is None:
        # "de janeiro a março de 2026": whole months, both included.
        start = _month_start(year, start_month)
        end = _next_month_start(end_year, end_month)
        if end <= start:
            raise TemporalAmbiguity(
                f"the range ends in {_month_label(end_year, end_month)}, before it starts in "
                f"{_month_label(year, start_month)}"
            )
        return ResolvedWindow(
            start,
            end,
            Granularity.MONTH,
            f"{_month_label(year, start_month)} a {_month_label(end_year, end_month)}",
            "whole civil months, both ends included, converted to an exclusive end",
        )

    start_day = _checked_day(year, start_month, intent.day if intent.day is not None else 1)
    last_day = intent.end_day if intent.end_day is not None else monthrange(end_year, end_month)[1]
    end_day = _checked_day(end_year, end_month, last_day)
    start = date(year, start_month, start_day)
    end = date(end_year, end_month, end_day) + timedelta(days=1)
    if end <= start:
        raise TemporalAmbiguity(
            f"the range ends {end - timedelta(days=1)}, before it starts {start}"
        )
    return ResolvedWindow(
        start,
        end,
        Granularity.DAY,
        f"{start_day} de {_month_label(year, start_month)} a "
        f"{end_day} de {_month_label(end_year, end_month)}",
        "named days, both ends included, converted to an exclusive end",
    )


def _checked_month(month: int | None, rule: str) -> int:
    if month is None:
        raise TemporalAmbiguity(f"{rule!r} needs a month and none was given")
    if not 1 <= month <= 12:
        raise TemporalAmbiguity(f"{month} is not a month")
    return month


def _checked_day(year: int, month: int, day: int | None) -> int:
    """A day that exists in that month. 31 April refuses; 29 February depends on the year."""
    if day is None:
        raise TemporalAmbiguity("an absolute day needs a day and none was given")
    length = monthrange(year, month)[1]
    if not 1 <= day <= length:
        raise TemporalAmbiguity(
            f"{day} is not a day of {_month_label(year, month)}, which has {length}"
        )
    return day


# --------------------------------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------------------------------

#: Which rule produces the immediately preceding window of the same granularity. Used when the
#: sender says "em relação ao período anterior" without naming the second period.
_PRECEDING: dict[str, str] = {
    "today": "yesterday",
    "yesterday": "day_before_yesterday",
    "this_week": "last_week",
    "this_month": "last_month",
    "this_quarter": "last_quarter",
    "this_year": "last_year",
}


def resolve_comparison(intent: TemporalIntent, *, now: datetime) -> ResolvedComparison:
    """Two windows and their alignment, or refuse.

    The comparison window comes from `comparison_expression` when the sender named one, and from
    `_PRECEDING` when they said "o período anterior". A comparison whose second window cannot be
    derived refuses rather than defaulting to the previous day, because "em relação ao anterior"
    after a monthly question means the previous *month*.
    """
    primary = resolve_window(intent, now=now)

    named = intent.comparison_expression
    if named is None:
        named = _PRECEDING.get(intent.expression)
        if named is None:
            raise TemporalAmbiguity(
                f"no comparison period was named and none follows from {intent.expression!r}; "
                "'o período anterior' is only unambiguous for a period the calendar precedes"
            )

    comparison = resolve_window(
        TemporalIntent(
            kind=TemporalKind.SINGLE_PERIOD,
            expression=named,
            granularity=intent.granularity,
            amount=intent.amount,
            year=intent.comparison_year,
            month=intent.comparison_month,
            day=intent.comparison_day,
            original_expression=intent.original_expression,
        ),
        now=now,
    )
    return ResolvedComparison(primary, comparison, _alignment(primary, comparison, now=now))


def _alignment(primary: ResolvedWindow, comparison: ResolvedWindow, *, now: datetime) -> Alignment:
    """How comparable two windows are. Reported so the answer can carry the caveat."""
    if primary.days != comparison.days:
        return Alignment.DIFFERENT_LENGTH
    if not primary.is_complete_at(now) and comparison.is_complete_at(now):
        return Alignment.PARTIAL_AGAINST_COMPLETE
    return Alignment.SAME_LENGTH


def windows_of(intents: Sequence[TemporalIntent], *, now: datetime) -> tuple[ResolvedWindow, ...]:
    """Resolve several intents against **one** reference instant.

    Exists so a caller resolving a comparison cannot accidentally resolve the two halves against two
    instants — which is possible, and produces two windows that disagree about what "today" is.
    """
    return tuple(resolve_window(intent, now=now) for intent in intents)
