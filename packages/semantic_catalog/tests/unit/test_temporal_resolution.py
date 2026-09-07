"""Every temporal rule the owner listed, with the clock injected. **No test here reads a clock.**

The owner's master authorization of 2026-08-20 lists thirty-nine cases. Each one is below, and each
one asserts the **bounds**, not a description of them: a test that checked a label would pass while
the dates were wrong, which is the only way this module can fail expensively.

## Why the reference instant is a constant

`NOW` is 2026-08-20 15:00 in `America/Sao_Paulo`, a **Thursday**. Every expected date below was
derived by hand from that instant and written as a literal. Deriving the expectation with the same
arithmetic the code uses would assert that the code agrees with itself.

The day of the week matters and is stated because six cases depend on it: Monday of that week is the
17th, so `this_week` starts on the 17th and `last_week` on the 10th.

## What "no constant" means, and where it is asserted

The module promises calendar arithmetic rather than fixed day counts. Three cases pin that: six
months back from a February reference lands in August and not 180 days earlier; a leap February has
29 days; and 31 January plus a month is the 28th or 29th, never 3 March.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from semantic_catalog.periods.canonical import CANONICAL_TIMEZONE
from semantic_catalog.periods.temporal import (
    Alignment,
    Granularity,
    TemporalAmbiguity,
    TemporalIntent,
    TemporalKind,
    add_months,
    resolve_comparison,
    resolve_window,
    windows_of,
)

pytestmark = pytest.mark.unit

ZONE = ZoneInfo(CANONICAL_TIMEZONE)

#: Thursday, 20 August 2026, 15:00 in the canonical zone. Every expectation below derives from it.
NOW = datetime(2026, 8, 20, 15, 0, tzinfo=ZONE)


def _intent(expression: str, **fields: object) -> TemporalIntent:
    return TemporalIntent(
        kind=TemporalKind.SINGLE_PERIOD,
        expression=expression,
        granularity=Granularity(fields.pop("granularity", Granularity.DAY)),  # pyright: ignore[reportArgumentType]
        **fields,  # pyright: ignore[reportArgumentType]
    )


def _bounds(expression: str, **fields: object) -> tuple[date, date]:
    window = resolve_window(_intent(expression, **fields), now=NOW)
    return window.start_inclusive, window.end_exclusive


class TestTheReferenceInstantSettlesTheseOnItsOwn:
    """The eleven relative rules. Nothing here needs a year, a month or a day."""

    def test_today(self) -> None:
        assert _bounds("today") == (date(2026, 8, 20), date(2026, 8, 21))

    def test_yesterday(self) -> None:
        assert _bounds("yesterday") == (date(2026, 8, 19), date(2026, 8, 20))

    def test_day_before_yesterday(self) -> None:
        assert _bounds("day_before_yesterday") == (date(2026, 8, 18), date(2026, 8, 19))

    def test_this_week_starts_on_monday(self) -> None:
        """The 17th is the Monday of the reference Thursday's week."""
        assert _bounds("this_week") == (date(2026, 8, 17), date(2026, 8, 24))

    def test_last_week_is_the_whole_previous_monday_to_sunday(self) -> None:
        assert _bounds("last_week") == (date(2026, 8, 10), date(2026, 8, 17))

    def test_this_month(self) -> None:
        assert _bounds("this_month") == (date(2026, 8, 1), date(2026, 9, 1))

    def test_last_month(self) -> None:
        assert _bounds("last_month") == (date(2026, 7, 1), date(2026, 8, 1))

    def test_this_quarter(self) -> None:
        """August is in Q3, so July through September."""
        assert _bounds("this_quarter") == (date(2026, 7, 1), date(2026, 10, 1))

    def test_last_quarter(self) -> None:
        assert _bounds("last_quarter") == (date(2026, 4, 1), date(2026, 7, 1))

    def test_this_year(self) -> None:
        assert _bounds("this_year") == (date(2026, 1, 1), date(2027, 1, 1))

    def test_last_year(self) -> None:
        assert _bounds("last_year") == (date(2025, 1, 1), date(2026, 1, 1))

    def test_the_week_convention_is_disclosed_on_the_window(self) -> None:
        """A weekly window says which convention produced it, because nothing governs it.

        Asserted rather than trusted: an answer that applied Monday-to-Sunday without disclosing it
        would be presenting an unapproved reporting standard as a fact.
        """
        window = resolve_window(_intent("this_week"), now=NOW)
        assert "Monday to Sunday" in window.resolution_rule
        assert "not approved" in window.resolution_rule


class TestRollingWindowsCountCalendarUnits:
    """`últimos N`. Today is included, and a month is a month."""

    def test_last_7_days_includes_today(self) -> None:
        assert _bounds("last_n_days", amount=7) == (date(2026, 8, 14), date(2026, 8, 21))

    def test_last_30_days(self) -> None:
        start, end = _bounds("last_n_days", amount=30)
        assert (start, end) == (date(2026, 7, 22), date(2026, 8, 21))
        assert (end - start).days == 30

    def test_last_12_weeks_is_84_days(self) -> None:
        start, end = _bounds("last_n_weeks", amount=12)
        assert (end - start).days == 84

    def test_last_6_months_is_calendar_months_and_not_180_days(self) -> None:
        """The assertion that the promise is kept: 181 days, not 180.

        Six calendar months back from 21 August 2026 is 21 February 2026. A `timedelta(days=180)`
        would land on 22 February and be wrong by a day — invisibly, and every month.
        """
        start, end = _bounds("last_n_months", amount=6)
        assert (start, end) == (date(2026, 2, 21), date(2026, 8, 21))
        assert (end - start).days == 181

    def test_last_n_years_crosses_a_leap_day(self) -> None:
        start, end = _bounds("last_n_years", amount=2)
        assert (start, end) == (date(2024, 8, 21), date(2026, 8, 21))
        assert (end - start).days == 730  # 2024 is a leap year, and its 29 February is inside

    def test_a_rolling_window_without_a_count_refuses(self) -> None:
        with pytest.raises(TemporalAmbiguity, match="positive count"):
            _bounds("last_n_days")

    def test_a_rolling_window_with_a_zero_count_refuses(self) -> None:
        with pytest.raises(TemporalAmbiguity):
            _bounds("last_n_days", amount=0)

    def test_a_rolling_window_is_marked_rolling(self) -> None:
        """Not `day`: asking again tomorrow moves the window, and an answer must say so."""
        window = resolve_window(_intent("last_n_days", amount=7), now=NOW)
        assert window.granularity is Granularity.ROLLING


class TestAbsoluteDatesAreTakenAsStated:
    """A named day, month, year or range. A missing year is ambiguity, never the current one."""

    def test_a_named_day(self) -> None:
        assert _bounds("absolute_day", year=2026, month=8, day=20) == (
            date(2026, 8, 20),
            date(2026, 8, 21),
        )

    def test_a_named_month(self) -> None:
        assert _bounds("absolute_month", year=2026, month=8) == (
            date(2026, 8, 1),
            date(2026, 9, 1),
        )

    def test_a_named_year(self) -> None:
        assert _bounds("absolute_year", year=2025) == (date(2025, 1, 1), date(2026, 1, 1))

    def test_february_in_a_common_year_has_28_days(self) -> None:
        start, end = _bounds("absolute_month", year=2026, month=2)
        assert (end - start).days == 28

    def test_february_in_a_leap_year_has_29_days(self) -> None:
        start, end = _bounds("absolute_month", year=2024, month=2)
        assert (end - start).days == 29
        assert end == date(2024, 3, 1)

    def test_a_month_with_no_year_refuses(self) -> None:
        """The owner's first named ambiguity: `julho` alone."""
        with pytest.raises(TemporalAmbiguity, match="needs a year"):
            _bounds("absolute_month", month=7)

    def test_an_impossible_day_refuses(self) -> None:
        with pytest.raises(TemporalAmbiguity, match="not a day"):
            _bounds("absolute_day", year=2026, month=4, day=31)

    def test_the_29th_of_february_refuses_in_a_common_year(self) -> None:
        with pytest.raises(TemporalAmbiguity, match="not a day"):
            _bounds("absolute_day", year=2026, month=2, day=29)

    def test_the_29th_of_february_resolves_in_a_leap_year(self) -> None:
        assert _bounds("absolute_day", year=2024, month=2, day=29) == (
            date(2024, 2, 29),
            date(2024, 3, 1),
        )

    def test_an_impossible_month_refuses(self) -> None:
        with pytest.raises(TemporalAmbiguity, match="not a month"):
            _bounds("absolute_month", year=2026, month=13)


class TestRangesIncludeBothEndsAndConvertOnce:
    """ "entre X e Y" means both. The exclusive end is produced here and nowhere else."""

    def test_a_range_of_days(self) -> None:
        """1 July to 20 August inclusive: 51 days, ending exclusive on the 21st."""
        start, end = _bounds("absolute_range", year=2026, month=7, day=1, end_month=8, end_day=20)
        assert (start, end) == (date(2026, 7, 1), date(2026, 8, 21))
        assert (end - start).days == 51

    def test_a_range_of_months(self) -> None:
        """ "de janeiro a março de 2026": three whole months."""
        start, end = _bounds("absolute_range", year=2026, month=1, end_month=3)
        assert (start, end) == (date(2026, 1, 1), date(2026, 4, 1))
        assert (end - start).days == 90

    def test_a_range_of_years(self) -> None:
        """ "entre 2025 e 2026": both years whole."""
        start, end = _bounds("absolute_range", year=2025, end_year=2026)
        assert (start, end) == (date(2025, 1, 1), date(2027, 1, 1))
        assert (end - start).days == 730

    def test_a_range_across_months_without_days(self) -> None:
        """ "entre julho e setembro de 2026": July, August and September."""
        start, end = _bounds("absolute_range", year=2026, month=7, end_month=9)
        assert (start, end) == (date(2026, 7, 1), date(2026, 10, 1))

    def test_an_inverted_range_of_days_refuses(self) -> None:
        with pytest.raises(TemporalAmbiguity, match="before it starts"):
            _bounds("absolute_range", year=2026, month=8, day=20, end_month=7, end_day=1)

    def test_an_inverted_range_of_months_refuses(self) -> None:
        with pytest.raises(TemporalAmbiguity, match="before it starts"):
            _bounds("absolute_range", year=2026, month=9, end_month=7)

    def test_an_inverted_range_of_years_refuses(self) -> None:
        with pytest.raises(TemporalAmbiguity, match="before it starts"):
            _bounds("absolute_range", year=2026, end_year=2025)

    def test_a_single_day_range_is_one_day_and_not_empty(self) -> None:
        """The boundary: same start and end means that one day, never zero days."""
        start, end = _bounds("absolute_range", year=2026, month=8, day=20, end_month=8, end_day=20)
        assert (end - start).days == 1


class TestComparisonsProduceTwoIndependentWindows:
    """Two windows and their alignment. Neither is derived from the other's bounds."""

    def _compare(self, expression: str, **fields: object):
        intent = TemporalIntent(
            kind=TemporalKind.COMPARISON,
            expression=expression,
            granularity=Granularity(fields.pop("granularity", Granularity.DAY)),  # pyright: ignore[reportArgumentType]
            **fields,  # pyright: ignore[reportArgumentType]
        )
        return resolve_comparison(intent, now=NOW)

    def test_day_against_day(self) -> None:
        result = self._compare("today", comparison_expression="yesterday")
        assert result.primary.start_inclusive == date(2026, 8, 20)
        assert result.comparison.start_inclusive == date(2026, 8, 19)
        assert result.primary.days == result.comparison.days == 1

    def test_week_against_week(self) -> None:
        result = self._compare("this_week", comparison_expression="last_week")
        assert result.primary.start_inclusive == date(2026, 8, 17)
        assert result.comparison.start_inclusive == date(2026, 8, 10)

    def test_month_against_month(self) -> None:
        result = self._compare("this_month", comparison_expression="last_month")
        assert result.primary.start_inclusive == date(2026, 8, 1)
        assert result.comparison.start_inclusive == date(2026, 7, 1)

    def test_year_against_year(self) -> None:
        result = self._compare("this_year", comparison_expression="last_year")
        assert result.primary.start_inclusive == date(2026, 1, 1)
        assert result.comparison.start_inclusive == date(2025, 1, 1)

    def test_two_named_months_against_each_other(self) -> None:
        """ "Compare os trials de julho com agosto de 2026" — both ends stated."""
        result = self._compare(
            "absolute_month",
            year=2026,
            month=7,
            comparison_expression="absolute_month",
            comparison_year=2026,
            comparison_month=8,
        )
        assert result.primary.start_inclusive == date(2026, 7, 1)
        assert result.comparison.start_inclusive == date(2026, 8, 1)
        assert result.alignment is Alignment.SAME_LENGTH  # both 31 days

    def test_the_same_month_of_two_years(self) -> None:
        result = self._compare(
            "absolute_month",
            year=2026,
            month=1,
            comparison_expression="absolute_month",
            comparison_year=2025,
            comparison_month=1,
        )
        assert result.primary.start_inclusive == date(2026, 1, 1)
        assert result.comparison.start_inclusive == date(2025, 1, 1)

    def test_the_preceding_period_is_derived_when_none_is_named(self) -> None:
        """ "em relação ao mês anterior" after a monthly question means the previous month."""
        result = self._compare("this_month")
        assert result.comparison.start_inclusive == date(2026, 7, 1)
        assert result.comparison.end_exclusive == date(2026, 8, 1)

    def test_a_preceding_period_that_does_not_follow_refuses(self) -> None:
        """ "o período anterior" after "últimos 7 dias" is not a calendar fact."""
        with pytest.raises(TemporalAmbiguity, match="no comparison period"):
            self._compare("last_n_days", amount=7)

    def test_different_lengths_are_reported(self) -> None:
        """February against January: 28 against 31, and the answer must carry the caveat."""
        result = self._compare(
            "absolute_month",
            year=2026,
            month=2,
            comparison_expression="absolute_month",
            comparison_year=2026,
            comparison_month=1,
        )
        assert result.alignment is Alignment.DIFFERENT_LENGTH

    def test_a_partial_window_against_a_complete_one_is_reported(self) -> None:
        """This week has not ended at the reference instant; last week has.

        Both are seven days, so a length check alone would call them comparable. They are not: one
        holds four days of data and the other seven.
        """
        result = self._compare("this_week", comparison_expression="last_week")
        assert result.alignment is Alignment.PARTIAL_AGAINST_COMPLETE

    def test_both_windows_are_resolved_against_one_instant(self) -> None:
        """The property that keeps a comparison self-consistent, asserted through the helper."""
        primary, comparison = windows_of(
            [_intent("today"), _intent("yesterday")],
            now=NOW,
        )
        assert primary.start_inclusive - comparison.start_inclusive == (
            date(2026, 8, 20) - date(2026, 8, 19)
        )


class TestCalendarBoundariesAndTheClockContract:
    """Turns of day, week, month and year; and the refusal that keeps the clock a parameter."""

    def test_the_turn_of_a_day(self) -> None:
        """One minute past midnight: today is the new day, not the one that just ended."""
        just_after = datetime(2026, 8, 21, 0, 1, tzinfo=ZONE)
        window = resolve_window(_intent("today"), now=just_after)
        assert window.start_inclusive == date(2026, 8, 21)

    def test_the_turn_of_a_week(self) -> None:
        """On a Monday, `this_week` starts that day and `last_week` is the seven days before."""
        monday = datetime(2026, 8, 24, 9, 0, tzinfo=ZONE)
        assert resolve_window(_intent("this_week"), now=monday).start_inclusive == date(2026, 8, 24)
        assert resolve_window(_intent("last_week"), now=monday).start_inclusive == date(2026, 8, 17)

    def test_the_turn_of_a_month(self) -> None:
        """On 1 September, `last_month` is the whole of August."""
        first = datetime(2026, 9, 1, 0, 30, tzinfo=ZONE)
        assert resolve_window(_intent("last_month"), now=first).start_inclusive == date(2026, 8, 1)
        assert resolve_window(_intent("last_month"), now=first).end_exclusive == date(2026, 9, 1)

    def test_the_turn_of_a_year(self) -> None:
        """On 1 January, `last_year` is the whole previous year and `this_year` has just begun."""
        new_year = datetime(2027, 1, 1, 0, 5, tzinfo=ZONE)
        assert resolve_window(_intent("last_year"), now=new_year).start_inclusive == date(
            2026, 1, 1
        )
        assert resolve_window(_intent("this_year"), now=new_year).start_inclusive == date(
            2027, 1, 1
        )

    def test_last_month_from_the_31st_does_not_overflow(self) -> None:
        """31 March: the previous month is the whole of February, not 3 March.

        This is the case a `timedelta` implementation gets wrong, and it is why `add_months` clamps.
        """
        end_of_march = datetime(2026, 3, 31, 12, 0, tzinfo=ZONE)
        window = resolve_window(_intent("last_month"), now=end_of_march)
        assert (window.start_inclusive, window.end_exclusive) == (
            date(2026, 2, 1),
            date(2026, 3, 1),
        )

    def test_six_months_back_from_a_leap_february(self) -> None:
        """Calendar arithmetic across a leap day, from inside the leap year."""
        leap = datetime(2024, 2, 29, 12, 0, tzinfo=ZONE)
        window = resolve_window(_intent("last_n_months", amount=6), now=leap)
        assert window.start_inclusive == date(2023, 9, 1)  # 1 March 2024 minus six months

    def test_a_naive_reference_instant_refuses(self) -> None:
        """Without a zone, "today" depends on which side of midnight the caller happens to be."""
        with pytest.raises(TemporalAmbiguity, match="no time zone"):
            resolve_window(_intent("today"), now=datetime(2026, 8, 20, 15, 0))

    def test_every_window_declares_the_canonical_zone(self) -> None:
        for expression, fields in (
            ("today", {}),
            ("last_month", {}),
            ("last_n_days", {"amount": 7}),
            ("absolute_year", {"year": 2025}),
        ):
            window = resolve_window(_intent(expression, **fields), now=NOW)
            assert window.timezone == "America/Sao_Paulo"

    def test_an_unknown_expression_refuses(self) -> None:
        """ "recentemente" is not a rule, and nothing nearby is substituted for it."""
        with pytest.raises(TemporalAmbiguity, match="no resolution rule"):
            _bounds("recently")

    def test_resolution_is_deterministic(self) -> None:
        """Two resolutions of one intent against one instant agree. Nothing reads a clock."""
        assert resolve_window(_intent("last_month"), now=NOW) == resolve_window(
            _intent("last_month"), now=NOW
        )


class TestAddMonthsIsTheOnlyMonthArithmetic:
    """The one shared primitive, asserted directly because every monthly rule depends on it."""

    @pytest.mark.parametrize(
        ("anchor", "months", "expected"),
        [
            (date(2026, 1, 31), 1, date(2026, 2, 28)),
            (date(2024, 1, 31), 1, date(2024, 2, 29)),
            (date(2026, 3, 31), -1, date(2026, 2, 28)),
            (date(2026, 12, 15), 1, date(2027, 1, 15)),
            (date(2026, 1, 15), -1, date(2025, 12, 15)),
            (date(2026, 8, 20), 12, date(2027, 8, 20)),
            (date(2026, 8, 20), -24, date(2024, 8, 20)),
            (date(2026, 5, 31), 1, date(2026, 6, 30)),
        ],
    )
    def test_the_day_clamps_to_the_target_month(
        self, anchor: date, months: int, expected: date
    ) -> None:
        assert add_months(anchor, months) == expected

    def test_zero_months_is_the_anchor(self) -> None:
        assert add_months(date(2026, 8, 20), 0) == date(2026, 8, 20)
