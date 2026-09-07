"""The decomposition either closes against the whole, or it is refused — `SC-1302`.

Each node here holds ONE property of `report/contribution.py`, and each was seen red under a
mutation named on its own docstring. A "who pulled it" list that does not add up is a list
that invents an explanation, so the interesting nodes are the ones that watch the REFUSAL.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from daily_reporting.report.contribution import Verdict, contributions_of


def _count(value: str, number: int) -> dict[str, object]:
    return {"country": value, "aggregation_class": "COUNT", "value": number}


def _rate(value: str, numerator: int, denominator: int) -> dict[str, object]:
    return {
        "country": value,
        "aggregation_class": "RATIO",
        "numerator": numerator,
        "denominator": denominator,
    }


def test_the_parts_that_close_are_published_with_their_shares() -> None:
    """Mutation: return RECONCILED unconditionally — the refusal nodes below go red."""
    block = contributions_of(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 60), _count("Mexico", 70)],
        "value",
        "country",
    )

    assert block.verdict is Verdict.RECONCILED
    assert block.may_publish
    assert block.residual == 0
    assert [part.value for part in block.parts] == ["Brasil", "Mexico"]
    assert [part.deviation for part in block.parts] == [Decimal(-40), Decimal(20)]


def test_a_sum_that_does_not_close_is_refused_and_never_published() -> None:
    """`SC-1302`. Mutation: make the residual a warning instead of a verdict — red here.

    **The gap is the sample floor**, which is the way production actually makes one: a part
    whose rate was measured over too few cases is not described, and the total still contains
    it. Chile's four cases are below the floor, so its movement is in the whole and in no line.

    The first version of this node manufactured the gap with a part seen on one day only, and
    that was the defect rather than the fixture: such a part is now counted in the sum — it is
    part of the total either way — and merely not printed. Driving the engine against the real
    warehouse refused every block, every day, for exactly that reason.
    """
    before = [_rate("Brasil", 100, 1000), _rate("Chile", 1, 4)]
    after = [_rate("Brasil", 200, 1000), _rate("Chile", 3, 4)]

    block = contributions_of(before, after, "value", "country", sample_floor=30)

    assert [part.value for part in block.parts] == ["Brasil"]
    assert block.verdict is Verdict.DID_NOT_RECONCILE
    assert not block.may_publish


def test_a_part_seen_on_only_one_day_counts_in_the_sum_and_prints_no_line() -> None:
    """**Two questions, and the first version of this node answered one with the other.**

    A country absent yesterday did not sell nothing yesterday, so its `before` stays ``None``
    and no line claims a movement from zero. But it IS part of the total either way, so the
    conservation counts it — and that is arithmetic about the sum, not a reading of the part.

    Treating those as one question dropped the part from the sum and then demanded the sum
    close, which refused every real block: measured against the warehouse on 2026-09-04, 190
    countries with dozens seen on one side only.

    Mutation: intersect the two periods again — red, and the verdict flips to a refusal.
    """
    block = contributions_of(
        [_count("Brasil", 100)],
        [_count("Brasil", 60), _count("Chile", 30)],
        "value",
        "country",
    )

    assert [part.value for part in block.parts] == ["Brasil", "Chile"]
    assert block.verdict is Verdict.RECONCILED
    assert block.residual == 0

    chile = next(part for part in block.parts if part.value == "Chile")
    assert chile.before is None
    assert not chile.was_measured_twice
    assert chile.deviation == Decimal(30)


def test_over_one_hundred_percent_publishes_and_says_the_others_compensated() -> None:
    """Mutation: refuse when a share exceeds one — this goes red, and the finding disappears.

    Brasil falls 40 while Mexico rises 20: the total moved 20, and Brasil alone explains 200%
    of it. That is precisely the reading worth surfacing, not a reconciliation failure.
    """
    block = contributions_of(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 60), _count("Mexico", 70)],
        "value",
        "country",
    )

    assert block.verdict is Verdict.RECONCILED
    assert block.may_publish
    assert block.others_compensated
    biggest = block.parts[0]
    assert biggest.share_of(block.total_deviation) == Decimal(2)


def test_a_total_that_did_not_move_is_not_attempted_and_divides_by_nothing() -> None:
    """Mutation: drop the zero-deviation guard — this raises `ZeroDivisionError` instead."""
    block = contributions_of(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 120), _count("Mexico", 30)],
        "value",
        "country",
    )

    assert block.verdict is Verdict.NOT_ATTEMPTED
    assert block.parts == ()
    assert not block.may_publish
    assert not block.others_compensated


def test_not_attempted_is_not_the_same_answer_as_did_not_reconcile() -> None:
    """Mutation: collapse the two into one verdict — red here.

    One says the check was tried and failed; the other says there was nothing to check. A
    reader handed the same word for both cannot tell a broken decomposition from an absent one.
    """
    nothing_moved = contributions_of(
        [_count("Brasil", 100)], [_count("Brasil", 100)], "value", "country"
    )
    did_not_close = contributions_of(
        [_rate("Brasil", 100, 1000), _rate("Chile", 1, 4)],
        [_rate("Brasil", 200, 1000), _rate("Chile", 3, 4)],
        "value",
        "country",
        sample_floor=30,
    )

    assert nothing_moved.verdict is Verdict.NOT_ATTEMPTED
    assert did_not_close.verdict is Verdict.DID_NOT_RECONCILE
    assert nothing_moved.verdict is not did_not_close.verdict


def test_each_part_of_a_rate_is_its_own_quotient_and_never_a_mean_of_rates() -> None:
    """Mutation: average the parts' rates — red, because the denominators differ.

    The same defect `F1` was shipped with and measured against the warehouse: a rate is
    `SUM(num)/SUM(den)` over that part's own rows, so a part with ten times the volume weighs
    ten times as much inside its own number.
    """
    before = [_rate("Brasil", 10, 100), _rate("Brasil", 90, 900), _rate("Mexico", 5, 100)]
    after = [_rate("Brasil", 20, 100), _rate("Brasil", 90, 900), _rate("Mexico", 5, 100)]

    block = contributions_of(before, after, "value", "country")

    brasil = next(part for part in block.parts if part.value == "Brasil")
    assert brasil.before == Decimal("0.1")
    assert brasil.after == Decimal("0.11")


def test_a_part_measured_over_too_few_cases_is_left_out_of_the_attribution() -> None:
    """`SC-1301`'s floor. Mutation: ignore `sample_floor` — red, the thin part comes back.

    A rate over a handful of cases is not a rate to blame a movement on.
    """
    before = [_rate("Brasil", 100, 1000), _rate("Chile", 1, 4)]
    after = [_rate("Brasil", 200, 1000), _rate("Chile", 3, 4)]

    with_floor = contributions_of(before, after, "value", "country", sample_floor=30)
    without_floor = contributions_of(before, after, "value", "country")

    assert [part.value for part in with_floor.parts] == ["Brasil"]
    assert [part.value for part in without_floor.parts] == ["Brasil", "Chile"]


def test_a_value_the_governance_excludes_is_never_a_part() -> None:
    """Mutation: drop the `excluded` argument on the way in — red, the total row becomes a part."""
    block = contributions_of(
        [_count("Brasil", 100), _count("(Total)", 100)],
        [_count("Brasil", 60), _count("(Total)", 60)],
        "value",
        "country",
        excluded=("(Total)",),
    )

    assert [part.value for part in block.parts] == ["Brasil"]


@pytest.mark.parametrize("rows", [[], [{"country": "Brasil", "aggregation_class": "COUNT"}]])
def test_a_period_with_no_number_is_not_attempted_rather_than_guessed(
    rows: list[dict[str, object]],
) -> None:
    """A period nobody measured yields no attribution, and never a deviation against zero.

    Mutation: fall back to zero for the absent total AND let the empty decomposition through
    — red, and the report ships a movement from zero that no day ever made. It takes BOTH
    halves, measured: the two guards catch the same input, and either one alone still refuses.
    """
    block = contributions_of(rows, [_count("Brasil", 60)], "value", "country")

    assert block.verdict is Verdict.NOT_ATTEMPTED
    assert not block.may_publish


def test_the_source_marker_is_out_of_the_whole_as_well_as_out_of_the_parts() -> None:
    """**A marker the governance excludes made one refusal CERTAIN, not possible.**

    `(Total)` is the source's own aggregate sitting in the same column as its parts —
    `semantic/dimensions/game.yaml` measured seventy thousand rows carrying it. `partition_by`
    drops it from the parts; a total read over the raw rows kept it. The whole was then the
    parts plus their own aggregate, and the `game` axis could never close, on any day.

    **Mutation**: read the totals over the raw rows again — red, and the block is refused for
    a gap exactly the size of the marker.
    """
    before = [_count("Brasil", 100), _count("Mexico", 50), _count("(Total)", 150)]
    after = [_count("Brasil", 60), _count("Mexico", 40), _count("(Total)", 100)]

    block = contributions_of(before, after, "value", "country", excluded=("(Total)",))

    assert [part.value for part in block.parts] == ["Brasil", "Mexico"]
    assert block.total_before == Decimal(150)
    assert block.verdict is Verdict.RECONCILED
    assert block.residual == 0
