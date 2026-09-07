"""The block reaches the reader, and a quiet day says so instead of showing nothing — `T1316`.

`FR-1310`. An empty section is a report that looks broken; his contract closes a quiet day
with a sentence, and the sentence is his.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from daily_reporting.report.breakdown import BreakdownGovernance
from daily_reporting.report.contribution import (
    ContributionGovernance,
    Pull,
    Verdict,
    contributions_of,
    pulls_of,
)
from daily_reporting.report.summary import (
    _contribution_lines,  # pyright: ignore[reportPrivateUsage]
)

REPO = Path(__file__).resolve().parents[4]
GOVERNED = REPO / "report_governance" / "contribution.yaml"


@pytest.fixture(scope="module")
def governance() -> ContributionGovernance:
    return ContributionGovernance.from_document(
        yaml.safe_load(GOVERNED.read_text(encoding="utf-8"))
    )


def _count(value: str, number: int) -> dict[str, object]:
    return {"country": value, "aggregation_class": "COUNT", "value": number}


def _rate(value: str, numerator: int, denominator: int) -> dict[str, object]:
    """A rate, because the only way to make a sum NOT close is the sample floor.

    A part seen on one day only is counted in the conservation and merely not printed — the
    correction of 2026-09-04, made after the engine refused every real block. A part the floor
    drops is in the total and in no line, and that is a genuine gap.
    """
    return {
        "country": value,
        "aggregation_class": "RATIO",
        "numerator": numerator,
        "denominator": denominator,
    }


def _pulls(
    before: list[dict[str, object]],
    after: list[dict[str, object]],
    governance: ContributionGovernance,
) -> tuple[Pull, ...]:
    block = contributions_of(before, after, "value", "country", tolerance=governance.tolerance)
    return pulls_of(block, "New trials", "count")


def test_a_quiet_day_says_so_and_never_shows_an_empty_heading(
    governance: ContributionGovernance,
) -> None:
    """Mutation: emit the heading with no lines under it — red, and the report looks broken."""
    lines = _contribution_lines((), governance)

    assert lines == [governance.quiet_day]
    assert governance.heading not in "\n".join(lines)
    assert governance.heading_emoji not in "\n".join(lines)


def test_the_block_names_who_pulled_and_carries_his_heading(
    governance: ContributionGovernance,
) -> None:
    pulls = _pulls(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 80), _count("Mexico", 40)],
        governance,
    )
    lines = _contribution_lines(pulls, governance)

    assert lines[0] == f"{governance.heading_emoji} {governance.heading}:"
    #: `OD-142`, 2026-09-06: the flat list became GROUPS, one per indicator and axis, each
    #: opened by a blank line and its own heading. With no breakdown governance handed in there
    #: is no axis word to name, so the group heading is the indicator alone — a word nobody
    #: invented rather than a column name the source spells `country`.
    assert lines[1] == ""
    assert lines[2] == "New trials"
    assert len(lines) == 5
    assert lines[3].startswith("Brasil")
    #: `OD-143` (c): the SIGN, not `before -> after`. He asked not to do the subtraction himself
    #: on thirty-seven lines, and the two terms are on the indicator's own rows one block up.
    assert governance.became not in chr(10).join(lines)
    assert lines[3].split()[1].startswith("-"), lines[3]


_AXES = BreakdownGovernance(
    top_n=5,
    axis_labels=(("country", "por pais"), ("game", "por jogo")),
    tail_label="demais",
    tail_noun="valores",
    axis_marker="-",
    value_marker="--",
    axis_plural=(("country", "paises"),),
)


def _pull(kpi: str, column: str, value: str, before: int, after: int) -> Pull:
    total = Decimal(100)
    return Pull(
        value=value,
        kpi_label=kpi,
        column=column,
        before=Decimal(before),
        after=Decimal(after),
        share=(Decimal(after) - Decimal(before)) / total,
        format_type="int",
        others_compensated=False,
    )


def test_the_block_is_four_named_groups_and_not_one_flat_list(
    governance: ContributionGovernance,
) -> None:
    """`OD-142`, 2026-09-06. He said it twice: *"nem da pra ler"*, and *"tem que separar os
    jogos e os paises, pq esta tudo numa coisa so"*.

    The block reached him as **thirty-seven lines**, flat, mixing a country and a game title
    under two different indicators. One list is now one group per `(indicator, axis)`, each
    headed by both words, and **the axis word comes from the governed breakdown file** — the
    same `axis_labels` the breakdown renders from, never retyped.

    The group ORDER is derived twice over: indicators in the order the caller produced them,
    axes in the order his file declares. Nothing here chooses which axis comes first.

    **Mutation**: render one flat list again — red on the group headings. Order the axes by
    name instead of by his file — red on the last assertion.
    """
    pulls = (
        _pull("New trials", "game", "Valorant", 100, 130),
        _pull("New trials", "country", "Brazil", 100, 120),
        _pull("Sales (qty)", "country", "Brazil", 100, 110),
        _pull("Sales (qty)", "game", "Valorant", 100, 105),
    )
    lines = _contribution_lines(pulls, governance, icons=_AXES)

    headings = [text for text in lines if " · " in text]
    assert headings == [
        "New trials · por pais",
        "New trials · por jogo",
        "Sales (qty) · por pais",
        "Sales (qty) · por jogo",
    ], lines

    #: Every group opens with a blank line, so four blocks read as four rather than as one.
    for heading in headings:
        assert lines[lines.index(heading) - 1] == ""


def test_the_parts_are_ranked_by_magnitude_and_not_by_name(
    governance: ContributionGovernance,
) -> None:
    """`OD-142`: `Belarus +2` came out above `Poland +11` because `B` comes before `P`.

    **Sorted by how much it moved.** A list ordered alphabetically puts the largest mover
    wherever its country's spelling lands it, so the reader has to read all thirty-seven to
    find the one that matters. The tie-break is the name, which keeps two runs of one day
    identical rather than deciding anything.

    **Mutation**: sort by name — red, and the fixture is built so the two orders differ.
    """
    pulls = (
        _pull("New trials", "country", "Belarus", 3, 5),
        _pull("New trials", "country", "Poland", 4, 15),
        _pull("New trials", "country", "Argentina", 10, 17),
    )
    lines = _contribution_lines(pulls, governance, icons=_AXES)
    named = [text.split()[0] for text in lines[3:]]

    assert named == ["Poland", "Argentina", "Belarus"], lines
    assert named != sorted(named), "the fixture stopped separating the two orders"


def test_a_deviation_of_one_unit_is_not_worth_a_line(
    governance: ContributionGovernance,
) -> None:
    """`OD-143` (a): fourteen of the thirty-seven lines were a part that went from one to two.

    **A movement of a single unit explains nothing and costs a whole line**, and fourteen of
    them is what made the twenty-three that meant something unreadable.

    **Only where a unit is a whole thing**: the filter reads the source's own `format_type`, so
    one unit of a COUNT is one trial and one unit of a RATE — a whole percentage point, larger
    than anything the daily has shown — is untouched. That is recorded rather than assumed.

    **Mutation**: drop the filter — red on the first assertion. Apply it to every format — red
    on the second, and a real move in points disappears from the alert.
    """
    counted = (
        _pull("New trials", "country", "Denmark", 1, 2),
        _pull("New trials", "country", "Poland", 4, 15),
    )
    lines = _contribution_lines(counted, governance, icons=_AXES)
    assert not any("Denmark" in text for text in lines), lines
    assert any("Poland" in text for text in lines), lines

    rated = (
        Pull(
            value="Denmark",
            kpi_label="Trial conversion (%)",
            column="country",
            before=Decimal(1),
            after=Decimal(2),
            share=Decimal("0.5"),
            format_type="pct",
            others_compensated=False,
        ),
    )
    assert any("Denmark" in text for text in _contribution_lines(rated, governance, icons=_AXES))


def test_a_group_names_the_governed_few_and_counts_what_it_left(
    governance: ContributionGovernance,
) -> None:
    """`OD-142`: the THREE largest and a counted tail, and **the three is governed data**.

    It is his number and it lives in `report_governance/contribution.yaml` for the reason the
    breakdown's cut does: a total written in the package is a total that stops matching what he
    asked for without anybody noticing, and `test_the_loop_enumerates_nothing` sweeps this
    package for exactly that.

    The tail borrows the words the breakdown's tail already uses — his `demais`, and the axis's
    own plural where his contract carries one.

    **Mutation**: cut at a number written here instead of read from his file — the node stays
    green only while the two agree, and the assertion below reads the file.
    """
    pulls = tuple(
        _pull("New trials", "country", name, 10, 10 + move)
        for name, move in (("A", 40), ("B", 30), ("C", 20), ("D", 15), ("E", 12))
    )
    lines = _contribution_lines(pulls, governance, icons=_AXES)
    parts = lines[3:]

    assert governance.top_n == 3, governance.top_n
    assert len(parts) == governance.top_n + 1, parts
    assert [text.split()[0] for text in parts[:-1]] == ["A", "B", "C"]
    assert parts[-1] == f"{_AXES.tail_label} 2 {_AXES.plural_for('country')}: +27"


def test_the_part_carries_the_sign_and_not_the_two_terms(
    governance: ContributionGovernance,
) -> None:
    """`OD-143` (c): he asked not to do the subtraction himself, thirty-seven times.

    The line printed `2 → 13`. The number he wants is the DIFFERENCE, and the two terms are on
    the indicator's own rows one block up — `OD-147` put them there with a word each.

    **Mutation**: print `before → after` again — red on both assertions.
    """
    lines = _contribution_lines(
        (_pull("New trials", "country", "Poland", 2, 13),), governance, icons=_AXES
    )
    assert lines[3].startswith("Poland +11 ("), lines
    assert governance.became not in chr(10).join(lines)


def test_the_alert_carries_his_other_heading_and_not_the_reports(
    governance: ContributionGovernance,
) -> None:
    """He wrote two forms. Mutation: use one heading for both — red.

    The alert's is `contrato-013-exemplos.md` line 22 and the report's is line 59; they are
    different sentences and neither was chosen here.
    """
    pulls = _pulls([_count("Brasil", 100)], [_count("Brasil", 80)], governance)

    for_report = _contribution_lines(pulls, governance)
    for_alert = _contribution_lines(pulls, governance, for_alert=True)

    assert governance.heading in for_report[0]
    assert governance.heading_alert in for_alert[0]
    assert for_report[0] != for_alert[0]
    assert for_report[1:] == for_alert[1:]


def test_only_the_part_that_explains_more_than_the_whole_carries_the_clause(
    governance: ContributionGovernance,
) -> None:
    """**The first render put the clause on every line, and that was false on most of them.**

    It says *the others rose and made up part of it*, which is true beside a part explaining
    two hundred per cent and false beside one explaining a third. Mutation: hang it on the
    block instead of the part — red.
    """
    # THREE parts, and the fixture is the point: two pulled the same way and a third pushed
    # back. Brasil explains a third more than the whole movement; Chile explains a ninth of it.
    # A clause hung on the BLOCK is true of the first and false of the second — and a fixture
    # with only ONE surviving part cannot tell the two implementations apart. The first
    # version of this node could not, and passed green under its own mutation.
    over = _pulls(
        [_count("Brasil", 100), _count("Chile", 50), _count("Mexico", 50)],
        [_count("Brasil", 40), _count("Chile", 45), _count("Mexico", 70)],
        governance,
    )
    together = _pulls(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 80), _count("Mexico", 40)],
        governance,
    )

    assert [pull.value for pull in over] == ["Brasil", "Chile"]
    assert [pull.others_compensated for pull in over] == [True, False]
    assert [pull.others_compensated for pull in together] == [False, False]
    #: `OD-142` put a blank line and a group heading between the block's heading and its first
    #: part, so the parts start at index three.
    assert governance.compensated in _contribution_lines(over, governance)[3]
    assert governance.compensated not in _contribution_lines(over, governance)[4]
    assert governance.compensated not in _contribution_lines(together, governance)[3]


def test_a_part_that_resisted_the_day_is_not_listed_as_having_pulled_it(
    governance: ContributionGovernance,
) -> None:
    """**The first render listed one, and it read as nonsense** — minus one hundred per cent.

    Brasil falls forty while Mexico rises twenty: Mexico did not pull the day down, it held it
    up. The heading says who pulled. Mutation: keep every part — red, and the block contradicts
    its own heading.
    """
    pulls = _pulls(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 60), _count("Mexico", 70)],
        governance,
    )

    assert [pull.value for pull in pulls] == ["Brasil"]
    assert all(pull.share > 0 for pull in pulls)


def test_a_block_that_did_not_reconcile_produces_no_line_at_all(
    governance: ContributionGovernance,
) -> None:
    """`SC-1302` at the render, not only at the verdict: a refusal cannot leak as a partial list."""
    block = contributions_of(
        [_rate("Brasil", 100, 1000), _rate("Chile", 40, 4)],
        [_rate("Brasil", 200, 1000), _rate("Chile", 300, 4)],
        "value",
        "country",
        sample_floor=30,
        tolerance=governance.tolerance,
    )

    assert not block.may_publish
    assert pulls_of(block, "New trials", "count") == ()
    assert _contribution_lines((), governance) == [governance.quiet_day]


def test_the_approximation_mark_appears_only_when_the_figure_was_rounded(
    governance: ContributionGovernance,
) -> None:
    """He carries `~` on a rounded share and not on an exact one, and stated no rounding rule.

    So the mark is DERIVED from whether rounding happened. Mutation: always print it, or never
    — red either way.
    """
    exact = _pulls(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 60), _count("Mexico", 70)],
        governance,
    )
    rounded = _pulls(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 80), _count("Mexico", 40)],
        governance,
    )

    assert governance.approximately not in _contribution_lines(exact, governance)[3]
    assert governance.approximately in _contribution_lines(rounded, governance)[3]


def test_every_word_with_a_letter_in_the_block_came_from_the_governed_file(
    governance: ContributionGovernance,
) -> None:
    """**The property the whole file exists for**, asserted over the rendered lines.

    Mutation: type any word into the renderer — red, because the token it produces belongs to
    no governed value and to no measured row.
    """
    pulls = _pulls(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 60), _count("Mexico", 70)],
        governance,
    )
    allowed = {
        token.casefold()
        for phrase in (*governance.words, "Brasil", "Mexico", "New trials")
        for token in phrase.split()
    }

    for line in (*_contribution_lines(pulls, governance), *_contribution_lines((), governance)):
        for token in line.split():
            stripped = token.strip(":()*,;")
            if any(character.isalpha() for character in stripped):
                assert stripped.casefold() in allowed, f"{stripped!r} in {line!r}"


def test_relevance_filters_the_lines_and_never_the_reconciliation(
    governance: ContributionGovernance,
) -> None:
    """`FR-1310`, and **the ORDER is the property**, not the filtering.

    Chile arrives on the second day alone and breaks the sum. Declaring only Brasil relevant
    must NOT rescue the block: a decomposition that does not add up is refused whatever the
    caller finds interesting.

    Mutation: filter the parts before reconciling — green block, wrong numbers, and the
    refusal that `SC-1302` exists for never happens.
    """
    broken = contributions_of(
        [_rate("Brasil", 100, 1000), _rate("Chile", 40, 4)],
        [_rate("Brasil", 200, 1000), _rate("Chile", 300, 4)],
        "value",
        "country",
        sample_floor=30,
        tolerance=governance.tolerance,
    )

    assert pulls_of(broken, "New trials", "count", relevant={"Brasil"}) == ()


def test_a_part_nobody_called_relevant_reconciles_and_then_stays_out_of_the_message(
    governance: ContributionGovernance,
) -> None:
    """The two answers are different questions: did the sum close, and is this worth a line."""
    block = contributions_of(
        [_count("Brasil", 100), _count("Chile", 50)],
        [_count("Brasil", 80), _count("Chile", 40)],
        "value",
        "country",
        tolerance=governance.tolerance,
    )

    assert block.verdict is Verdict.RECONCILED
    everyone = pulls_of(block, "New trials", "count")
    only_brasil = pulls_of(block, "New trials", "count", relevant={"Brasil"})
    nobody = pulls_of(block, "New trials", "count", relevant=set())

    assert [pull.value for pull in everyone] == ["Brasil", "Chile"]
    assert [pull.value for pull in only_brasil] == ["Brasil"]
    assert nobody == ()
    assert _contribution_lines(nobody, governance) == [governance.quiet_day]


def test_a_part_that_vanished_counts_in_the_sum_and_still_prints_no_line(
    governance: ContributionGovernance,
) -> None:
    """**The half the first version of this pair could not see.**

    A country measured yesterday and absent today explains the whole fall — its share is one,
    positive, and nothing about the sign keeps it out of the block. Only the rule that a line
    needs BOTH sides measured does, and a line reading `50 → 0` would state that it sold
    nothing today when what happened is that nobody measured it.

    The earlier fixture had the vanished part on the OTHER side, where its share came out
    negative and the positive-share filter hid the question. The mutation passed green.

    **Mutation**: drop the `was_measured_twice` filter — red, and the report states a fall to
    zero that the source never said.
    """
    block = contributions_of(
        [_count("Brasil", 100), _count("Chile", 50)],
        [_count("Brasil", 100)],
        "value",
        "country",
        tolerance=governance.tolerance,
    )

    assert block.verdict is Verdict.RECONCILED
    assert [part.value for part in block.parts] == ["Brasil", "Chile"]

    chile = next(part for part in block.parts if part.value == "Chile")
    assert chile.after is None
    assert chile.share_of(block.total_deviation) == 1

    assert pulls_of(block, "New trials", "count") == ()
    assert _contribution_lines((), governance) == [governance.quiet_day]


def test_the_block_and_the_breakdown_write_the_same_value_the_same_way(
    governance: ContributionGovernance,
) -> None:
    """**Measured defect that lived one day: one message, one value, two spellings.**

    `contribution.yaml` refused the flag because the source carries a country NAME and not an
    ISO code, so deriving one would be the hand-written table `S-4` forbids. That was true
    until `OD-119` put the hand-written map in `breakdown.yaml` the next day — his, dated, one
    entry per value. The refusal outlived its reason, and the same report rendered
    `🇧🇷 Brazil 139` in the breakdown and a bare `Brazil` four lines below it in the block.

    **Mutation**: stop handing the map to the block — red. Derive the icon from the name — the
    map is the only source, so there is nothing to derive from, and the node above it fails.
    """
    icons = BreakdownGovernance(
        top_n=5,
        axis_labels=(("country", "por pais"),),
        tail_label="demais",
        tail_noun="valores",
        axis_marker="-",
        value_marker="--",
        icons=(("country", (("Brasil", "\N{BAR CHART}"),)),),
    )
    pulls = _pulls(
        [_count("Brasil", 100), _count("Mexico", 50)],
        [_count("Brasil", 80), _count("Mexico", 40)],
        governance,
    )

    named = _contribution_lines(pulls, governance, icons=icons)
    bare = _contribution_lines(pulls, governance)

    #: **`OD-143` (b), 2026-09-06, and it CHANGES what this node measured.** His words were
    #: about the column he sees: a flag two rows above a bare name reads as a defect in the
    #: message rather than as an absence in a map. So the icons are all-or-nothing per group,
    #: and this fixture -- one value in the map, one not -- is exactly the mixed case he
    #: refused. Nothing is derived and no placeholder stands in; what changed is that the
    #: entries which DO exist are not used in a group where some do not.
    assert named[3].startswith("Brasil"), "a mixed group drew a flag on half its rows"
    assert named[4].startswith("Mexico")
    #: Read off the two ROWS and not off the whole block: the governed heading emoji of this
    #: fixture happens to be the same symbol, and a whole-text search would measure that
    #: instead of the rule.
    assert icons.icon_for("country", "Brasil") not in named[3] + named[4]
    assert bare[3].startswith("Brasil"), "no map handed in means no icon, never a placeholder"

    #: The other direction, so the node is not vacuous: a group where EVERY value is in the map
    #: draws every flag. Without this half a renderer that dropped icons entirely would pass.
    whole = BreakdownGovernance(
        top_n=5,
        axis_labels=(("country", "por pais"),),
        tail_label="demais",
        tail_noun="valores",
        axis_marker="-",
        value_marker="--",
        icons=(
            (
                "country",
                (("Brasil", "📊"), ("Mexico", "📈")),
            ),
        ),
    )
    lettered = _contribution_lines(pulls, governance, icons=whole)
    assert lettered[3].startswith(f"{whole.icon_for('country', 'Brasil')} Brasil")
    assert lettered[4].startswith(f"{whole.icon_for('country', 'Mexico')} Mexico")


#: `OD-153`, 2026-09-06: `_AXES` with his singular beside the plural, for the group's tail.
_AXES_BOTH_NUMBERS = BreakdownGovernance(
    top_n=5,
    axis_labels=(("country", "por pais"), ("game", "por jogo")),
    tail_label="demais",
    tail_noun="valores",
    axis_marker="-",
    value_marker="--",
    axis_plural=(("country", "países"), ("game", "jogos")),
    axis_singular=(("country", "país"), ("game", "jogo")),
)


def test_a_group_tail_of_one_part_is_said_in_the_singular(
    governance: ContributionGovernance,
) -> None:
    """`OD-153` — **the block's counted tail agrees with its count too.**

    The breakdown's tail and this one are two different renderers reading the same governed
    words, and fixing one alone would leave the message saying it both ways four lines apart.
    That is the shape of the defect `OD-119` left for a day, with the flag drawn in one block
    and not in the other, and it is asserted here rather than trusted.

    **Mutation**: always plural — red here and in the breakdown's own node; always singular —
    red on the second half below.
    """
    four = tuple(
        _pull("New trials", "country", name, 10, 10 + move)
        for name, move in (("A", 40), ("B", 30), ("C", 20), ("D", 15))
    )
    one_left = _contribution_lines(four, governance, icons=_AXES_BOTH_NUMBERS)

    assert governance.top_n == 3, governance.top_n
    assert one_left[-1] == f"{_AXES_BOTH_NUMBERS.tail_label} 1 país: +15", one_left

    five = (*four, _pull("New trials", "country", "E", 10, 22))
    two_left = _contribution_lines(five, governance, icons=_AXES_BOTH_NUMBERS)
    assert two_left[-1] == f"{_AXES_BOTH_NUMBERS.tail_label} 2 países: +27", two_left


def test_a_group_tail_on_the_game_axis_uses_his_word_and_not_the_generic_noun(
    governance: ContributionGovernance,
) -> None:
    """The axis `OD-153` gave words to, in the block that had none for it either."""
    four = tuple(
        _pull("New trials", "game", name, 10, 10 + move)
        for name, move in (("A", 40), ("B", 30), ("C", 20), ("D", 15))
    )
    one_left = _contribution_lines(four, governance, icons=_AXES_BOTH_NUMBERS)
    assert one_left[-1] == f"{_AXES_BOTH_NUMBERS.tail_label} 1 jogo: +15", one_left

    five = (*four, _pull("New trials", "game", "E", 10, 22))
    two_left = _contribution_lines(five, governance, icons=_AXES_BOTH_NUMBERS)
    assert two_left[-1] == f"{_AXES_BOTH_NUMBERS.tail_label} 2 jogos: +27", two_left


def test_the_clause_about_the_others_stays_plural_because_it_counts_nothing(
    governance: ContributionGovernance,
) -> None:
    """**`plural_for` keeps a call site, and that is measured rather than assumed.**

    `OD-153` is about AGREEMENT WITH A COUNT, and this clause has no count in it: it says the
    other parts moved against the one being described. There is no number for a word to agree
    with, so the plural is the only right answer and the counted method is the wrong tool.

    **Mutation**: route this clause through the counted method with a hard-coded 1 — red here,
    and his sentence would read as though exactly one other part had moved.
    """
    compensating = Pull(
        value="Poland",
        kpi_label="New trials",
        column="country",
        before=Decimal(2),
        after=Decimal(13),
        share=Decimal("1.09"),
        format_type="int",
        others_compensated=True,
    )
    lines = _contribution_lines((compensating,), governance, icons=_AXES_BOTH_NUMBERS)
    #: The clause reads the BLOCK's own governed file, not the breakdown's — two files, and the
    #: plural of this one is what stands in his sentence.
    clause = f"{governance.others} {governance.plural_for('country')} {governance.compensated}"

    assert any(clause in text for text in lines), lines
    assert governance.plural_for("country") != governance.singular_for("country")
