"""The threshold comes from the series — `T818`, `T820`, `T821`, `T823`.

## The mutation this file is built around

**A node fails when the threshold is replaced by a constant, INCLUDING a constant equal
to today's `p90`** — `SC-806`. That is the whole difficulty: today's correct answer and
tomorrow's wrong one are the same string, so a node comparing against the right number
passes forever while the alerts drift away from the data.

So the check is drivability, the same shape as everywhere else in this feature: handed
two series, the computation answers two thresholds, and a constant answers the same to
both.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

import pytest

from daily_reporting.alert.threshold import (
    ALERT_PERCENTILE,
    minimum_comparable_periods,
    percentile,
    refuse_unless_series_is_long_enough,
    threshold_from,
)
from daily_reporting.contracts import ReportReasonCode, ReportRefusal

pytestmark = pytest.mark.unit

#: Two series with different spreads. Neither resembles a real KPI: a fixture shaped
#: like the measured `p90` table would put that table in source, which `FR-812` forbids.
A_TIGHT_SERIES = tuple(Decimal(value) for value in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
A_WIDE_SERIES = tuple(Decimal(value) for value in (1, 2, 3, 4, 5, 6, 7, 8, 9, 400))

Computer = Callable[[Sequence[Decimal]], Decimal]


def answers_the_series_it_is_handed(computer: Computer) -> bool:
    """**The one predicate**, used by the real computation and by every stand-in."""
    return computer(A_TIGHT_SERIES) != computer(A_WIDE_SERIES)


def test_the_threshold_answers_the_series_it_is_handed() -> None:
    assert answers_the_series_it_is_handed(threshold_from), (
        "the same threshold came back for a tight series and a wide one, so it is not "
        "reading the series it was given"
    )


def test_a_constant_equal_to_todays_answer_would_fail_this() -> None:
    """**The dangerous stand-in**: correct for one series, frozen for every other."""
    todays_answer = threshold_from(A_TIGHT_SERIES)

    def frozen_at_todays_p90(_series: Sequence[Decimal]) -> Decimal:
        return todays_answer

    def a_flat_twenty(_series: Sequence[Decimal]) -> Decimal:
        return Decimal(20)

    for stand_in in (frozen_at_todays_p90, a_flat_twenty):
        assert not answers_the_series_it_is_handed(stand_in), (
            "the predicate accepts a constant threshold"
        )


def test_the_percentile_is_the_one_he_chose() -> None:
    chosen = Decimal("0.90")
    assert chosen == ALERT_PERCENTILE


def test_the_percentile_interpolates_rather_than_picking_a_neighbour() -> None:
    """Ten points, `p90` at position 8.1 — between the ninth and the tenth."""
    assert percentile(A_TIGHT_SERIES, ALERT_PERCENTILE) == Decimal("9.1")


def test_a_fall_and_a_rise_are_the_same_size_of_movement() -> None:
    """A threshold built from signed values sits below the falls and above the rises."""
    rises = tuple(Decimal(value) for value in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
    falls = tuple(-value for value in rises)
    assert threshold_from(rises) == threshold_from(falls)


def test_an_empty_series_refuses_instead_of_receiving_a_flat_threshold() -> None:
    with pytest.raises(ReportRefusal) as refused:
        threshold_from(())
    assert refused.value.code is ReportReasonCode.ALERT_THRESHOLD_NOT_COMPUTABLE


def test_the_minimum_is_derived_from_the_counts_it_is_handed() -> None:
    """Handed different counts it answers a different minimum. `FR-814`."""
    assert minimum_comparable_periods([53, 54, 55, 56]) != minimum_comparable_periods(
        [8, 9, 10, 11]
    )


def test_the_minimum_excludes_a_short_series_and_admits_a_full_one() -> None:
    """Driven one week short and one week over, which is what `SC-808` asks for.

    The counts here are the ones measured on 2026-08-27, used as an INPUT rather than
    written as configuration: seventeen KPIs between 53 and 56, and three at 3, 19 and
    26. The rule excludes exactly those three.
    """
    counts = [*([54] * 17), 3, 19, 26]
    minimum = minimum_comparable_periods(counts)
    assert refuse_unless_series_is_long_enough("full", minimum, minimum) == minimum
    for short in (3, 19, 26):
        with pytest.raises(ReportRefusal) as refused:
            refuse_unless_series_is_long_enough("short", short, minimum)
        assert refused.value.code is ReportReasonCode.ALERT_SERIES_TOO_SHORT
    with pytest.raises(ReportRefusal):
        refuse_unless_series_is_long_enough("one_short", minimum - 1, minimum)


def test_the_minimum_never_falls_below_two() -> None:
    """A single comparison has no distribution to take a percentile of."""
    assert minimum_comparable_periods([1, 1, 1]) == 2


def test_no_counts_at_all_refuses_rather_than_inventing_a_minimum() -> None:
    with pytest.raises(ReportRefusal) as refused:
        minimum_comparable_periods([])
    assert refused.value.code is ReportReasonCode.ALERT_THRESHOLD_NOT_COMPUTABLE
