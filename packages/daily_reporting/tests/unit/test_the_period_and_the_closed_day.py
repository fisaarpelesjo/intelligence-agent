"""A complete week, and the day that is closed — `T816`, `T817`.

**Six days against seven is a movement this feature would have invented**, and a week
with a hole in it looks fine in a row count — which is why the two failures are refused
separately and named separately.

## `last_complete_week` — `T1331`, added 2026-09-05

The weekly of `FR-1317` runs from a timer, and a timer that fires late must not report a
different period. **Mutations, each seen red and restored by `cp` + `cmp`**: the naive
composition `week_ending(closed_day_at(instant))`, which is right on a Monday and a rolling
window on every other day → `2 failed, 11 passed`; the instant read in UTC instead of in the
business zone, which is a whole week wrong for the two hours either side of midnight →
`2 failed, 11 passed`. Both reddened the same two nodes, which is the right answer: one node
holds the anchor and the other holds the clock, and neither defect is visible on a Monday
morning in the middle of the day.

A third defect came from ADVERSARIAL REVIEW of that same commit rather than from a mutation:
`astimezone` does not raise on a NAIVE instant, it assumes the machine's zone — so the guard
`journal.py` and `schedule/derive.py` already carry was missing here, where the price is a week
instead of a day. Guard removed → `1 failed, 13 passed`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from daily_reporting.contracts import ReportReasonCode, ReportRefusal
from daily_reporting.numbers.period import (
    BUSINESS_ZONE,
    COMPLETE_WEEK,
    closed_day_at,
    last_complete_week,
    refuse_unless_closed,
    refuse_unless_complete,
    week_ending,
)

pytestmark = pytest.mark.unit

#: An instant, passed in. **This package computes no `now()`** — a run is called and
#: receives its instant as a parameter, the same constraint `005`, `006` and `007` carry.
AN_INSTANT = datetime(2026, 8, 28, 3, 5, tzinfo=UTC)


def test_the_closed_day_is_the_day_before_the_local_date() -> None:
    """`03:05Z` on the 28th is `00:05` in Sao Paulo, so the closed day is the 27th."""
    assert closed_day_at(AN_INSTANT) == date(2026, 8, 27)


def test_the_zone_is_resolved_and_not_a_fixed_offset() -> None:
    """A day boundary read from a fixed offset is wrong twice a year."""
    assert str(BUSINESS_ZONE) == "America/Sao_Paulo"


def test_the_day_in_progress_is_refused() -> None:
    """The source's window ends yesterday, so today is a day it does not hold."""
    today_locally = AN_INSTANT.astimezone(BUSINESS_ZONE).date()
    with pytest.raises(ReportRefusal) as refused:
        refuse_unless_closed(today_locally, AN_INSTANT)
    assert refused.value.code is ReportReasonCode.REPORT_DAY_NOT_CLOSED


def test_a_future_day_is_refused_too() -> None:
    """The same refusal, because *not yet closed* covers both."""
    ahead = AN_INSTANT.astimezone(BUSINESS_ZONE).date() + timedelta(days=3)
    with pytest.raises(ReportRefusal):
        refuse_unless_closed(ahead, AN_INSTANT)


def test_the_closed_day_passes() -> None:
    day = closed_day_at(AN_INSTANT)
    assert refuse_unless_closed(day, AN_INSTANT) == day


def test_a_week_is_seven_consecutive_days_ending_on_the_day_given() -> None:
    week = week_ending(date(2026, 8, 27))
    assert len(week) == COMPLETE_WEEK
    assert week[-1] == date(2026, 8, 27)
    assert week[0] == date(2026, 8, 21)
    assert refuse_unless_complete(week) == week


def test_a_short_week_is_refused_and_the_count_is_named() -> None:
    short = week_ending(date(2026, 8, 27))[1:]
    with pytest.raises(ReportRefusal) as refused:
        refuse_unless_complete(short)
    assert refused.value.code is ReportReasonCode.REPORT_PERIOD_NOT_COMPLETE
    assert str(COMPLETE_WEEK - 1) in refused.value.detail


def test_seven_days_with_a_hole_are_refused_separately() -> None:
    """**The one that looks fine in a row count.** Seven days, not seven consecutive."""
    holed = (*week_ending(date(2026, 8, 27))[1:], date(2026, 8, 19))
    assert len(set(holed)) == COMPLETE_WEEK
    with pytest.raises(ReportRefusal) as refused:
        refuse_unless_complete(holed)
    assert refused.value.code is ReportReasonCode.REPORT_PERIOD_NOT_COMPLETE
    assert "consecutive" in refused.value.detail


def test_a_repeated_day_does_not_pad_a_short_week() -> None:
    """Otherwise six days plus a duplicate would pass as seven."""
    padded = (*week_ending(date(2026, 8, 27))[1:], date(2026, 8, 27))
    with pytest.raises(ReportRefusal):
        refuse_unless_complete(padded)


#: Monday 09:00 in the business zone — the instant `FR-1317` names for the weekly. Written in
#: UTC because that is what a timer hands over, and the conversion is part of what is asserted.
A_MONDAY_MORNING = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

#: The civil week that closed before it: Monday 31/08 to Sunday 06/09.
THE_WEEK_THAT_CLOSED = tuple(date(2026, 8, 31) + timedelta(days=offset) for offset in range(7))


def test_the_weekly_reads_the_civil_week_that_closed() -> None:
    """`FR-1317`, `FR-1318`: Monday to Sunday, whole, and behind the run."""
    week = last_complete_week(A_MONDAY_MORNING)
    assert week == THE_WEEK_THAT_CLOSED
    assert week[0].weekday() == 0 and week[-1].weekday() == 6
    assert len(week) == COMPLETE_WEEK
    #: It is a week by the same instrument the report already uses on any seven days.
    assert refuse_unless_complete(week) == week


def test_the_period_does_not_move_because_the_run_was_late() -> None:
    """**The reason this is not `week_ending(closed_day_at(instant))`.**

    That composition is right on a Monday and silently wrong on every other day: one day later
    it returns Tuesday..Monday, a rolling window sharing six days with the week it is named
    after. A timer fires late, a retry lands on Wednesday, and nothing would have said the
    period had shifted. Every instant inside one civil week must answer the same week.
    """
    within_the_same_week = [
        A_MONDAY_MORNING + timedelta(days=days, hours=hours)
        #: Monday 09:00 local through Sunday 21:00 local. **Six days and twenty-three hours
        #: would be the NEXT Monday**, which is a different civil week and would have made this
        #: node fail for the right reason — it did, and the fixture was the thing that was wrong.
        for days, hours in ((0, 0), (1, 5), (3, 14), (5, 2), (6, 12))
    ]
    assert {last_complete_week(instant) for instant in within_the_same_week} == {
        THE_WEEK_THAT_CLOSED
    }
    #: And it DOES move the moment a new week starts — otherwise the node above would pass
    #: over a function that returns one fixed week forever.
    next_monday = A_MONDAY_MORNING + timedelta(days=7)
    assert last_complete_week(next_monday) == tuple(
        date(2026, 9, 7) + timedelta(days=offset) for offset in range(7)
    )


def test_the_week_in_progress_is_never_the_week_reported() -> None:
    """Including on a Sunday evening, when six of its seven days are already closed.

    A period that is one day short is the `FR-809` refusal said about weeks, and returning it
    would be this feature inventing a movement rather than refusing one.
    """
    sunday_night = datetime(2026, 9, 6, 23, 30, tzinfo=BUSINESS_ZONE)
    week = last_complete_week(sunday_night)
    assert sunday_night.date() not in week
    assert week[-1] < sunday_night.date()


def test_the_week_is_read_in_the_business_zone_and_not_in_the_timer_s() -> None:
    """**Two hours of UTC decide which week this is**, and the wrong one is a whole week off.

    At 02:00 UTC on Monday it is still 23:00 Sunday in Sao Paulo, so the week containing that
    Sunday has NOT closed. Reading the instant in UTC would report a week the source's own day
    boundary says is still open — the same defect `BUSINESS_ZONE` exists to prevent for the day.
    """
    still_sunday_locally = datetime(2026, 9, 7, 2, 0, tzinfo=UTC)
    assert last_complete_week(still_sunday_locally) == tuple(
        date(2026, 8, 24) + timedelta(days=offset) for offset in range(7)
    )
    assert last_complete_week(still_sunday_locally) != THE_WEEK_THAT_CLOSED


def test_an_instant_with_no_zone_refuses_instead_of_answering_the_machine_s_week() -> None:
    """**Found by review of the commit that added the function, not by a mutation.**

    `datetime.astimezone` does not raise on a naive value: it assumes the machine's zone and
    converts, silently. `journal.py` and `schedule/derive.py` already refuse for that reason, and
    here the price is higher — `2026-09-07T02:00` is Sunday 23:00 in Sao Paulo and Monday in UTC,
    so reading it as either without being told is a whole week, not an hour.
    """
    naive = datetime(2026, 9, 7, 2, 0)
    with pytest.raises(ValueError, match="no zone"):
        last_complete_week(naive)
    #: And the aware instant naming the same moment still answers, so the refusal is about the
    #: missing zone and not about the hour.
    assert last_complete_week(naive.replace(tzinfo=UTC)) == tuple(
        date(2026, 8, 24) + timedelta(days=offset) for offset in range(7)
    )
