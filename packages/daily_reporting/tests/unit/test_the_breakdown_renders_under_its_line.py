"""The breakdown appears under the KPI it belongs to — `T1308`, `FR-1303`.

**This is where the message he reads actually changes**, and it is the first task of `F1`
whose visible delivery is not "nothing yet". Everything before it was arranging data so this
line could be written honestly.

## What this file guards, and why each is separate

* the sub-line sits UNDER its own KPI line, not at the end of the section — a breakdown that
  floats away from its number is a list of names;
* a line with NO breakdowns renders exactly as it did before, byte for byte. That is what
  makes `F1` safe to ship before every KPI has an axis, and it is asserted rather than
  assumed;
* the sub-line contributes **no word of its own**. The axis label and the tail word come from
  the governed file, the values come from the source. What this module adds is punctuation,
  and the node below reads the rendered line for exactly that;
* the tail carries BOTH numbers, because `SC-1304` is about honesty and not brevity.

## `Line.breakdowns` is deliberately not `Line`

`test_the_report_carries_every_kpi.py` compares the SET of labels in the report against the
KPIs that exist. Sub-lines shaped as `Line` would join that set and break a guard that is
right to exist. The parallel type keeps two questions apart: which KPIs there are, and what
each one breaks down into.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from itertools import pairwise

import pytest

from daily_reporting.numbers.variation import VariationUnit
from daily_reporting.report.breakdown import Breakdown, BreakdownGovernance
from daily_reporting.report.summary import Line, Summary, render

#: The shape `OD-119` chose, held here so every node reads the same governance the report does.
GOVERNANCE = BreakdownGovernance(
    top_n=5,
    axis_labels=(("country", "por pais"), ("game", "por jogo")),
    tail_label="demais",
    tail_noun="valores",
    axis_marker="-",
    value_marker="--",
    icons=(("country", (("Brasil", "🇧🇷"),)),),
)

pytestmark = pytest.mark.unit

_BY_COUNTRY = Breakdown(
    column="country",
    label="por pais",
    lines=(("Brasil", Decimal(412)), ("Mexico", Decimal(133))),
    tail_count=7,
    tail_total=Decimal(49),
)
_BY_GAME = Breakdown(
    column="game",
    label="por jogo",
    lines=(("Valorant", Decimal(289)),),
    tail_count=0,
    tail_total=Decimal(0),
)


def _line(label: str, *breakdowns: Breakdown) -> Line:
    return Line(
        label=label,
        value=Decimal(763),
        previous_value=Decimal(691),
        variation=Decimal("10.4"),
        unit=VariationUnit.RELATIVE_PERCENT,
        footnoted=False,
        format_type="int",
        breakdowns=breakdowns,
    )


def _rendered(*lines: Line) -> list[str]:
    summary = Summary(day=date(2026, 9, 3), sections=(("Acquisition", lines),), periods=None)
    return render(summary, breakdowns_governance=GOVERNANCE).splitlines()


def test_the_breakdown_sits_directly_under_its_own_line() -> None:
    """A breakdown that floats away from its number is a list of names.

    **`OD-147` put four rows between the label and the block**, and the property is unchanged:
    the axis opens directly after the indicator's LAST row, not at the end of the section. The
    offset is computed from the block's own end rather than written down, so this node measures
    adjacency and not a row count somebody would have to edit again.
    """
    lines = _rendered(_line("New trials", _BY_COUNTRY), _line("Sales"))
    index = next(i for i, text in enumerate(lines) if text.endswith("New trials"))
    #: `OD-147`: label, then the closed day, the day before and the movement.
    last = next(i for i in range(index + 1, len(lines)) if lines[i] == "")
    assert last - index == 4, lines[index:last]
    # `OD-119`: a blank line opens the block, then the axis, then one line per value.
    assert lines[last] == ""
    assert lines[last + 1] == "- por pais"
    # Blank, axis, two values, tail, then the fence `S-46` added below the block.
    assert lines[last + 5] == ""
    assert lines[last + 6].startswith("Sales")


def test_the_axes_render_in_the_order_they_were_given() -> None:
    lines = _rendered(_line("New trials", _BY_COUNTRY, _BY_GAME))
    positions = [
        next(i for i, text in enumerate(lines) if label in text)
        for label in ("por pais", "por jogo")
    ]
    assert positions == sorted(positions)


def test_a_line_with_no_breakdown_renders_exactly_as_before() -> None:
    """**The property that makes F1 safe to ship**, driven rather than assumed."""
    without = _rendered(_line("New trials"))
    assert not any("por pais" in text or "demais" in text for text in without)
    # Blank line, axis, two values, tail — five lines, and NO blank line trailing the block.
    assert len(without) == len(_rendered(_line("New trials", _BY_COUNTRY))) - 5
    assert without[-1] != ""


def test_the_tail_names_how_many_and_how_much() -> None:
    """One without the other is a half-truth that reads like a whole one."""
    text = next(t for t in _rendered(_line("New trials", _BY_COUNTRY)) if "demais" in t)
    assert text == "-- demais 7 valores: 49"


_SPLITTING = BreakdownGovernance(
    top_n=5,
    axis_labels=(("country", "por pais"), ("game", "por jogo")),
    tail_label="demais",
    tail_noun="valores",
    axis_marker="-",
    value_marker="--",
    sampled_qualifier="com amostra",
    withheld_label="sem amostra para afirmar",
    withheld_value="nao classificados",
    axis_plural=(("country", "paises"),),
)


def _rate_line(breakdown: Breakdown) -> Line:
    """An indicator whose numbers are a RATE, so the tail wears the per-cent sign.

    The floor only exists where a denominator does, so a split tail is a rate's tail; a fixture
    built on a count would render the same words over numbers that cannot have been withheld.
    """
    return Line(
        label="Conv",
        value=Decimal("36.28"),
        previous_value=Decimal("41.44"),
        variation=Decimal("-5.16"),
        unit=VariationUnit.PERCENTAGE_POINTS,
        footnoted=False,
        format_type="pct",
        breakdowns=(breakdown,),
    )


def test_a_rate_tail_splits_its_two_populations_and_asserts_a_rate_for_only_one() -> None:
    """`OD-144`, 2026-09-06 — **one line was answering two questions**.

    The tail summed the parts that did not fit the cut AND the parts the sample floor withheld.
    The number was arithmetically honest, because a tail is aggregated rather than summed, and
    it was unreadable: on the real message a partition at `0,00 %` ranked visibly above a tail
    reading `4,47 %`, with nothing on screen to say the tail held partitions whose rate is
    deliberately not asserted.

    Two lines now: the cut parts with their count, their aggregate and a qualifier saying they
    HAVE a sample; the withheld with their count and his phrase where a rate would be.

    **The withheld stay in the reconciliation** — he refused dropping them — and the second
    line is what carries them.

    **Mutation**: merge the two back into one line — red on the second assertion, and the
    number on the first changes because it would have to absorb a population it does not
    describe. Drop the withheld line — red, and the count vanishes from the message.
    """
    split = Breakdown(
        column="country",
        label="por pais",
        lines=(("Kuwait", Decimal("9.09")),),
        tail_count=31,
        tail_total=Decimal("1.74"),
        withheld_count=43,
    )
    lines = render(
        Summary(day=date(2026, 9, 3), sections=(("Acquisition", (_rate_line(split),)),)),
        breakdowns_governance=_SPLITTING,
    ).splitlines()

    assert "-- demais 31 paises com amostra: 1,74 %" in lines, lines
    assert "-- 43 paises sem amostra para afirmar: nao classificados" in lines, lines
    #: The two are adjacent and in that order: the count that HAS a number first.
    assert lines.index("-- 43 paises sem amostra para afirmar: nao classificados") == (
        lines.index("-- demais 31 paises com amostra: 1,74 %") + 1
    )


def test_a_tail_with_nothing_withheld_keeps_the_one_line_it_always_had() -> None:
    """**A count has no floor, so it has one population** — `OD-144` scoped to a rate.

    A qualifier distinguishing a tail from nothing is noise, and this is the half that keeps
    `OD-144` from changing every breakdown in the message.

    **Mutation**: qualify every tail — red here, and `New trials` grows a word about a
    distinction it does not have.
    """
    lines = render(
        Summary(
            day=date(2026, 9, 3), sections=(("Acquisition", (_line("New trials", _BY_COUNTRY),)),)
        ),
        breakdowns_governance=_SPLITTING,
    ).splitlines()

    assert "-- demais 7 valores: 49" in lines, lines
    assert not any(_SPLITTING.sampled_qualifier in text for text in lines)
    assert not any(_SPLITTING.withheld_label in text for text in lines)


def test_the_split_needs_his_three_words_and_falls_back_to_one_line_without_them() -> None:
    """A governed file stating none of the three renders the tail exactly as it did before.

    **The absence is declared, not defaulted** — the `S-41` rule. Half the vocabulary would
    print a qualifier with nothing to qualify against, or a second population with no word
    saying what it is, and either is worse than the one line this replaces.

    **Mutation**: state one of the three and render — the fallback must still hold, because
    `splits_the_tail` is all-or-nothing.
    """
    split = Breakdown(
        column="country",
        label="por pais",
        lines=(("Kuwait", Decimal("9.09")),),
        tail_count=31,
        tail_total=Decimal("1.74"),
        withheld_count=43,
    )
    silent = render(
        Summary(day=date(2026, 9, 3), sections=(("Acquisition", (_rate_line(split),)),)),
        breakdowns_governance=GOVERNANCE,
    ).splitlines()

    assert "-- demais 31 valores: 1,74 %" in silent, silent
    assert not any("43" in text for text in silent), silent

    half = BreakdownGovernance(
        top_n=5,
        axis_labels=(("country", "por pais"),),
        tail_label="demais",
        tail_noun="valores",
        axis_marker="-",
        value_marker="--",
        sampled_qualifier="com amostra",
    )
    assert not half.splits_the_tail


def test_a_breakdown_with_nothing_cut_prints_no_tail() -> None:
    """A tail that is always there teaches a reader to skip tails."""
    lines = _rendered(_line("New trials", _BY_GAME))
    assert not any("demais" in text for text in lines)


def test_the_sub_line_contributes_no_word_of_its_own() -> None:
    """Every word came from the governed file or from the source. This module adds symbols.

    Read off the RENDERED line rather than off the source: a module can hold a word it never
    prints, and what a person reads is what matters.
    """
    lines = _rendered(_line("New trials", _BY_COUNTRY))
    block = lines[lines.index("- por pais") : lines.index("- por pais") + 4]
    supplied = {"por", "pais", "demais", "valores", "Brasil", "Mexico"}
    for text in block:
        for word in re.findall(r"[^\W\d_]+", text, re.UNICODE):
            assert word in supplied, f"{word!r} is a word nobody supplied"


def test_the_hierarchy_is_a_count_of_his_markers_and_not_an_indent() -> None:
    """`OD-119`, and it replaces the node that asserted three spaces.

    That node said a dash "would be a character nobody decided". True until he decided it: he
    read the inline form on a phone on 2026-09-04 and chose one marker for an axis and two for
    a value. Both come from the governed file; the count is what carries the level.

    **Mutation**: swap the two markers, or read them from the package instead of the file — red.
    """
    lines = _rendered(_line("New trials", _BY_COUNTRY))

    assert lines[lines.index("- por pais")] == f"{GOVERNANCE.axis_marker} por pais"
    for text in lines[lines.index("- por pais") + 1 : lines.index("- por pais") + 4]:
        assert text.startswith(f"{GOVERNANCE.value_marker} ")
    assert not any(text.startswith("   ") for text in lines)


def test_a_value_the_file_names_carries_its_icon_and_one_it_does_not_carries_none() -> None:
    """`OD-119`, and the ABSENCE is the half that matters.

    A value the governed file does not carry renders with no symbol at all. Deriving a flag
    from a country's spelling would be this package inventing a symbol for a value that came
    from the source — the `S-44` defect wearing a different hat — and it would put a wrong flag
    beside a name the day the source spells one differently.

    **Mutation**: fall back to a placeholder, or derive from the name — red on the second line.
    """
    lines = _rendered(_line("New trials", _BY_COUNTRY))
    named = GOVERNANCE.icon_for("country", "Brasil")

    assert f"-- {named} Brasil 412" in lines
    assert "-- Mexico 133" in lines
    assert not any("Mexico" in text and named in text for text in lines)


def test_the_group_of_blocks_is_fenced_by_blank_lines_on_both_sides() -> None:
    """`OD-119` and `S-46`, and the second corrected the first.

    The rule was *before each block and none after the last*, so that an indicator would not
    hand a hole to the one below it. He read the result: `demais 68 valores: 218` sat directly
    against the next indicator's line with nothing between them. The fix is a fence — one blank
    line before the first block and one after the last — and an indicator with no breakdown is
    untouched, which is what keeps a KPI without an axis rendering as it always did.

    **Mutation**: drop either side of the fence — red. Two blank lines anywhere — red.
    """
    lines = _rendered(_line("New trials", _BY_COUNTRY, _BY_GAME), _line("Sales"))

    for axis in ("- por pais", "- por jogo"):
        assert lines[lines.index(axis) - 1] == ""

    sales = next(i for i, text in enumerate(lines) if text.startswith("Sales"))
    assert lines[sales - 1] == "", "the tail of the last block touches the next indicator"
    assert lines[sales - 2] != ""

    # No junction in the message carries two blanks: a fence and a separator would double up.
    assert not any(first == "" and second == "" for first, second in pairwise(lines))


def test_an_indicator_with_no_breakdown_is_fenced_by_nothing() -> None:
    """The fence belongs to the BLOCKS, not to the indicator — no blocks, no fence.

    **What changed with `OD-147` is what a fence separates.** An indicator is now four rows of
    its own, so the single blank between two of them is the indicator separator and not a
    breakdown's fence: exactly ONE blank, never the two that `S-46` measured as a hole.
    """
    lines = _rendered(_line("New trials"), _line("Sales"))

    trials = next(i for i, text in enumerate(lines) if text.endswith("New trials"))
    sales = next(i for i, text in enumerate(lines) if text.endswith("Sales"))
    assert sales - trials == 5, lines[trials:sales]
    assert lines[sales - 1] == ""
    assert lines[sales - 2] != ""


def test_the_breakdowns_are_not_lines_and_do_not_enter_the_label_set() -> None:
    """The guard comparing KPI labels is right, and this must not break it."""
    lines = _rendered(_line("New trials", _BY_COUNTRY, _BY_GAME))
    labelled = [text for text in lines if text.startswith("New trials")]
    assert len(labelled) == 1
    assert not isinstance(_BY_COUNTRY, Line)


# --- the SECOND reference — `T1312`, `FR-1306`, `SC-1305` --------------------------------
#
# His contract asks every indicator for two references: the day before yesterday and the same
# weekday a week back. The first has been there since `OD-31`; this is the second.
#
# Seven days is not a preference — it is the SAME WEEKDAY. A daily series is noisy and a
# Saturday does not compare with a Tuesday, which is the reasoning `OD-14-E` used to pick
# weeks before `OD-31` made the first reference daily. The report now carries both the
# sensitive comparison and the stable one.


def _line_with_week(week_value: Decimal | None, week_variation: Decimal | None) -> Line:
    return Line(
        label="New trials",
        value=Decimal(571),
        previous_value=Decimal(796),
        variation=Decimal("-28.27"),
        unit=VariationUnit.RELATIVE_PERCENT,
        footnoted=False,
        format_type="int",
        week_ago_value=week_value,
        week_ago_variation=week_variation,
    )


def _rendered_with_reference(line: Line, was: str = "") -> str:
    """The indicator's rows as ONE string — `OD-147` made it a block instead of a line.

    Joined rather than picked, because the questions these nodes ask are about the block: is
    the second reference there, does it carry its word, does the first reference still come
    first. A node picking one row would have to know which row, which is the thing `OD-147`
    changed and could change again.
    """
    summary = Summary(day=date(2026, 9, 3), sections=(("Acquisition", (line,)),), periods=None)
    text = render(summary, reference_label="D-7", reference_against="vs", reference_was=was)
    rows = text.splitlines()
    start = next(i for i, t in enumerate(rows) if t.endswith("New trials"))
    return chr(10).join(rows[start:])


def test_the_second_reference_carries_its_variation_its_word_and_its_value() -> None:
    """All three, because a variation whose other term is invisible cannot be checked."""
    text = _rendered_with_reference(_line_with_week(Decimal(525), Decimal("8.76")))
    assert "+8,76" in text
    assert "vs D-7" in text
    assert "525" in text


def test_the_second_reference_is_absent_when_the_day_was_not_measured() -> None:
    """**A reference against a day nobody measured is worse than one reference.**

    Driven in both directions: with the value the word appears, without it nothing does — so
    a change that printed the word over a missing number would fail here.
    """
    assert "D-7" not in _rendered_with_reference(_line_with_week(None, None))
    assert "D-7" in _rendered_with_reference(_line_with_week(Decimal(525), Decimal("8.76")))


def test_the_second_reference_needs_both_of_its_own_numbers() -> None:
    """Half a reference is not half as useful; it is a number nobody can place."""
    assert "D-7" not in _rendered_with_reference(_line_with_week(Decimal(525), None))
    assert "D-7" not in _rendered_with_reference(_line_with_week(None, Decimal("8.76")))


def test_the_words_of_the_reference_come_from_the_caller() -> None:
    """`D-7` has a letter, so it must be governed data — the `S-44` lesson applied ahead.

    With no words supplied the reference does not render at all, rather than falling back to
    something this module wrote: a word the package chose is a word nobody decided.
    """
    line = _line_with_week(Decimal(525), Decimal("8.76"))
    summary = Summary(day=date(2026, 9, 3), sections=(("Acquisition", (line,)),), periods=None)
    bare = next(t for t in render(summary).splitlines() if "New trials" in t)
    assert "D-7" not in bare
    assert "vs" not in bare


def test_the_first_reference_is_untouched_by_the_second() -> None:
    """The line that existed before F2 still reads the same up to the new clause."""
    text = _rendered_with_reference(_line_with_week(Decimal(525), Decimal("8.76")))
    assert text.index("571") < text.index("796") < text.index("+8,76")


def test_the_reference_value_wears_his_word_when_the_file_states_one() -> None:
    """`OD-147`, 2026-09-06: the bracketed number stopped being a bare figure.

    It closed the line as `(654)` — a number in brackets after three others, with nothing
    saying what tense it was in. The word arrives from `report_governance/references.yaml` for
    the reason the two words beside it do, and its ABSENCE leaves the bare parentheses the line
    always had rather than a word this package chose.

    **Mutation**: write the word in the renderer instead of reading it — red in
    `test_the_words_are_written_in_no_python_file_of_this_package`. Print it when the file
    states none — red on the second half here.
    """
    line = _line_with_week(Decimal(525), Decimal("8.76"))
    stated = _rendered_with_reference(line, was="era")
    silent = _rendered_with_reference(line)

    assert "(era 525)" in stated
    assert "(525)" in silent
    assert "era" not in silent


# --- `OD-153`, 2026-09-06: the tail AGREES WITH ITS COUNT ---------------------------------
#
# He gave three words the governance was missing. Until he did, the renderer refused to invent
# them and the refusal was RIGHT -- `D-28` forbids authoring his vocabulary, so the game axis
# fell back to the governed generic noun rather than to a plural somebody guessed. What the
# words unlock is a second thing: a tail of ONE partition can stop wearing the word for many.

#: The same shape as `_SPLITTING`, with his `OD-153` words in both numbers for both axes.
#: **Spelled as he wrote them, accents included**, because what these nodes measure is the
#: agreement a reader sees on the line rather than the loading of a file.
_BOTH_NUMBERS = BreakdownGovernance(
    top_n=5,
    axis_labels=(("country", "por pais"), ("game", "por jogo")),
    tail_label="demais",
    tail_noun="valores",
    axis_marker="-",
    value_marker="--",
    sampled_qualifier="com amostra",
    withheld_label="sem amostra para afirmar",
    withheld_value="nao classificados",
    axis_plural=(("country", "países"), ("game", "jogos")),
    axis_singular=(("country", "país"), ("game", "jogo")),
)


def _split_lines(breakdown: Breakdown, governance: BreakdownGovernance) -> list[str]:
    """A rate's block rendered under ``governance``. A rate is where the floor withholds."""
    return render(
        Summary(day=date(2026, 9, 3), sections=(("Acquisition", (_rate_line(breakdown),)),)),
        breakdowns_governance=governance,
    ).splitlines()


def test_a_tail_of_one_partition_is_said_in_the_singular() -> None:
    """`OD-153` — **the agreement defect that was real, measured on his own message.**

    The 08:00 report carried a plural over a count of one, on both halves of the split tail. It
    was not an invention and it was not a guess: it was the ONLY word the governed file carried
    for the axis, because no singular had ever been declared. He declared one, so the line can
    now say what it counts.

    Both halves of the split are asserted, and that is deliberate: the withheld line carries its
    own count and would have kept the plural on its own the day the first line was fixed alone.

    **Mutation**: always plural regardless of count — red here, green everywhere else in this
    file. Always singular — red on the node below.
    """
    one = Breakdown(
        column="country",
        label="por pais",
        lines=(("Kuwait", Decimal("9.09")),),
        tail_count=1,
        tail_total=Decimal("1.74"),
        withheld_count=1,
    )
    lines = _split_lines(one, _BOTH_NUMBERS)

    assert "-- demais 1 país com amostra: 1,74 %" in lines, lines
    assert "-- 1 país sem amostra para afirmar: nao classificados" in lines, lines
    assert not any("países" in text for text in lines), lines


def test_a_tail_of_many_keeps_the_plural_on_the_axis_he_named_it_for() -> None:
    """The other half of the count, on the axis whose plural was governed all along.

    **Mutation**: always singular — red here, and every tail in the message counts many
    partitions with the word for one.
    """
    many = Breakdown(
        column="country",
        label="por pais",
        lines=(("Kuwait", Decimal("9.09")),),
        tail_count=31,
        tail_total=Decimal("1.74"),
        withheld_count=43,
    )
    lines = _split_lines(many, _BOTH_NUMBERS)

    assert "-- demais 31 países com amostra: 1,74 %" in lines, lines
    assert "-- 43 países sem amostra para afirmar: nao classificados" in lines, lines


def test_the_game_axis_names_his_own_word_instead_of_the_generic_noun() -> None:
    """`OD-153` gave the plural the game axis never had.

    **The line it replaces was not a defect.** The generic noun was the governed fallback doing
    its job while no word of his existed for the axis: the alternative was this package
    authoring one, which `D-28` forbids and which no node here would have caught. What changed
    is the vocabulary, not the rule.

    **Mutation**: drop `game` from the plural map and the line falls back to the generic noun
    again — which is still correct behaviour, and is what the fallback node below asserts.
    """
    game = Breakdown(
        column="game",
        label="por jogo",
        lines=(("Valorant", Decimal("9.09")),),
        tail_count=2,
        tail_total=Decimal("1.74"),
        withheld_count=3,
    )
    lines = _split_lines(game, _BOTH_NUMBERS)

    assert "-- demais 2 jogos com amostra: 1,74 %" in lines, lines
    assert "-- 3 jogos sem amostra para afirmar: nao classificados" in lines, lines
    assert not any(_BOTH_NUMBERS.tail_noun in text for text in lines), lines


def test_the_game_axis_of_one_is_said_in_his_singular_too() -> None:
    """Both of his new words on the same axis, so neither can pass by the other's node."""
    game = Breakdown(
        column="game",
        label="por jogo",
        lines=(("Valorant", Decimal("9.09")),),
        tail_count=1,
        tail_total=Decimal("1.74"),
        withheld_count=1,
    )
    lines = _split_lines(game, _BOTH_NUMBERS)

    assert "-- demais 1 jogo com amostra: 1,74 %" in lines, lines
    assert "-- 1 jogo sem amostra para afirmar: nao classificados" in lines, lines
    assert not any("jogos" in text for text in lines), lines


def test_an_axis_he_named_no_word_for_still_falls_back_to_the_governed_noun() -> None:
    """**The fallback discipline is untouched** — the property `OD-153` must not cost.

    An axis absent from both maps falls back to `tail_noun`, which is governed too, for EVERY
    count. His vocabulary carries no singular for that generic noun — measured, not assumed —
    so the fallback stands for one and for many alike. That is an absence stated rather than a
    word chosen here, and it is the same reason the game axis fell back until yesterday.

    **Mutation**: derive a singular from the plural by trimming a letter — red, and the package
    would be authoring his vocabulary one character at a time.
    """
    for count in (1, 4):
        unnamed = Breakdown(
            column="platform",
            label="por pais",
            lines=(("Kuwait", Decimal("9.09")),),
            tail_count=count,
            tail_total=Decimal("1.74"),
            withheld_count=count,
        )
        lines = _split_lines(unnamed, _BOTH_NUMBERS)
        assert f"-- demais {count} valores com amostra: 1,74 %" in lines, lines
        assert f"-- {count} valores sem amostra para afirmar: nao classificados" in lines, lines


def test_a_singular_declared_without_a_plural_is_still_used_where_the_count_is_one() -> None:
    """The two maps are read INDEPENDENTLY, so a half-declared axis loses only the half missing.

    The loader refuses a FILE shaped this way — an axis named in one number and not the other is
    refused rather than half-rendered — so the only way here is by constructing the object, which
    is what this node does. It is the property that keeps `noun_for` from asking the plural map
    for permission to consult the singular one.
    """
    half = BreakdownGovernance(
        top_n=5,
        axis_labels=(("country", "por pais"),),
        tail_label="demais",
        tail_noun="valores",
        axis_singular=(("country", "país"),),
    )

    assert half.noun_for("country", 1) == "país"
    assert half.noun_for("country", 2) == half.tail_noun
    assert half.noun_for("game", 1) == half.tail_noun


def test_zero_and_the_negative_are_not_one_and_so_are_not_singular() -> None:
    """*Exactly one* is the condition, and the boundary is asserted rather than described."""
    assert _BOTH_NUMBERS.noun_for("country", 1) == "país"
    for count in (0, 2, 31):
        assert _BOTH_NUMBERS.noun_for("country", count) == "países", count
