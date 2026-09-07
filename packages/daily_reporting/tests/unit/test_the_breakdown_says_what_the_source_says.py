"""Four ways the breakdown would have shipped a WRONG number — `T1309`, `SC-1301`.

Every node here exists because running the report against the real warehouse on 2026-09-04
printed something false. None of them was caught by a suite: the maths was right in the
fixtures and wrong on the day, which is the whole argument for `T1309` existing before
`T1310`.

The four, in the order they were found:

1. **A rate's tail was SUMMED.** `Trial conversion` printed a tail of *1,95 %* over a hundred
   countries — a number that is not a percentage of anything. A rate's tail is
   `SUM(numerator)/SUM(denominator)` over the rows that were cut.
2. **No sample floor.** The country ranking opened with a country whose entire sample was a
   handful of cases, because a rate over two cases outranks a rate over three hundred.
   `SC-1301`: below the floor the rate is NOT asserted.
3. **The scale was not applied.** The view stores a rate as a fraction of one and the caller
   reads that scale once, for the KPI's own value. The breakdown did not go through it, so
   Brazil's conversion rendered `0,03 %` where the source says `1,24 %` — a hundred times out.
4. **Both days were aggregated.** The read carries two days in one query. Partitioning without
   filtering made every partition the sum of a day the report does not claim to be about:
   Brazil read `3,38 %` against the source's `1,24 %`.

Each is driven separately. A single "the breakdown is correct" node would have gone green the
day three of the four checks were removed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from daily_reporting.numbers.variation import as_percent
from daily_reporting.report.breakdown import BreakdownGovernance, cut_to_top
from daily_reporting.view.reading import sample_size
from daily_reporting.view.shape import ViewRow

pytestmark = pytest.mark.unit

_GOVERNANCE = BreakdownGovernance(
    top_n=2,
    axis_labels=(("country", "por pais"),),
    tail_label="demais",
    tail_noun="valores",
    sample_floor=30,
)


def _rate(numerator: int, denominator: int) -> ViewRow:
    return {
        "aggregation_class": "RATIO",
        "numerator": numerator,
        "denominator": denominator,
    }


def test_a_rates_tail_is_aggregated_and_not_summed() -> None:
    """**Defect 1.** Summing rates produces a percentage of nothing.

    Four partitions. The cut keeps `c` (30 %) and `b` (20 %) — `big` ties with `b` on rate and
    loses the tie on name — so the tail holds `big` (60/300) and `a` (10/100). Summing their
    rates gives 30 %; aggregating their rows gives 70/400 = 17,5 %. The two differ, which is
    what makes this node worth having.
    """
    partitions = (
        ("big", (_rate(60, 300),)),
        ("a", (_rate(10, 100),)),
        ("b", (_rate(10, 50),)),
        ("c", (_rate(15, 50),)),
    )
    breakdown = cut_to_top(partitions, _GOVERNANCE, "country", "value", sample_floor=0)
    assert breakdown is not None
    assert breakdown.tail_count == 2
    assert breakdown.tail_total == Decimal(70) / Decimal(400)
    assert breakdown.tail_total != Decimal("0.20") + Decimal("0.10")


def test_a_partition_under_the_floor_is_not_ranked_and_is_counted_apart() -> None:
    """**Defect 2**, `SC-1301`. A rate over two cases must not outrank a rate over three
    hundred, and it must not vanish either.

    **`OD-144` (2026-09-06) changed where it goes, and not whether it counts.** It fell into
    the tail, and the tail then answered two questions with one number: on the real message
    `Australia 0,00 %` ranked above a tail reading `4,47 %`, because that tail also held
    partitions whose rate the floor refuses to assert. Now the withheld are counted on their
    own — still IN the reconciliation, which he refused to give up — and no number is stated
    for them, which is exactly what the floor decided about them.
    """
    partitions = (
        ("tiny", (_rate(1, 2),)),
        ("real", (_rate(60, 300),)),
        ("other", (_rate(10, 100),)),
    )
    breakdown = cut_to_top(partitions, _GOVERNANCE, "country", "value", sample_floor=30)
    assert breakdown is not None
    assert [value for value, _n in breakdown.lines] == ["real", "other"]
    assert "tiny" not in [value for value, _n in breakdown.lines]
    assert breakdown.tail_count == 0
    assert breakdown.withheld_count == 1
    assert breakdown.has_withheld
    #: The reconciliation he approved: every partition is in exactly one of the three.
    assert len(breakdown.lines) + breakdown.tail_count + breakdown.withheld_count == 3
    #: **And the withheld part no longer moves the tail's number**, which is the half that
    #: made the ranking read as nonsense. The tail is empty here, so it states nothing.
    assert breakdown.tail_total == Decimal(0)


def test_the_floor_does_not_apply_where_there_is_no_denominator() -> None:
    """A count of five is a count of five. Refusing it would refuse the measurement."""
    partitions = (("a", ({"aggregation_class": "COUNT", "value": 5},)),)
    breakdown = cut_to_top(partitions, _GOVERNANCE, "country", "value", sample_floor=30)
    assert breakdown is not None
    assert breakdown.lines == (("a", Decimal(5)),)


def test_sample_size_is_the_denominator_for_a_rate_and_nothing_otherwise() -> None:
    assert sample_size((_rate(1, 200), _rate(2, 100))) == Decimal(300)
    assert sample_size(({"aggregation_class": "COUNT", "value": 5},)) is None


def test_an_axis_where_nothing_clears_the_floor_renders_no_heading() -> None:
    """Silence rather than a heading over nothing — the same rule as an empty breakdown."""
    partitions = (("tiny", (_rate(1, 2),)), ("small", (_rate(1, 3),)))
    assert cut_to_top(partitions, _GOVERNANCE, "country", "value", sample_floor=30) is None


def test_the_scale_reaches_every_number_including_the_tail() -> None:
    """**Defect 3.** The KPI's value went through `as_percent` and the breakdown did not.

    Driven through the same function the caller uses, so the two cannot drift: what the report
    does to its headline number is what it does to every part of it.
    """
    partitions = (
        ("a", (_rate(30, 300),)),
        ("b", (_rate(10, 100),)),
        ("c", (_rate(5, 100),)),
    )
    breakdown = cut_to_top(partitions, _GOVERNANCE, "country", "value", sample_floor=0)
    assert breakdown is not None
    scaled = breakdown.scaled(lambda number: as_percent(number, "pct"))
    assert scaled.lines[0][1] == Decimal(10)
    assert scaled.tail_total == Decimal(5)
    assert breakdown.lines[0][1] == Decimal("0.1"), "the original must not be mutated"


def test_partitioning_two_days_is_a_different_number_than_partitioning_one() -> None:
    """**Defect 4**, stated as the difference it makes rather than as a rule.

    The caller filters to the closed day. This node exists so that a change removing the
    filter has something to fail: the two answers are asserted to DIFFER, so a fixture where
    they coincide cannot make the guard vacuous.
    """
    closed = (_rate(4, 323),)
    both = (_rate(4, 323), _rate(20, 300))
    one_day = cut_to_top((("Brazil", closed),), _GOVERNANCE, "country", "value")
    two_days = cut_to_top((("Brazil", both),), _GOVERNANCE, "country", "value")
    assert one_day is not None and two_days is not None
    assert one_day.lines[0][1] != two_days.lines[0][1]
    assert one_day.lines[0][1] == Decimal(4) / Decimal(323)
