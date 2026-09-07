"""`T902`, `T903` — the hour comes from a measurement, and moves when the measurement does.

The defect this guards is the one spec `009` was written around: a trigger registered before the
warehouse finishes turns a **correct** refusal into a report that never arrives, every day, in
silence. Nothing about that failure is loud — from his phone it looks like a quiet day.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from daily_reporting.schedule.derive import earliest_admissible

pytestmark = pytest.mark.contract

SAO_PAULO = ZoneInfo("America/Sao_Paulo")

#: Measured 2026-08-31T04:24Z against the real project, `SELECT` only, from
#: `example-project-id.example_dataset.__TABLES__`: the last completion of `tbl_summary`.
MEASURED_COMPLETION = datetime(2026, 8, 30, 6, 0, 54, 829000, tzinfo=UTC)


def test_the_hour_is_the_first_whole_hour_after_the_measured_rebuild() -> None:
    """`SC-901` over the number actually measured."""
    start = earliest_admissible(MEASURED_COMPLETION, zone=SAO_PAULO)

    assert start.utc == datetime(2026, 8, 30, 7, 0, tzinfo=UTC)
    #: **Strictly after the rebuild**, which is the whole property.
    assert start.utc > MEASURED_COMPLETION
    #: And the slack is a consequence of the rule, not a number anybody chose.
    assert start.utc - MEASURED_COMPLETION >= timedelta(minutes=59)


def test_a_rebuild_that_lands_exactly_on_the_hour_still_advances() -> None:
    """Strictly after, and the word does work.

    A run starting in the same second as the last write reads a table mid-replace. Were this `<`
    instead of `<=`, the derived margin here would be **zero**.
    """
    on_the_hour = datetime(2026, 8, 30, 6, 0, 0, tzinfo=UTC)
    start = earliest_admissible(on_the_hour, zone=SAO_PAULO)

    assert start.utc == datetime(2026, 8, 30, 7, 0, tzinfo=UTC)
    assert start.utc > on_the_hour


def test_a_moved_upstream_moves_the_hour() -> None:
    """`SC-902`, `FR-904` — **a derivation that answers the same thing whatever it measures is not
    a derivation.**

    The upstream hour has moved once already: `tbl_summary` went from `04:00` to `06:00` UTC on
    2026-06-08, for a reason internal to the neighbouring project. Nothing here would have noticed.
    """
    answers = {
        earliest_admissible(moment, zone=SAO_PAULO).utc
        for moment in (
            datetime(2026, 8, 30, 4, 0, 12, tzinfo=UTC),
            datetime(2026, 8, 30, 6, 0, 54, tzinfo=UTC),
            datetime(2026, 8, 30, 7, 10, 0, tzinfo=UTC),
        )
    }
    assert len(answers) == 3, "the derivation returned the same hour for three different rebuilds"
    assert datetime(2026, 8, 30, 8, 0, tzinfo=UTC) in answers


def test_the_local_side_is_converted_and_not_computed_by_subtracting_three() -> None:
    """`FR-905`, in both directions.

    `America/Sao_Paulo` holds a single offset across 2026 — `UTC-3`, no daylight change — and that
    is a fact **with a date on it**, not an arithmetic rule. The conversion goes through the zone so
    that the year the rule changes, this stops being wrong silently.
    """
    start = earliest_admissible(MEASURED_COMPLETION, zone=SAO_PAULO)

    assert start.local.tzinfo is not None
    assert start.local.utcoffset() is not None
    #: The SAME instant, said twice.
    assert start.local.astimezone(UTC) == start.utc
    #: What goes into the scheduler, and it is the local clock by name.
    assert start.local_clock == "04:00"

    #: A zone with a different offset gives a different clock from the same instant. Were the local
    #: side computed by subtracting three, this would still read `04:00`.
    assert earliest_admissible(MEASURED_COMPLETION, zone=ZoneInfo("UTC")).local_clock == "07:00"


def test_a_rebuild_without_a_zone_is_refused() -> None:
    """Assuming a naive datetime is UTC is exactly how an instant three hours off reaches a
    scheduler. It is refused instead."""
    with pytest.raises(ValueError, match="carries no zone"):
        earliest_admissible(datetime(2026, 8, 30, 6, 0, 54), zone=SAO_PAULO)
