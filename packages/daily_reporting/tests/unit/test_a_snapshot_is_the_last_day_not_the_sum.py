"""A snapshot is a LEVEL, and seven levels do not add up — `SC-1306`, `T1330`.

:func:`daily_reporting.view.reading.aggregate` had one branch, `RATIO`, and `SNAPSHOT` fell
through to the same sum a `COUNT` takes. Handed one day at a time by every caller, that was
invisible; handed a WEEK by the `T1331` weekly, `MAU` reads about seven times the number of
people who used the product.

**The source said so first.** The warehouse measurement of 2026-08-26 recorded that MRR, MAU
and paid subscribers are snapshots and that adding their days inflates them, and the query
side of this repository has taken the last covered day since it was written. The two readers
of one view disagreed, and these nodes are which one is right.

**The additive control is the other half.** A `COUNT` over the same seven days must STILL sum,
because trials really do add up: a fix that made every class read its last day would pass the
first node and report one day's trials as the week's.

**Mutation** (`tasks.md`, `T1330`): the snapshot summed across the week — the branch removed —
→ `3 failed, 4 passed`, measured 2026-09-05 22:44 -03:
`test_a_snapshot_over_a_week_is_the_last_day`,
`test_the_last_day_is_summed_across_its_own_partitions` and
`test_a_snapshot_row_with_no_day_refuses_instead_of_answering_nothing` red. The third is red
because the refusal lives inside the branch: with no branch, a dateless snapshot row is summed
like any other, which is the same defect wearing a quieter face.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from daily_reporting.contracts import ReportRefusal
from daily_reporting.view.reading import aggregate, aggregate_by

pytestmark = pytest.mark.unit

#: Seven days, one row each, and **the sum differs from the last day by about seven** — the
#: shape of the defect, and the reason the numbers sit close together rather than far apart. A
#: level moves slowly, which is what makes the inflation invisible to anyone reading one figure.
SEVEN_DAYS: tuple[dict[str, object], ...] = (
    {"aggregation_class": "SNAPSHOT", "event_date": "2026-08-30", "value": 9000},
    {"aggregation_class": "SNAPSHOT", "event_date": "2026-08-31", "value": 9020},
    {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-01", "value": 9041},
    {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-02", "value": 9063},
    {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-03", "value": 9080},
    {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-04", "value": 9102},
    {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-05", "value": 9117},
)

#: The sum of the seven against the last day of the seven.
SUMMED = Decimal(63423)
LAST_DAY = Decimal(9117)

#: The same seven days and the same seven numbers, one word changed.
SEVEN_DAYS_COUNTED = tuple({**row, "aggregation_class": "COUNT"} for row in SEVEN_DAYS)


def test_a_snapshot_over_a_week_is_the_last_day() -> None:
    """The figure of a period is the level it ended at."""
    got = aggregate(SEVEN_DAYS, "value")
    assert got == LAST_DAY, got
    assert got != SUMMED, (
        f"the level was added across the week: {SUMMED} against a real {LAST_DAY}, inflated "
        f"by {SUMMED / LAST_DAY:.2f}"
    )


def test_the_last_day_is_summed_across_its_own_partitions() -> None:
    """**Days are not summed; the last day's rows are.**

    The view is granular by country and by game, so the last day is many rows and the level is
    their total. Taking the maximum value, or the first row of the last day, would pass the
    node above and report one country as the whole business.
    """
    last_day_in_three_parts = (
        {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-04", "value": 9102},
        {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-05", "value": 5000},
        {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-05", "value": 3000},
        {"aggregation_class": "SNAPSHOT", "event_date": "2026-09-05", "value": 1117},
    )
    assert aggregate(last_day_in_three_parts, "value") == LAST_DAY


def test_a_count_over_the_same_week_still_sums() -> None:
    """The additive control: trials really do add up, and this keeps the branch honest."""
    assert aggregate(SEVEN_DAYS_COUNTED, "value") == SUMMED


def test_a_snapshot_of_one_day_is_that_day() -> None:
    """The case every caller passes today, unchanged by this task."""
    assert aggregate(SEVEN_DAYS[-1:], "value") == LAST_DAY


def test_a_snapshot_row_with_no_day_refuses_instead_of_answering_nothing() -> None:
    """It carried a number, so ``None`` would report a measured figure as an absence."""
    with pytest.raises(ReportRefusal):
        aggregate(({"aggregation_class": "SNAPSHOT", "value": 9117},), "value")


def test_a_count_row_with_no_day_is_untouched() -> None:
    """The refusal lives on the snapshot branch only; nothing that worked stops working."""
    assert aggregate(({"aggregation_class": "COUNT", "value": 41},), "value") == Decimal(41)


def test_a_snapshot_is_broken_down_by_nothing() -> None:
    """A part whose last row is older would be reported on another part's day.

    The query side declares no axis for this class for the same reason, and the parts of a
    level that were measured on different days do not add up to the level.
    """
    parts = tuple({**row, "country": "Brazil"} for row in SEVEN_DAYS)
    with pytest.raises(ReportRefusal):
        aggregate_by(parts, "value", "country")
