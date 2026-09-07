"""A rate per partition is the partition's own rate — `T1304`, `FR-1301`.

The whole of `F1`'s correctness argument is one sentence: **`aggregate` is reused, not
rewritten.** It computes a ratio as ``SUM(numerator) / SUM(denominator)`` over the rows it is
handed, so handing it one partition's rows gives that partition's rate. Nothing about the
function changes, and this file exists to make that claim measurable rather than asserted.

## The failure this guards is the one that looks right

Averaging the parts' rates is the obvious wrong answer, and it is wrong *invisibly*: it agrees
with the correct number whenever the denominators happen to be equal, which is exactly the
shape of a hand-made fixture and never the shape of a real day. So the fixtures below carry
**deliberately unequal denominators**, and the mean-of-means answer is computed alongside and
asserted to DIFFER — a node whose two candidate answers coincide proves nothing.

## And the one-partition identity

With a single partition the partitioned result has to equal the whole-set result exactly. That
is the cheapest possible statement of "nothing changed for the report that exists today", and
it is what makes the F1 change safe to ship before anything renders.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from daily_reporting.view.reading import aggregate, aggregate_by, partition_by, sample_size
from daily_reporting.view.shape import ViewRow

pytestmark = pytest.mark.unit

#: A ratio KPI whose denominators are unequal **in both directions** — across countries AND
#: across the rows of one country. The second half was added after a mutation survived: with
#: Brasil's two rows at 20/200 and 10/100 both meaning 10%, averaging per row gave the same
#: answer as `SUM/SUM` and the sharpest node did not fire. A fixture whose two candidate
#: answers coincide proves nothing, and that is true row by row as well as country by country.
#:
#: Now: Brasil is 30/250 = 12% while its rows alone read 10% and 20%; Mexico is 40/100 = 40%.
#: The whole set is 70/350 = 20%, and the mean of the two countries' rates is 26%.
_RATIO_ROWS: tuple[ViewRow, ...] = (
    {"country": "Brasil", "aggregation_class": "RATIO", "numerator": 20, "denominator": 200},
    {"country": "Brasil", "aggregation_class": "RATIO", "numerator": 10, "denominator": 50},
    {"country": "Mexico", "aggregation_class": "RATIO", "numerator": 40, "denominator": 100},
)

_COUNT_ROWS: tuple[ViewRow, ...] = (
    {"country": "Brasil", "aggregation_class": "COUNT", "value": 5},
    {"country": "Brasil", "aggregation_class": "COUNT", "value": 7},
    {"country": "Mexico", "aggregation_class": "COUNT", "value": 3},
)


def test_one_partition_equals_the_whole_set() -> None:
    """The report that exists today is unchanged when there is nothing to split."""
    single = tuple({**row, "country": "Brasil"} for row in _RATIO_ROWS)
    whole = aggregate(single, "value")
    parts = aggregate_by(single, "value", "country")
    assert len(parts) == 1
    assert parts[0][1] == whole


def test_each_partitions_rate_is_its_own_sum_over_its_own_sum() -> None:
    """`SUM(num)/SUM(den)` per partition — the property `aggregate` already had."""
    parts = dict(aggregate_by(_RATIO_ROWS, "value", "country"))
    assert parts["Brasil"] == Decimal(30) / Decimal(250)
    assert parts["Mexico"] == Decimal(40) / Decimal(100)


def test_the_mean_of_the_parts_is_a_different_number_and_that_is_the_point() -> None:
    """**Anti-vacuity.** If the two candidate answers agreed, the node above would be free.

    Measured on this fixture: the correct whole-set rate is 20% and the mean of the parts'
    rates is 26%. A partition implementation that averaged would pass every "looks like a
    rate" check and be wrong by six points on three rows.
    """
    parts = [number for _value, number in aggregate_by(_RATIO_ROWS, "value", "country")]
    correct = aggregate(_RATIO_ROWS, "value")
    mean_of_parts = sum(parts, Decimal(0)) / Decimal(len(parts))
    assert correct == Decimal(70) / Decimal(350)
    assert mean_of_parts != correct, "the fixture stopped separating the two answers"


def test_a_count_kpi_partitions_by_adding_its_own_rows() -> None:
    parts = dict(aggregate_by(_COUNT_ROWS, "value", "country"))
    assert parts["Brasil"] == Decimal(12)
    assert parts["Mexico"] == Decimal(3)


def test_a_row_with_no_value_for_the_dimension_is_dropped_and_not_named() -> None:
    """An "(unknown)" bucket would be a word nobody decided, in a report that refuses those."""
    rows = (*_COUNT_ROWS, {"aggregation_class": "COUNT", "value": 99})
    assert dict(aggregate_by(rows, "value", "country")).keys() == {"Brasil", "Mexico"}
    assert all(value.strip() for value, _group in partition_by(rows, "country"))


def test_a_partition_whose_number_is_absent_is_omitted_rather_than_zero() -> None:
    """`aggregate` keeps `None` and `Decimal(0)` apart; one level up must not merge them."""
    rows = (
        *_COUNT_ROWS,
        {"country": "Chile", "aggregation_class": "COUNT", "value": None},
    )
    parts = dict(aggregate_by(rows, "value", "country"))
    assert "Chile" not in parts, "an absent number was reported as a partition"


def test_the_partition_order_is_first_appearance_and_decides_no_ranking() -> None:
    """Ranking is the cut's business (`FR-1303`), not this function's.

    Kept separate on purpose: a partitioner that also sorted would make the cut impossible to
    change without touching the maths.
    """
    assert [value for value, _group in partition_by(_RATIO_ROWS, "country")] == [
        "Brasil",
        "Mexico",
    ]


# --- the aggregate that sits beside its parts — `T1306`, `FR-1305` -----------------------
#
# `semantic/dimensions/game.yaml` measured it: 70,532 rows carry `(Total)` in the `game`
# column, all of one source KPI. The axis declares `permitted_values: open`, which filters
# nothing — so a breakdown by game that does not exclude the marker ranks an aggregate above
# every real game and counts the whole set twice.
#
# The marker is a value of the SOURCE, not a word of his, which is why it is named in the
# governed file and not here: this package writes no source value of its own.

_WITH_AGGREGATE: tuple[ViewRow, ...] = (
    {"game": "(Total)", "aggregation_class": "COUNT", "value": 300},
    {"game": "Valorant", "aggregation_class": "COUNT", "value": 200},
    {"game": "Fortnite", "aggregation_class": "COUNT", "value": 60},
    {"game": "CS2", "aggregation_class": "COUNT", "value": 40},
)


def test_the_aggregate_marker_is_excluded_from_the_partition() -> None:
    """It would otherwise rank FIRST — above every game it is the sum of."""
    parts = dict(aggregate_by(_WITH_AGGREGATE, "value", "game", excluded=("(Total)",)))
    assert set(parts) == {"Valorant", "Fortnite", "CS2"}
    assert sum(parts.values()) == Decimal(300)


def test_without_the_exclusion_the_aggregate_is_counted_beside_its_parts() -> None:
    """**Anti-vacuity, and it is the measurement that justifies the exclusion existing.**

    Same rows, no exclusion: the parts now sum to 600 for a set whose real total is 300 —
    every number double-counted, and the marker ranked first.
    """
    parts = dict(aggregate_by(_WITH_AGGREGATE, "value", "game"))
    assert "(Total)" in parts
    assert sum(parts.values()) == Decimal(600)


def test_the_exclusion_drops_the_rows_and_not_just_the_line() -> None:
    """Excluded at the PARTITION, so no number of the marker survives anywhere.

    Dropping it at the cut instead would leave a total that includes a number no line shows —
    which is the shape of a report that cannot be reconciled.
    """
    partitions = partition_by(_WITH_AGGREGATE, "game", excluded=("(Total)",))
    assert all(value != "(Total)" for value, _group in partitions)
    assert sum(len(group) for _value, group in partitions) == 3


def test_a_column_with_no_declared_exclusion_keeps_every_value() -> None:
    """Exclusions are the exception, measured once. They are not expected of an axis."""
    assert len(partition_by(_RATIO_ROWS, "country")) == 2


class TestARateIsReadInPairs:
    """**Measured defect, 2026-09-04: the two halves were read independently.**

    A row carrying a numerator and a null denominator put its number on top of the rate and
    nothing underneath. `Not renewed (%)` has 809 such rows in ninety days and
    `Cancellations (%)` has 194 — measured against the warehouse, not imagined.

    The number he read moved: `Not renewed (%)` went out as `0,6228 %` on 2026-08-15 where the
    paired arithmetic gives `0,5028 %`. Eight of the last ninety days differ, and the error is
    always in the same direction, because an unmatched numerator can only push a rate up.
    """

    @staticmethod
    def _rate(numerator: object, denominator: object) -> dict[str, object]:
        return {
            "aggregation_class": "RATIO",
            "numerator": numerator,
            "denominator": denominator,
        }

    def test_a_row_missing_its_denominator_contributes_to_neither_half(self) -> None:
        """Mutation: read the two columns independently again — red, and the rate inflates."""
        rows = [self._rate(50, 1000), self._rate(30, None)]

        assert aggregate(rows, "value") == Decimal(50) / Decimal(1000)

    def test_a_row_missing_its_numerator_contributes_to_neither_half(self) -> None:
        """The other direction, which deflates instead of inflating."""
        rows = [self._rate(50, 1000), self._rate(None, 500)]

        assert aggregate(rows, "value") == Decimal(50) / Decimal(1000)

    def test_a_rate_whose_every_row_is_unpaired_is_absent_and_never_a_number(self) -> None:
        """Absent is not zero, and it is not an infinity either."""
        assert aggregate([self._rate(30, None), self._rate(None, 500)], "value") is None

    def test_the_sample_floor_counts_the_cases_the_rate_was_measured_over(self) -> None:
        """Mutation: count every denominator — red, and the floor passes a rate it exists to stop.

        A denominator whose row carries no numerator is not a case this rate was measured over.
        Counting it sets the floor against a larger sample than the number came from.
        """
        rows = [self._rate(1, 4), self._rate(None, 500)]

        assert sample_size(rows) == Decimal(4)

    def test_a_fully_paired_set_reads_exactly_as_it_did_before(self) -> None:
        """The property that makes the pairing safe: nothing moves where nothing was unpaired."""
        rows = [self._rate(10, 100), self._rate(90, 900)]

        assert aggregate(rows, "value") == Decimal(100) / Decimal(1000)
        assert sample_size(rows) == Decimal(1000)
