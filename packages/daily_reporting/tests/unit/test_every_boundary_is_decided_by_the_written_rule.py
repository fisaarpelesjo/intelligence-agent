"""Every boundary comparison in this package, with a fixture EXACTLY on the line — `OD-124`.

## What was measured, and it is the number this file exists to drive to zero

Every `<`, `<=`, `>` and `>=` in `daily_reporting/src` was inverted one at a time, the whole suite
run, the file restored byte for byte. Measured 2026-09-04: **24 comparisons in code, 11 bite, 13
stay green**. The record said six — that was one shape (`<` against `<=`) on an earlier date; with
`>`/`>=` counted and the package grown by F2 and F3, it is thirteen. Same class as `809`→`813`.

A comparison whose inversion stays green is a node written where the two operators AGREE. They
disagree at exactly one value — the boundary — and no fixture sat there.

## The rule decides which side the exact case falls on, never the code

**This is the constraint the reviewer put on the work and it changes what a "fix" is.** A fixture
that pins whatever the operator does today freezes an off-by-one nobody measured and calls it a
bite — the same defect from the other side. So every node below CITES the written rule that says
which way the exact case goes. **One boundary had no written rule when this file was first
written** — the alert at exactly its own `p90` — and that node asserted the two decided sides and
NOTHING at equality, until the owner decided it (`OD-125`, 2026-09-04: reaching the threshold is
crossing it). It is the last section, and it is now the thirteenth decided boundary.

Format, so there are not thirteen styles: one case exactly on the line, one on each side, and the
inverted operator seen red.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from daily_reporting.alert.rule import evaluate
from daily_reporting.numbers.variation import VariationUnit
from daily_reporting.report.breakdown import (
    BreakdownGovernance,
    BreakdownGovernanceError,
    cut_to_top,
)
from daily_reporting.report.contribution import (
    Contribution,
    ContributionBlock,
    ContributionGovernance,
    ContributionGovernanceError,
    Verdict,
    contributions_of,
    pulls_of,
)
from daily_reporting.report.references import ReferenceGovernance, ReferenceGovernanceError
from daily_reporting.report.summary import (
    UNMOVED,
    Line,
    _indicator_lines,  # pyright: ignore[reportPrivateUsage] -- the node measures the private helper directly
    mark_for,
)
from daily_reporting.view.shape import ViewRow

pytestmark = pytest.mark.unit

AN_INSTANT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
A_DAY = date(2026, 9, 3)


# --- `SC-1301`: the sample floor, twice ----------------------------------------
#
# `report_governance/breakdown.yaml:89` — "ABAIXO DO PISO A TAXA NAO E AFIRMADA". *Below* the floor,
# so a part measured over EXACTLY the floor is not below it and its rate IS asserted. The two
# operators differ at 30 and nowhere else; every fixture in this section sits at 29, 30 and 31.

_FLOOR = 30
_CUT = BreakdownGovernance(
    top_n=5,
    axis_labels=(("country", "por pais"),),
    tail_label="demais",
    tail_noun="valores",
    sample_floor=_FLOOR,
)


def _rate(country: str, numerator: int, denominator: int) -> ViewRow:
    return {
        "aggregation_class": "RATIO",
        "country": country,
        "numerator": numerator,
        "denominator": denominator,
    }


def _partitions(*rows: ViewRow) -> list[tuple[str, list[ViewRow]]]:
    return [(str(row["country"]), [row]) for row in rows]


def test_a_part_measured_over_exactly_the_floor_is_ranked_and_one_under_it_is_not() -> None:
    """`breakdown.py` — `size < sample_floor`. The word in his file is ABAIXO."""
    breakdown = cut_to_top(
        _partitions(
            _rate("under", 3, _FLOOR - 1), _rate("on", 3, _FLOOR), _rate("over", 3, _FLOOR + 1)
        ),
        _CUT,
        "country",
        "value",
        sample_floor=_FLOOR,
    )
    assert breakdown is not None
    ranked = [value for value, _n in breakdown.lines]
    assert "on" in ranked, (
        "a part measured over exactly the floor was withheld; the rule says BELOW"
    )
    assert "over" in ranked
    assert "under" not in ranked
    #: **`OD-144` (2026-09-06) split the tail's two populations.** The withheld part is counted
    #: on its own now — it never fitted the same line as the parts that were merely cut, and
    #: the number beside those has no meaning for a part whose rate is not asserted. What did
    #: not change is that it is still COUNTED: he refused dropping it, because that contradicts
    #: the reconciliation he approved.
    assert breakdown.tail_count == 0
    assert breakdown.withheld_count == 1
    assert len(breakdown.lines) + breakdown.tail_count + breakdown.withheld_count == 3


def test_a_contribution_part_measured_over_exactly_the_floor_stays_in_the_sum() -> None:
    """`contribution.py` — the same `size < sample_floor`, one function over."""
    before = [_rate("under", 2, _FLOOR - 1), _rate("on", 2, _FLOOR), _rate("over", 2, _FLOOR + 1)]
    after = [_rate("under", 3, _FLOOR - 1), _rate("on", 3, _FLOOR), _rate("over", 3, _FLOOR + 1)]
    block = contributions_of(before, after, "value", "country", sample_floor=_FLOOR)
    names = [part.value for part in block.parts]
    assert "on" in names, "exactly the floor was dropped from the attribution; the rule says BELOW"
    assert "over" in names
    assert "under" not in names


# --- governance validation: the limit is where the sentence puts it ---------------------


def test_a_floor_of_exactly_zero_is_a_valid_floor_and_minus_one_is_not() -> None:
    """`breakdown.py` — `floor < 0`. The refusal's own sentence: *a floor is a whole number of
    cases, never negative*. Zero is a whole number of cases — it is the floor being OFF — and the
    package's every signature defaults to it."""
    document = {
        "top_n": 5,
        "axis_labels": {"country": "por pais"},
        "tail_label": "demais",
        "tail_noun": "valores",
        "sample_floor": 0,
    }
    assert BreakdownGovernance.from_document(document).sample_floor == 0
    with pytest.raises(BreakdownGovernanceError, match="never negative"):
        BreakdownGovernance.from_document({**document, "sample_floor": -1})


def _contribution_document(tolerance: str) -> dict[str, object]:
    return {
        "heading": "quem puxou",
        "heading_emoji": "x",
        "deviation_noun": "desvio",
        "approximately": "cerca de",
        "became": "virou",
        "unit_singular": "parte",
        "unit_plural": "partes",
        "others": "demais",
        "others_noun": "valores",
        "compensated": "compensaram",
        "quiet_day": "dia quieto",
        #: `T1334`: as quatro palavras da peça 6 passaram a ser exigidas pelo carregador.
        "discarded_heading": "descartado",
        "inside_band": "dentro da banda",
        "none_of": "nenhum",
        "concentrated": "concentrado",
        "dash": "-",
        "heading_alert": "quem puxou o alerta",
        "tolerance": tolerance,
    }


def test_a_tolerance_of_exactly_zero_is_valid_and_demands_an_exact_close() -> None:
    """`contribution.py` — `tolerance < 0`. The refusal's sentence: *a negative slack would refuse
    a sum that closes exactly*. Zero slack is the strictest legitimate setting — it accepts ONLY
    the exact close — and is not the defect the sentence describes."""
    assert ContributionGovernance.from_document(_contribution_document("0")).tolerance == 0
    with pytest.raises(ContributionGovernanceError, match="negative slack"):
        ContributionGovernance.from_document(_contribution_document("-0.01"))


def test_one_day_back_is_a_valid_reference_and_zero_is_the_day_itself() -> None:
    """`references.py` — `days_back < 1`. The refusal's sentence: *a reference at zero days back
    is the day itself, which compares a number with itself*. One day back is a different day."""
    assert (
        ReferenceGovernance.from_document(
            {"days_back": 1, "label": "D-1", "against": "vs"}
        ).days_back
        == 1
    )
    with pytest.raises(ReferenceGovernanceError, match="the day itself"):
        ReferenceGovernance.from_document({"days_back": 0, "label": "D-0", "against": "vs"})


# --- `SC-1302`: the reconciliation and the over-100% reading ---------------------------


def test_a_residual_exactly_at_the_tolerance_closes_and_one_past_it_does_not() -> None:
    """`contribution.py` — `abs(residual) <= abs(total_deviation) * tolerance`.

    `report_governance/contribution.yaml`: *quanto o residual pode se afastar ... e a conta ainda
    FECHAR ... Acima dela o bloco NAO PUBLICA*. ABOVE the tolerance refuses, so a residual of
    exactly the tolerance still closes. Total moved 100; with 1 % slack the exact case is a residual
    of 1.
    """
    # The total is measured over the SAME rows the partitions come from (`_axis_rows`), so a
    # residual can only come from a part that is IN the total and OUT of the parts -- and the one
    # thing that does that is the sample floor: Chile's four cases are below it, so its rate is
    # not described while the total still contains it. Same construction as the neighbouring
    # `test_the_governed_slack_is_what_decides_whether_the_block_publishes`.
    before = [_rate("Brasil", 100, 1000), _rate("Chile", 40, 4)]
    after = [_rate("Brasil", 150, 1000), _rate("Chile", 300, 4)]
    measured = contributions_of(before, after, "value", "country", sample_floor=_FLOOR)
    exact = abs(measured.residual) / abs(measured.total_deviation)
    # The fixture is only worth anything if the two sides can differ: a zero residual would make
    # every tolerance close and the operators agree.
    assert exact > 0, "the fixture produced no residual, so the boundary cannot be measured"

    on_the_line = contributions_of(
        before, after, "value", "country", sample_floor=_FLOOR, tolerance=exact
    )
    assert on_the_line.verdict is Verdict.RECONCILED, (
        "a residual EXACTLY at the tolerance was refused; the rule says ABOVE it refuses"
    )
    just_past = contributions_of(
        before, after, "value", "country", sample_floor=_FLOOR, tolerance=exact - Decimal("1e-12")
    )
    assert just_past.verdict is Verdict.DID_NOT_RECONCILE


def _block(*parts: tuple[str, int, int]) -> ContributionBlock:
    contributions = tuple(
        Contribution(value=name, before=Decimal(before), after=Decimal(after))
        for name, before, after in parts
    )
    total_before = sum((c.before or Decimal(0) for c in contributions), Decimal(0))
    total_after = sum((c.after or Decimal(0) for c in contributions), Decimal(0))
    return ContributionBlock(
        column="country",
        total_before=total_before,
        total_after=total_after,
        parts=contributions,
        verdict=Verdict.RECONCILED,
        residual=Decimal(0),
    )


def test_a_part_explaining_exactly_the_whole_movement_did_not_have_others_compensate() -> None:
    """`contribution.py` — `share > 1`, in the block's verdict AND per pull.

    His rule 2 (`docs/exemplos-analise-dimensional.md:347`): *Acima de 100% é legítimo (os demais
    compensaram)*. ABOVE 100 %. A part that explains exactly 100 % of the movement had nobody
    move against it — the others were flat — so nothing was compensated.
    """
    exactly = _block(("a", 100, 200), ("b", 100, 100))
    assert not exactly.others_compensated
    (pull_a,) = (p for p in pulls_of(exactly, "k") if p.value == "a")
    assert pull_a.share == 1
    assert not pull_a.others_compensated

    above = _block(("a", 100, 210), ("b", 100, 90))
    assert above.others_compensated
    (pull_above,) = (p for p in pulls_of(above, "k") if p.value == "a")
    assert pull_above.others_compensated


# --- the sign on a movement: `+` only when it rose --------------------------------------
#
# His contract writes `+1,4%` and `+12,4%` for a rise and `▬` with no sign where nothing moved
# (`docs/exemplos-analise-dimensional.md:69,73`). A movement of exactly zero is the one value where
# `> 0` and `>= 0` differ, and it is the FLAT case: no plus sign, ever.


def _line_text(line: Line, **words: str) -> str:
    """The indicator as ONE string — `OD-147` turned its line into a block of rows.

    Every node below asks whether a `+` is or is not written somewhere in what the reader sees,
    which is a question about the whole indicator and not about a row. Joining is what keeps
    the boundary these nodes measure — `> 0` against `>= 0` — the thing being measured, rather
    than a row index that would need editing the next time the shape moves.
    """
    return chr(10).join(_indicator_lines(line, **words))  # pyright: ignore[reportArgumentType]


def _line(**overrides: object) -> Line:
    base: dict[str, object] = {
        "label": "k",
        "value": Decimal(10),
        "previous_value": Decimal(10),
        "variation": Decimal(0),
        "unit": VariationUnit.RELATIVE_PERCENT,
        "footnoted": False,
    }
    base.update(overrides)
    return Line(**base)  # pyright: ignore[reportArgumentType]


def test_a_movement_of_exactly_zero_carries_no_plus_sign() -> None:
    """`summary.py` — `line.variation > 0`, the day-before movement."""
    flat = _line_text(_line(variation=Decimal(0)))
    assert "+0" not in flat, flat
    assert "+" not in flat, flat
    rose = _line_text(_line(variation=Decimal("0.01"), value=Decimal(11)))
    assert "+0,01" in rose, rose


def test_a_brl_movement_of_exactly_zero_carries_no_plus_sign() -> None:
    """`summary.py` — `line.brl_variation > 0`."""
    flat = _line_text(
        _line(
            brl_value=Decimal(50),
            brl_previous=Decimal(50),
            brl_variation=Decimal(0),
            brl_format="brl",
        )
    )
    assert "+0" not in flat, flat
    rose = _line_text(
        _line(
            brl_value=Decimal(51),
            brl_previous=Decimal(50),
            brl_variation=Decimal(2),
            brl_format="brl",
        )
    )
    assert "+2" in rose, rose


def test_a_week_ago_movement_of_exactly_zero_carries_no_plus_sign() -> None:
    """`summary.py` — `line.week_ago_variation > 0`, the second reference of `FR-1306`."""
    flat = _line_text(
        _line(week_ago_value=Decimal(10), week_ago_variation=Decimal(0)),
        reference_label="D-7",
        reference_against="vs",
    )
    assert "D-7" in flat, flat
    assert "+0" not in flat, flat
    rose = _line_text(
        _line(value=Decimal(11), week_ago_value=Decimal(10), week_ago_variation=Decimal(10)),
        reference_label="D-7",
        reference_against="vs",
    )
    assert "+10" in rose and "D-7" in rose, rose


def test_a_movement_of_exactly_zero_is_the_flat_mark_and_the_direction_test_never_sees_it() -> None:
    """`summary.py` — `rose = variation > 0` inside `mark_for`.

    **This inversion is inert BY CONSTRUCTION, and the node says so rather than pretending to
    bite.** `mark_for` returns `UNMOVED` for `variation == 0` one line above, so `> 0` only ever
    sees a non-zero value — a value where `>` and `>=` agree. The boundary the operator could get
    wrong is handled before it. What IS asserted is the rule: zero is the flat mark (`▬` in his
    contract), not a rise and not a fall.
    """
    assert mark_for(Decimal(0), lower_is_better=False) == UNMOVED
    assert mark_for(Decimal(0), lower_is_better=True) == UNMOVED
    assert mark_for(Decimal("0.01"), lower_is_better=False) != UNMOVED
    assert mark_for(Decimal("-0.01"), lower_is_better=False) != UNMOVED


# --- the one boundary NO written rule decides -------------------------------------------


def test_a_movement_exactly_at_its_own_p90_is_a_crossing() -> None:
    """`alert/rule.py` — `abs(latest) < threshold`. **The thirteenth boundary, decided by him.**

    No spec placed the exact case: `008` said only *only on a crossing* (`spec.md:30`), `FR-811`
    derives the `p90` at run time, and `FR-814`'s *"when a KPI passes it"* is about the minimum
    number of weeks. The `p90` is linearly interpolated, so equality is reachable. A first version
    of this node asserted the two sides every reading agreed on and NOTHING at equality — pinning
    the operator of the day would have frozen an off-by-one nobody decided.

    **`OD-125` (2026-09-04) decided it: igualar o p90 DISPARA — reaching the threshold is already
    crossing it.** The sentence now stands in spec `008` beside *only on a crossing*, and `<` is
    the operator the rule asks for: a movement below the threshold is inside the noise, a movement
    at or above it is a finding. Inverting to `<=` swallows the exact case and this goes red.
    """
    history = tuple(Decimal(value) for value in range(1, 21))  # p90 = 18.1, interpolated
    periods = [len(history)] * 3
    threshold = Decimal("18.1")

    below = evaluate(
        "k", "int", history, threshold - Decimal("0.1"), comparable_periods_across_kpis=periods
    )
    exactly = evaluate("k", "int", history, threshold, comparable_periods_across_kpis=periods)
    above = evaluate(
        "k", "int", history, threshold + Decimal("0.1"), comparable_periods_across_kpis=periods
    )

    assert below is None
    assert exactly is not None, "a movement EXACTLY at its p90 did not fire; OD-125 says it does"
    assert exactly.threshold == threshold, "the fixture is not sitting on the line it claims"
    assert above is not None
