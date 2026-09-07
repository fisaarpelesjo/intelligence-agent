"""Completion-evidence tests for T061, T064, T065.

T061 evidence: never a fixed UTC offset; pre-2019 DST handled.
T064 evidence: ``TIMEZONE_OFFSET_MATERIAL`` when a canonical day draws on two
     reporting days.
T065 evidence: partial-vs-complete DENY; equivalent-partial ALLOW_WITH_CAVEAT
     naming the cutoff.

The DST assertions are the ones that matter. ``America/Sao_Paulo`` observed
daylight saving until 2019, so a range crossing a transition contains a 23-hour
day and a 25-hour day. A hard-coded ``-03:00`` gets both wrong, and gets them
wrong silently — the arithmetic still returns a number.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

import pytest

from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode, outcome_for
from semantic_catalog.contracts.source import Source
from semantic_catalog.loader.load import load_catalog
from semantic_catalog.periods.canonical import (
    CANONICAL_TIMEZONE,
    PeriodCompleteness,
    canonical_period,
    canonical_zone,
    day_length,
    local_midnight,
)
from semantic_catalog.periods.completeness import ComparisonShape, compare_periods
from semantic_catalog.periods.offsets import material_offsets, offset_for, offsets_for

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
ON = date(2026, 8, 11)


# --- T061 canonical zone ----------------------------------------------------


def test_the_canonical_zone_is_the_declared_one() -> None:
    assert CANONICAL_TIMEZONE == "America/Sao_Paulo"
    assert str(canonical_zone()) == "America/Sao_Paulo"


def test_dst_transitions_produce_short_and_long_days() -> None:
    """The property a fixed offset destroys.

    2018 is the last full year the canonical zone observed DST: clocks went
    forward at midnight on 4 November (a 23-hour day) and back at midnight on
    18 February, which makes 17 February 25 hours long.
    """
    assert day_length(date(2018, 11, 4)) == timedelta(hours=23)
    assert day_length(date(2018, 2, 17)) == timedelta(hours=25)
    assert day_length(date(2026, 8, 11)) == timedelta(hours=24)


def test_exactly_two_days_in_2018_were_not_24_hours() -> None:
    """Stated as a sweep so a tz-database change cannot pass unnoticed."""
    odd = {
        day
        for offset in range(365)
        if (day := date(2018, 1, 1) + timedelta(days=offset))
        and day_length(day) != timedelta(hours=24)
    }
    assert odd == {date(2018, 2, 17), date(2018, 11, 4)}


def test_a_fixed_offset_would_fail_these() -> None:
    """Stated as an assertion so the claim is checked, not asserted in prose."""
    fixed = timedelta(hours=24)
    assert day_length(date(2018, 11, 4)) != fixed
    assert day_length(date(2018, 2, 17)) != fixed


def test_the_local_hour_that_occurs_twice_is_resolvable() -> None:
    """Fall-back day: midnight resolves, and the day really is 25 hours."""
    midnight = local_midnight(date(2018, 2, 17))
    assert midnight.tzinfo is not None
    assert midnight.utcoffset() is not None
    assert day_length(date(2018, 2, 17)) == timedelta(hours=25)


def test_a_leap_day_is_a_real_day() -> None:
    period = canonical_period(date(2024, 2, 28), date(2024, 3, 1), on=ON)
    assert period.days == 3
    assert period.contains(date(2024, 2, 29))
    assert period.elapsed() == timedelta(days=3)


def test_a_range_crossing_a_dst_boundary_measures_real_elapsed_time() -> None:
    """Three calendar days, 71 real hours. A fixed offset would say 72."""
    period = canonical_period(date(2018, 11, 3), date(2018, 11, 5), on=ON)
    assert period.days == 3
    assert period.elapsed() == timedelta(days=3) - timedelta(hours=1)


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (date(2026, 7, 1), date(2026, 7, 31), PeriodCompleteness.COMPLETE),
        (date(2026, 8, 1), date(2026, 8, 11), PeriodCompleteness.PARTIAL),
        (date(2026, 8, 11), date(2026, 8, 11), PeriodCompleteness.PARTIAL),
        (date(2026, 9, 1), date(2026, 9, 30), PeriodCompleteness.OUTSIDE_COVERAGE),
    ],
)
def test_period_completeness_is_resolved_against_the_evaluation_date(
    start: date, end: date, expected: PeriodCompleteness
) -> None:
    assert canonical_period(start, end, on=ON).completeness is expected


def test_a_cutoff_is_kept_only_on_a_partial_period() -> None:
    partial = canonical_period(date(2026, 8, 11), date(2026, 8, 11), on=ON, cutoff=time(12))
    complete = canonical_period(date(2026, 7, 1), date(2026, 7, 31), on=ON, cutoff=time(12))
    assert partial.partial_cutoff == time(12)
    assert complete.partial_cutoff is None


def test_a_reversed_range_is_refused() -> None:
    with pytest.raises(ValueError, match=r"ends .* before it starts"):
        canonical_period(date(2026, 7, 31), date(2026, 7, 1), on=ON)


# --- T076 period properties: month boundaries and partial final periods -----


@pytest.mark.parametrize(
    "year, month, days",
    [(2026, 1, 31), (2026, 2, 28), (2024, 2, 29), (2026, 4, 30), (2026, 12, 31)],
)
def test_a_whole_month_counts_its_real_days(year: int, month: int, days: int) -> None:
    """Including the February that has 29. Off-by-one here is a silent error."""
    last = date(year, month, days)
    period = canonical_period(date(year, month, 1), last, on=date(2027, 1, 1))
    assert period.days == days
    assert period.elapsed() == timedelta(days=days)


def test_a_range_spanning_a_month_boundary_is_contiguous() -> None:
    period = canonical_period(date(2026, 1, 30), date(2026, 2, 2), on=ON)
    assert period.days == 4
    assert period.contains(date(2026, 1, 31))
    assert period.contains(date(2026, 2, 1))


def test_a_range_spanning_a_year_boundary_is_contiguous() -> None:
    period = canonical_period(date(2025, 12, 30), date(2026, 1, 2), on=ON)
    assert period.days == 4
    assert period.contains(date(2025, 12, 31))
    assert period.contains(date(2026, 1, 1))


def test_a_month_to_date_range_is_partial_and_a_finished_month_is_not() -> None:
    """The partial *final* period: today is in the range, so it is still forming."""
    month_to_date = canonical_period(date(2026, 8, 1), ON, on=ON)
    finished = canonical_period(date(2026, 7, 1), date(2026, 7, 31), on=ON)
    assert month_to_date.is_partial
    assert finished.is_complete


def test_the_day_before_today_completes_and_today_does_not() -> None:
    """The boundary itself, asserted rather than assumed."""
    assert canonical_period(ON - timedelta(days=1), ON - timedelta(days=1), on=ON).is_complete
    assert canonical_period(ON, ON, on=ON).is_partial


def test_a_leap_day_range_is_partial_only_when_it_reaches_today() -> None:
    leap = canonical_period(date(2024, 2, 29), date(2024, 2, 29), on=ON)
    assert leap.is_complete
    assert leap.days == 1


def test_a_month_that_crosses_a_dst_transition_still_counts_its_days() -> None:
    """November 2018 has 30 calendar days and 30 days minus an hour of real time."""
    period = canonical_period(date(2018, 11, 1), date(2018, 11, 30), on=ON)
    assert period.days == 30
    assert period.elapsed() == timedelta(days=30) - timedelta(hours=1)


# --- T064 offsets -----------------------------------------------------------


@pytest.fixture(scope="module")
def sources() -> dict[str, Source]:
    return dict(load_catalog(REPO / "semantic").sources)


def test_a_source_in_the_canonical_zone_has_no_material_offset(
    sources: dict[str, Source],
) -> None:
    offset = offset_for(sources["android_app"], on=ON)
    assert offset.offset == timedelta()
    assert not offset.material


def test_a_store_in_another_zone_is_material(sources: dict[str, Source]) -> None:
    """One canonical day draws on two of the store's reporting days."""
    offset = offset_for(sources["google_play"], on=ON)
    assert offset.offset != timedelta()
    assert offset.material
    assert offset.reporting_timezone == "America/Los_Angeles"
    assert "America/Los_Angeles" in offset.describe()


def test_the_offset_is_recomputed_per_date(sources: dict[str, Source]) -> None:
    """A zone that matches today may diverge across a transition."""
    winter = offset_for(sources["google_play"], on=date(2018, 7, 1))
    summer = offset_for(sources["google_play"], on=date(2018, 1, 15))
    assert winter.offset != summer.offset


def test_material_offsets_filters_to_what_must_be_disclosed(
    sources: dict[str, Source],
) -> None:
    everything = offsets_for(sources, ("android_app", "google_play", "website"), on=ON)
    material = material_offsets(everything)
    assert {o.source for o in material} == {"google_play"}


def test_native_zones_are_preserved_not_normalised(sources: dict[str, Source]) -> None:
    """The catalog cuts answers canonically and leaves the source's zone alone."""
    assert sources["galaxy_store"].reporting_timezone == "Asia/Seoul"
    assert offset_for(sources["galaxy_store"], on=ON).reporting_timezone == "Asia/Seoul"


# --- T065 comparisons -------------------------------------------------------


def test_two_complete_periods_compare_without_caveat() -> None:
    verdict = compare_periods(
        canonical_period(date(2026, 7, 1), date(2026, 7, 31), on=ON),
        canonical_period(date(2026, 6, 1), date(2026, 6, 30), on=ON),
    )
    assert verdict.shape is ComparisonShape.BOTH_COMPLETE
    assert verdict.reason_code is None
    assert verdict.permitted


def test_partial_against_complete_is_refused() -> None:
    """The most plausible-looking wrong chart the catalog can produce."""
    verdict = compare_periods(
        canonical_period(date(2026, 8, 11), date(2026, 8, 11), on=ON),
        canonical_period(date(2026, 8, 10), date(2026, 8, 10), on=ON),
    )
    assert verdict.shape is ComparisonShape.PARTIAL_VS_COMPLETE
    assert verdict.reason_code is ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON
    assert outcome_for(verdict.reason_code) is Outcome.DENY
    assert not verdict.permitted


def test_equivalent_partials_sharing_a_cutoff_are_permitted_and_labelled() -> None:
    subject = canonical_period(date(2026, 8, 11), date(2026, 8, 11), on=ON, cutoff=time(12))
    baseline = canonical_period(date(2026, 8, 11), date(2026, 8, 11), on=ON, cutoff=time(12))
    verdict = compare_periods(subject, baseline)
    assert verdict.shape is ComparisonShape.EQUIVALENT_PARTIAL
    assert verdict.reason_code is ReasonCode.EQUIVALENT_PARTIAL_COMPARISON
    assert outcome_for(verdict.reason_code) is Outcome.ALLOW_WITH_CAVEAT
    assert verdict.cutoff == time(12)
    assert "12:00" in verdict.detail


def test_partials_with_no_declared_cutoff_are_refused() -> None:
    """A cutoff is never inferred; guessing one manufactures the equivalence."""
    both = canonical_period(date(2026, 8, 11), date(2026, 8, 11), on=ON)
    verdict = compare_periods(both, both)
    assert verdict.shape is ComparisonShape.MISMATCHED_CUTOFF
    assert not verdict.permitted


def test_partials_with_different_cutoffs_are_refused() -> None:
    subject = canonical_period(date(2026, 8, 11), date(2026, 8, 11), on=ON, cutoff=time(12))
    baseline = canonical_period(date(2026, 8, 11), date(2026, 8, 11), on=ON, cutoff=time(18))
    verdict = compare_periods(subject, baseline)
    assert verdict.shape is ComparisonShape.MISMATCHED_CUTOFF
    assert not verdict.permitted


def test_a_future_period_cannot_be_compared() -> None:
    verdict = compare_periods(
        canonical_period(date(2026, 9, 1), date(2026, 9, 30), on=ON),
        canonical_period(date(2026, 7, 1), date(2026, 7, 31), on=ON),
    )
    assert verdict.shape is ComparisonShape.OUTSIDE_COVERAGE
    assert verdict.reason_code is ReasonCode.RANGE_OUTSIDE_COVERAGE
