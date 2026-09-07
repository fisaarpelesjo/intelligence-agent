"""Which days are compared, and which day the report speaks of — `T816`, `T817`.

## Week against previous week, and the reason is measured

`OD-14-E`. Day against the same day, `New trials` already varies **10,4 %** typically
with a `p90` of **46 %**, and **196 of 387 days** would cross a 10 % line. Weekly, the
typical variation falls to **6,9 %**. *The daily series is noisy at every threshold,
which is a property of the data and not of the threshold* — so no threshold choice
rescues a daily comparison, and the period is where the fix belongs.

## And a short week is refused rather than reported over

Six days against seven is a movement this feature would have invented. `FR-809`.

## The day the report speaks of is the CLOSED one

`FR-802`, `OD-15-C`. The source rebuilds at 06:00 UTC and its window ends yesterday, so
a report about *today* is a report about a day the source does not hold. **The instant
is a parameter** — this package computes no `now()`, which is the same constraint
`005`, `006` and `007` carry.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from ..contracts import ReportReasonCode, ReportRefusal

__all__ = [
    "BUSINESS_ZONE",
    "COMPLETE_WEEK",
    "closed_day_at",
    "last_complete_week",
    "refuse_unless_closed",
    "refuse_unless_complete",
    "week_ending",
]

#: The canonical business time zone, resolved through the IANA database rather than a
#: fixed offset. A day boundary read from a fixed offset is wrong twice a year.
BUSINESS_ZONE: Final = ZoneInfo("America/Sao_Paulo")

#: Seven. Named rather than spelled inline so the refusal below and the builder above
#: cannot disagree about what "complete" means.
COMPLETE_WEEK: Final = 7


def closed_day_at(instant: datetime, zone: ZoneInfo = BUSINESS_ZONE) -> date:
    """The last **closed** day at ``instant``: the day before its local date."""
    return instant.astimezone(zone).date() - timedelta(days=1)


def refuse_unless_closed(day: date, instant: datetime, zone: ZoneInfo = BUSINESS_ZONE) -> date:
    """``day`` back, or a refusal when it is the day still in progress or later."""
    local = instant.astimezone(zone).date()
    if day >= local:
        raise ReportRefusal(
            ReportReasonCode.REPORT_DAY_NOT_CLOSED,
            f"{day.isoformat()} is not closed at {local.isoformat()} local; the daily report "
            f"speaks of the closed day and the source's window ends yesterday",
        )
    return day


def week_ending(day: date) -> tuple[date, ...]:
    """The seven consecutive days ending on ``day``, oldest first."""
    return tuple(day - timedelta(days=offset) for offset in reversed(range(COMPLETE_WEEK)))


def last_complete_week(instant: datetime, zone: ZoneInfo = BUSINESS_ZONE) -> tuple[date, ...]:
    """The last CIVIL week — Monday to Sunday — that is entirely closed at ``instant``.

    `FR-1317` asks for a message every Monday at 09:00, and `FR-1318` makes its comparison
    week against week. **A civil week is not a rolling seven days**, and the difference is the
    whole point of this function: *the week that closed* is what a person means on a Monday,
    and it must not move because the run was late.

    ## Why this is not `week_ending(closed_day_at(instant))`

    That composition is right on a Monday and silently wrong on every other day. At Monday
    09:00 local the closed day is Sunday, so the seven days ending there ARE the civil week —
    and one day later they are Tuesday..Monday, a rolling window that shares six days with the
    week it is named after. The weekly runs from a timer, timers fire late, a retry happens on
    Tuesday, and nothing in the composition would say the period had shifted. So the anchor is
    the WEEKDAY, computed here, rather than the day the machine happened to wake up.

    ## Monday is the first day, and the calendar says so rather than this module

    `date.weekday()` is zero on Monday, which is the same anchor `semantic_catalog`'s
    `periods/temporal.py` uses for its own `last_week` rule. Two calendars in one repository
    that disagree about which day starts a week is a defect waiting for a Sunday, so this reads
    the standard library's answer instead of choosing one.

    **Today's own week is never returned, even on a Sunday evening**: the current week is not
    closed until it ends, and `refuse_unless_closed` already carries that rule for the day.

    ## A naive instant REFUSES, and here that is worth a whole week

    `datetime.astimezone` does not raise on a naive value — it assumes the MACHINE's zone and
    converts from there, silently. `journal.py` and `schedule/derive.py` already refuse for that
    reason, and this function needs it more than either: for the daily a misread zone costs one
    day, and here any instant that crosses the Sunday-to-Monday midnight costs SEVEN. A weekly
    runner handing `datetime.utcnow()` — still a common idiom, and naive — would report the wrong
    week with no refusal and no line in any log.
    """
    if instant.tzinfo is None:
        message = "instant carries no zone; refusing to assume one and answer the wrong week"
        raise ValueError(message)
    local = instant.astimezone(zone).date()
    this_week_started = local - timedelta(days=local.weekday())
    return week_ending(this_week_started - timedelta(days=1))


def refuse_unless_complete(days: Sequence[date]) -> tuple[date, ...]:
    """``days`` back as a tuple, or a refusal when it is not a whole seven-day week.

    Both failures are named separately in the message, because *you gave me six days*
    and *your seven days have a hole in them* are different problems with different
    fixes — and the second is the one that looks fine in a row count.
    """
    ordered = tuple(sorted(set(days)))
    if len(ordered) != COMPLETE_WEEK:
        raise ReportRefusal(
            ReportReasonCode.REPORT_PERIOD_NOT_COMPLETE,
            f"{len(ordered)} distinct days were given where a complete week is {COMPLETE_WEEK}; "
            f"comparing an incomplete week against a whole one invents a movement",
        )
    if ordered[-1] - ordered[0] != timedelta(days=COMPLETE_WEEK - 1):
        raise ReportRefusal(
            ReportReasonCode.REPORT_PERIOD_NOT_COMPLETE,
            f"the {COMPLETE_WEEK} days given are not consecutive, spanning "
            f"{(ordered[-1] - ordered[0]).days + 1} days; a week with a hole is not a week",
        )
    return ordered
