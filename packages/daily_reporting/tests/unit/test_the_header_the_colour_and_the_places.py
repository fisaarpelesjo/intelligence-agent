"""The header's order, the colour's provenance, and the decimals — `OD-33`, `OD-34`, `OD-35`.

Three things he found reading the report on 2026-08-30, and each one gets a node rather than
only a repair: a fix nobody holds up is a fix that comes undone.

## The one that matters most, and it is the third time in this feature

**The header and the line disagreed on the order of the two days.** The header read
`2026-08-28 · 2026-08-29` — older first — over a line reading `644,00 (591,00)` — newer
first. Two opposite orders in one message, and **naked dates carried nothing to undo it**:
a reader mapping the first date onto the first column read the two numbers swapped, so a
rise looked like a fall.

It is the same class as the two before it. On 2026-08-28 the header said *ontem* over a
week's total. `S-8` had a header promising a provenance the entries did not have. **Every
time, the label and the number drifted apart while each was individually correct.**

So the node below does not check a layout. It derives BOTH orders — the dates the header
carries and the values the line carries — and asserts they agree.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from daily_reporting.numbers.variation import as_percent
from daily_reporting.report import template
from daily_reporting.report.summary import (  # pyright: ignore[reportPrivateUsage] -- the node measures the private helpers directly
    Reading,
    _number,  # pyright: ignore[reportPrivateUsage]
    _places_for,  # pyright: ignore[reportPrivateUsage]
    mark_for,
    render,
    summarise,
)
from daily_reporting.view.shape import ViewRow

pytestmark = pytest.mark.unit

A_CLOSED_DAY = date(2026, 8, 29)
THE_DAY_BEFORE = date(2026, 8, 28)
AN_INSTANT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

ROWS: tuple[ViewRow, ...] = ({"section_name": "Acquisition", "kpi_name": "k"},)
_DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
#: The two words that open the closed day's row and the day before's — `OD-147`. Read from the
#: template so a node never spells one of his words itself.
_DAY_WORDS = (template.CLOSED_DAY_WORD, template.PREVIOUS_DAY_WORD)
_NUMBER = re.compile(r"-?[\d.]+(?:,\d+)?")


def _report(
    *,
    value: Decimal | None = Decimal("644"),
    previous: Decimal | None = Decimal("591"),
    format_type: str = "int",
    lower_is_better: bool | None = False,
    periods: tuple[tuple[date, date], tuple[date, date]] | None = (
        (A_CLOSED_DAY, A_CLOSED_DAY),
        (THE_DAY_BEFORE, THE_DAY_BEFORE),
    ),
    crossings: dict[str, tuple[Decimal, int]] | None = None,
    brl: tuple[Decimal, Decimal] | None = None,
) -> str:
    readings = {
        "k": Reading(
            format_type=format_type,
            value=value,
            previous_period=previous,
            current_period=value,
            series_is_short=False,
            lower_is_better=lower_is_better,
            brl_value=brl[0] if brl else None,
            brl_previous=brl[1] if brl else None,
            brl_format="brl" if brl else "",
        )
    }
    return render(
        summarise(
            ROWS,
            readings,
            day=A_CLOSED_DAY,
            instant=AN_INSTANT,
            periods=periods,
            crossings=crossings,
        )
    )


def header_words(text: str) -> str:
    """The column-label row: the two words, over the columns they name — `OD-41`."""
    return text.splitlines()[0]


def header_dates(text: str) -> list[str]:
    """The dates the header carries, in the order it carries them.

    **One running line since `OD-44`**: the columns are gone, so the words and their dates
    share the top line, in the same order the KPI line shows the two numbers.
    """
    return _DATE.findall(text.splitlines()[0])


def _kpi_line(text: str) -> str:
    """The KPI's own BLOCK, as one string — `OD-147` turned the line into four rows.

    **The mark still opens it since `OD-36`**, so the label is not first; what changed is that
    the numbers moved onto rows of their own, each opening with the word that names it. Every
    node below asks a question about the indicator rather than about a row, so the block is
    joined and searched instead of a row being picked by index — an index would have to be
    edited again the next time the shape moves, which is how a node stops guarding.
    """
    rows = text.splitlines()
    start = next(i for i, row in enumerate(rows) if row.endswith("k"))
    end = next((i for i in range(start + 1, len(rows)) if rows[i] == ""), len(rows))
    return chr(10).join(rows[start:end])


def line_numbers(text: str) -> list[str]:
    """The two day figures the KPI block carries, in the order it carries them.

    `OD-147`: the closed day's row comes first and the day before's second, each named. The
    ORDER is what the node above compares against the header's, and it is read off the rendered
    rows rather than assumed — which is the whole point of the pair.
    """
    rows = _kpi_line(text).splitlines()
    named = [row for row in rows if row.split(":", 1)[0] in _DAY_WORDS]
    return [_NUMBER.findall(row.split(": ", 1)[1])[0] for row in named]


def test_the_header_and_the_line_agree_on_which_day_comes_first() -> None:
    """`OD-33-C`. **Both orders are DERIVED and compared; neither is written here.**"""
    text = _report()
    dates = header_dates(text)
    numbers = line_numbers(text)
    assert len(dates) == 2, dates
    assert len(numbers) == 2, numbers

    #: The header's first date is the newer one, and the line's first number is that day's.
    assert dates[0] == "29/08/2026", dates
    assert dates[1] == "28/08/2026", dates
    assert numbers[0] == "644", numbers
    assert numbers[1] == "591", numbers


def test_swapping_either_side_makes_the_two_orders_disagree() -> None:
    """**Proof it bites.** Feed the report the periods the other way round.

    This is the exact shape that shipped: the header naming the older day first over a line
    naming the newer number first. The node above must see it.
    """
    swapped = _report(periods=((THE_DAY_BEFORE, THE_DAY_BEFORE), (A_CLOSED_DAY, A_CLOSED_DAY)))
    dates = header_dates(swapped)
    numbers = line_numbers(swapped)
    #: The line is unchanged -- 644 is still the closed day's value -- and the header now
    #: leads with the older date. The two orders disagree, which is the defect.
    assert dates[0] == "28/08/2026", dates
    assert numbers[0] == "644", numbers
    assert dates[0] != "29/08/2026", "the mutation did not actually swap the header"


def test_both_words_are_in_the_header_so_the_dates_are_not_naked() -> None:
    """`OD-33-C`: bare dates carried nothing to undo an inversion. The words do."""
    text = _report()
    head = header_words(text)
    assert template.CLOSED_DAY_WORD in head, head
    assert template.PREVIOUS_DAY_WORD in head, head

    #: **`OD-41` and `OD-147` COLLIDE here, and the collision is recorded rather than
    #: resolved by taste.**
    #:
    #: `OD-41` was *"ficou ontem e anteontem repetido"*, said when the two words appeared TWICE
    #: IN THE HEADER -- once as a column label and once beside the dates -- which is a header
    #: saying one thing twice. `OD-147` (2026-09-06) is later and is a shape he chose over his
    #: own numbers, and it opens the closed day's row and the day before's row of EVERY
    #: indicator with those same two words. Under the old reading of `OD-41` that is a
    #: repetition; under its reason it is not, because each occurrence names a different number.
    #:
    #: So what this node measures is what `OD-41` was about: the words appear **once in the
    #: header**. The per-indicator rows are counted separately, so a change that put the words
    #: back into the header twice still lights.
    head_rows = [row for row in text.splitlines() if _DATE.search(row)]
    assert len(head_rows) == 1, head_rows
    assert head.count(template.CLOSED_DAY_WORD) == 1, head
    assert head.count(template.PREVIOUS_DAY_WORD) == 1, head

    #: `OD-147`: one pair of rows per indicator, and this report has one indicator.
    assert text.count(f"{template.CLOSED_DAY_WORD}:") == 1, text
    assert text.count(f"{template.PREVIOUS_DAY_WORD}:") == 1, text


def test_the_colour_is_derived_from_the_source_and_flipping_it_flips_the_colour() -> None:
    """`OD-34`. **Which way is good comes from the metric's contract, not from this repository.**

    It came from the view's own column until `D-1303` on 2026-09-04; what never changed is
    that this repository does not hold the opinion.
    """
    rose = Decimal("8.97")
    fell = Decimal("-0.05")

    #: `lower_is_better=False` -- a rise is good.
    assert mark_for(rose, False) == template.MOVED_WELL
    assert mark_for(fell, False) == template.MOVED_BADLY

    #: Flip the SOURCE's own flag and every colour flips with it. Nothing else changed.
    assert mark_for(rose, True) == template.MOVED_BADLY
    assert mark_for(fell, True) == template.MOVED_WELL

    #: Exactly zero is neither, and an absence is not coloured at all.
    assert mark_for(Decimal("0"), False) == template.UNMOVED
    assert mark_for(Decimal("0"), True) == template.UNMOVED
    assert mark_for(None, False) == ""
    assert mark_for(rose, None) == "", "an unknown direction was given a colour"


def test_no_kpi_name_decides_a_colour() -> None:
    """**The `S-4` shape, refused.** A table of which KPIs are good going up would be an
    enumeration nothing forces to stay complete — and it would be this repository's opinion.

    `mark_for` takes the movement and the source's flag and **nothing else**: it cannot know
    a KPI's name, so it cannot hold a list of them. Two KPIs with opposite flags get opposite
    colours from the same movement, which is the whole property.
    """
    movement = Decimal("5")
    assert mark_for(movement, False) != mark_for(movement, True)

    #: And the module that renders holds no KPI name at all — asserted over its source by
    #: `tests/contract/test_the_loop_enumerates_nothing.py`, which this node leans on rather
    #: than repeating.
    assert "lower_is_better" in Reading.__dataclass_fields__


def test_a_count_carries_no_decimals_and_a_rate_does() -> None:
    """`OD-35`, and his question was the argument: *"e pq casas decimais, e nao e valor, mas
    sim, numeros absolutos?"*. There is no half trial.

    **Read from the source's `format_type`**, never from a list of KPI names.
    """
    assert _number(Decimal("644"), "int") == "644"
    assert _number(Decimal("24186"), "k") == "24.186"
    assert _number(Decimal("46860.55"), "usd_k") == "46.860,55 US$"

    #: A rate carries the per-cent sign, and the CONVERSION happens where the source is read
    #: -- measured: the four `Plan share` rates sum to exactly 1,0, so `0,0024` in the source
    #: is `0,24 %` to the reader, and the caller converts once before building the reading.
    assert _number(Decimal("0.24"), "pct") == "0,24 %"
    assert as_percent(Decimal("0.0024"), "pct") == Decimal("0.24")
    assert as_percent(Decimal("644"), "int") == Decimal("644")

    #: The mutation: the same number, one format_type away.
    assert _number(Decimal("644"), "int") != _number(Decimal("644"), "pct")
    assert _places_for("int") != _places_for("pct")


def test_the_variation_keeps_its_decimals_even_for_a_count() -> None:
    """A variation is a FRACTION, not a count of things: rounding it to whole numbers would
    throw the measurement away. `New trials` is `int` and still moves `+8,97 %`.
    """
    line = _kpi_line(_report(format_type="int"))
    assert "644" in line
    assert "+8,97" in line, line


def test_every_date_in_the_message_is_written_his_way() -> None:
    """`OD-33-B`: `dd/mm/yyyy`, and no ISO date survives anywhere in the message."""
    text = _report()
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text), text
    assert "29/08/2026" in text
    assert "28/08/2026" in text


def test_a_flat_series_never_alerts_on_standing_still() -> None:
    """Found running the twenty on 2026-08-30, and it would have alerted every day.

    `Semiannual (%)` is zero in 61.038 of its 61.041 rows, so the `p90` of its own movements
    is **zero** — and `abs(0) < 0` is false, so a KPI that never moved "crossed" its
    threshold daily. **Standing still is not a finding**, which is the same reading `OD-34`
    takes when it paints an exactly-zero movement yellow.
    """
    from daily_reporting.alert.rule import evaluate

    flat = [Decimal("0")] * 90
    assert evaluate("k", "pct", flat, Decimal("0"), comparable_periods_across_kpis=[90]) is None

    #: And a real movement over a flat history still crosses: the repair refuses zero, not
    #: the rule.
    crossing = evaluate("k", "pct", flat, Decimal("5"), comparable_periods_across_kpis=[90])
    assert crossing is not None
    assert crossing.movement == Decimal("5")


def test_the_alert_carries_its_threshold_and_the_report_never_does() -> None:
    """`OD-43`, and it exists because the two products arrived indistinguishable.

    He received both and asked *"pq esta repetindo duas kpis?"*. They were not a repetition:
    the second held exactly the two KPIs that crossed. **But the two messages looked the
    same** — same header, same sections, same line shape — so the only thing separating them
    was what had been left OUT, **and nobody reads what did not arrive.**

    The whole spec is built on two products that never mix. On the screen they mixed, which
    is the same family as everything else closed today: a thing that reads as another thing.

    So every ALERT line carries the threshold it crossed and how long the series was, and no
    REPORT line ever does. **Derived data, not a sentence**: the threshold is the `p90` of the
    KPI's own series and the count is the series length, both already computed on the run
    that prints them. No fourth authored string.
    """
    report = _report()
    alert = _report(crossings={"k": (Decimal("3.24"), 90)})

    #: The report says nothing about a threshold, on any line.
    assert "3,24" not in report, report
    #: The alert says it on the line that crossed.
    assert "3,24" in alert, alert
    assert "90" in alert, alert


def test_taking_the_threshold_off_an_alert_line_makes_it_a_report_line() -> None:
    """**Proof it bites both ways**, which `OD-43` asked for by name.

    Putting a threshold on a report line and taking one off an alert line are the two ways
    the products drift back together, and each has to be visible.
    """
    without = _report()
    with_it = _report(crossings={"k": (Decimal("3.24"), 90)})
    assert without != with_it, "the two products render identically, which is the defect"

    #: And the difference is exactly the crossing annotation, not something else moving.
    #:
    #: The shape is `T838`'s, with his word: the threshold wears **the same unit as the movement**
    #: — a volume here, so `%` — because `· 3,24 · 90` floated naked and he asked twice what the
    #: numbers were. The unit is already his (`OD-20-C`), the parentheses are punctuation, and the
    #: `90` stays a bare count until HE chooses its word — `FR-804`'s budget is not ours to spend.
    #: **`OD-151` (2026-09-06) moved it onto a row of its own, with a word.** His reasoning is
    #: the reason this node still measures a single difference: the threshold is WHY the
    #: indicator is in the alert, so it is first-class information rather than a trailing
    #: annotation -- and a bare pair at the end of a line read as a column somebody forgot to
    #: remove, which is the `OD-49` complaint under a different hat.
    from daily_reporting.report.template import (
        DAY_COUNT_WORD,
        OVER_PERIOD_WORD,
        THRESHOLD_LABEL,
    )

    row = f"{THRESHOLD_LABEL}: 3,24 % {OVER_PERIOD_WORD} 90 {DAY_COUNT_WORD}"
    assert row in with_it, with_it
    assert with_it.replace(chr(10) + row, "") == without, (
        f"the difference is not exactly the anchored crossing: {with_it!r}"
    )


def test_the_alignment_nodes_are_gone_because_the_alignment_is() -> None:
    """`OD-44` removed columns from the design, so the nodes that guarded them went too.

    **This is not a guard being dropped to make a red go away.** `S-9` measured a real thing —
    a coloured circle is one character and two display columns — and the ruler that fixed it
    was correct. What changed is that **there is no column left to align**: he refused the
    monospaced block that alignment depends on, and the layout now carries meaning by ORDER
    and PUNCTUATION, which no font can bend.

    A node asserting that two lines start on the same display column would now be asserting
    about something the product does not have. **Keeping it would be worse than removing it**:
    a green node over an absent property is exactly the thing this feature spent a day
    closing.
    """
    from daily_reporting.report import summary

    assert not hasattr(summary, "columns"), "the ruler is back without the columns it served"
    text = _report()
    #: **And since `OD-147` it carries its meaning by a WORD as well**, which is the stronger
    #: version of the same property: he refused monospace again on the day he chose this shape,
    #: and a row that names itself needs no font to be read in the right order.
    line = _kpi_line(text)
    assert all(": " in row for row in line.splitlines()[1:]), line
    #: No padding anywhere: a run of spaces is what a column looks like when the columns are
    #: supposed to be gone. The one indent in the message is the second currency's block, and
    #: this fixture carries no second currency.
    assert "  " not in text, text
    #: The header keeps the running form `OD-44` chose, which is the one line that still holds
    #: two facts side by side.
    assert " · " in next(row for row in text.splitlines() if _DATE.search(row)), text


def test_no_symbol_on_the_line_points_against_the_sign_of_the_movement() -> None:
    """`S-12`, and it is the FOURTH time a label and a number came apart in this feature.

    The line read `41 → 35` with `+17,14 %` beside it: **the arrow said it fell and the sign
    said it rose**, on every line at once. Two of his decisions had collided — yesterday comes
    FIRST, because it is the number that matters, and an arrow means a DIRECTION, which only
    exists along time. They do not fit together, so the arrow went.

    ## The pattern this node exists for

    Four times now: the header saying *ontem* over a week's total; a header promising a
    provenance the entries did not have; the header's date order against the line's value
    order; and now a symbol against a sign. **All four were found by HIM, none by a node of
    ours** — which is why this one asserts the class rather than the instance.
    """
    rising = _report(value=Decimal("41"), previous=Decimal("35"))
    falling = _report(value=Decimal("35"), previous=Decimal("41"))

    #: A rise must not carry a symbol that reads as a fall, nor the other way round.
    backwards = ("→", "->", "→", "⇒", ">")
    for text, sign in ((rising, "+"), (falling, "-")):
        line = _kpi_line(text)
        assert sign in line, line
        for symbol in backwards:
            assert symbol not in line, (symbol, line)

    #: **`OD-46` and `OD-147` COLLIDE here, and the collision is named rather than settled
    #: quietly.**
    #:
    #: `OD-46` was *"nao, tira esse ontem e anteontem na linha do kpi"*, said on 2026-08-30
    #: after `OD-45` had put the two words INLINE on a one-line indicator, where they were a
    #: second copy of what the header already said, sitting in a row the eye reads as numbers.
    #: `OD-147` (2026-09-06) is later, and he chose it over a preview built with his own
    #: numbers: the words are now ROW LABELS, one per number, each naming a different figure.
    #:
    #: The two orders are not reconciled by this file. What is asserted is the property `OD-46`
    #: was protecting -- no number is left for the reader to place by position alone -- which
    #: the new shape satisfies more strongly than the old one did.
    from daily_reporting.report import template

    rows = _kpi_line(rising).splitlines()
    for row in rows[1:]:
        assert ": " in row, row
    assert rows[1].startswith(f"{template.CLOSED_DAY_WORD}: "), rows
    assert rows[2].startswith(f"{template.PREVIOUS_DAY_WORD}: "), rows


# ---------------------------------------------------------------- OD-70 e OD-71


def test_the_sections_come_out_in_HIS_order_and_the_unlisted_survive() -> None:  # noqa: N802
    """`OD-70`, both sides.

    His words fixed the order; the node fixes that shuffling it lights. And a section the view
    gains one day, absent from his list, is NOT dropped — it appears after the declared ones. The
    20→17 lesson: what is not on the map must not vanish in silence.
    """
    import yaml as _yaml

    from daily_reporting.view.shape import sections_from

    #: The order is GOVERNED DATA — the node reads the same file production reads, so a hand
    #: edit to the yaml and a code change are caught by the same assertion.
    governed = Path(__file__).resolve().parents[4] / "report_governance" / "section_order.yaml"
    payload = _yaml.safe_load(governed.read_text(encoding="utf-8"))
    declared = tuple(payload["order"])
    assert payload["decided_by"] == "OD-70"
    #: His sentence, in his order, read from the governed file and not from this test's head.
    assert declared == ("Acquisition", "Revenue", "Retention", "Plan share", "LTV")

    rows = [
        {"kpi_name": f"k-{name}", "section_name": name}
        for name in (*reversed(declared), "Nova Frente")
    ]
    ordered = [section.name for section in sections_from(rows, declared_order=declared)]
    assert ordered[:5] == list(declared), ordered
    #: The unlisted section SURVIVES, after the declared ones.
    assert ordered[5] == "Nova Frente", ordered

    #: And with no order handed in, first-seen stands — the pre-OD-70 behaviour, kept.
    plain = [section.name for section in sections_from(rows)]
    assert plain[0] == "LTV"


def test_no_section_name_is_printed_and_his_governed_order_is_untouched() -> None:
    """`OD-146`, 2026-09-06: *"arranca a palavra Acquisition ali antes do Sales tbm"*.

    **A section label separates nothing when the report has one section.** Since `T1329` the
    08:00 daily carries three indicators of one family, so `Acquisition` stood alone above all
    of them, naming a partition with one part.

    **The governed file is NOT touched, and this node measures both halves.** Line 3 of
    `report_governance/section_order.yaml` carries his own words about the ordering and the
    KPIs still belong to those sections; what was removed is the PRINTING. So the order still
    decides which indicator comes first, and the name is nowhere on the screen.

    **Reintroduction condition**: the day the governed scope widens back to several families —
    the weekly (`T1331`) is exactly that — a label again separates things that need separating.
    Whoever restores it then is fulfilling this reasoning, not undoing the order.

    **Mutation**: print the section name again — red here. Drop the declared order — red in
    `test_the_sections_come_out_in_HIS_order_and_the_unlisted_survive`, which is the half this
    node must not be allowed to swallow.
    """
    import yaml as _yaml

    governed = Path(__file__).resolve().parents[4] / "report_governance" / "section_order.yaml"
    declared = tuple(_yaml.safe_load(governed.read_text(encoding="utf-8"))["order"])
    assert declared, "the governed order is empty; this node would forbid nothing"

    #: The KPI names are POSITIONS and carry no piece of the section's own name -- a label
    #: spelled `k-Acquisition` would make the assertion below pass or fail for the wrong reason.
    named = {name: f"k{index}" for index, name in enumerate(declared)}
    rows: tuple[ViewRow, ...] = tuple(
        {"section_name": name, "kpi_name": named[name]} for name in declared
    )
    readings = {
        named[name]: Reading(
            format_type="int",
            value=Decimal(10),
            previous_period=Decimal(9),
            current_period=Decimal(10),
            series_is_short=False,
            lower_is_better=False,
        )
        for name in declared
    }
    text = render(
        summarise(
            rows,
            readings,
            day=A_CLOSED_DAY,
            instant=AN_INSTANT,
            declared_order=declared,
        )
    )

    for name in declared:
        assert name not in text, f"the section name {name!r} is still printed"

    #: The ORDER still decides, which is what makes the deletion a rendering change and not a
    #: governance change: the indicators come out in his order, named after their sections.
    positions = [text.index(named[name]) for name in declared]
    assert positions == sorted(positions), positions


def test_neither_product_prints_a_description_under_its_title() -> None:
    """`OD-145` and `OD-149`, 2026-09-06 — two removals, two different arguments.

    `OD-145` reverses his own `OD-131` of the day before: *"ai esse ontem contra anteontem,
    arranca essa frase fora"*, because the row under it already prints the same two days as
    dates. `OD-149` removed the alert's for another reason entirely — `OD-151` moved that fact
    onto every indicator's own threshold row, so the subtitle repeated its own contents.

    **Both strings stay in the ledger** with their reintroduction conditions beside them; what
    this node measures is that neither reaches the screen, and that the title still does.

    **Mutation**: pass the description as the heading — the title disappears and this node is
    red on the first assertion. Print both — red on the second.
    """
    text = render(
        summarise(
            ROWS,
            {
                "k": Reading(
                    format_type="int",
                    value=Decimal(10),
                    previous_period=Decimal(9),
                    current_period=Decimal(10),
                    series_is_short=False,
                )
            },
            day=A_CLOSED_DAY,
            instant=AN_INSTANT,
        ),
        heading=template.REPORT_TITLE,
    )
    assert text.splitlines()[0] == template.REPORT_TITLE
    assert template.REPORT_DESCRIPTION not in text
    assert template.ALERT_DESCRIPTION not in text


def test_a_two_currency_kpi_renders_both_triplets_from_one_reading() -> None:
    """`OD-71` — the BRL triplet beside the USD one, same grammar, and TWO variations.

    Measured 2026-08-31 before this was written: Revenue moved +29,04 % in USD and +3,64 % in BRL
    between the same two days — the embedded rate moved — so one variation beside two currencies
    would describe neither.
    """
    rendered = _report(
        value=Decimal("46948.23"),
        previous=Decimal("46860.55"),
        format_type="usd_k",
        brl=(Decimal("67223.40"), Decimal("67231.00")),
    )
    #: `OD-150` (2026-09-06) gave the second currency a BLOCK of its own, indented and fenced,
    #: after `MRR` reached him as nine numbers on one line in two currencies. The whole
    #: indicator is read here, blank rows included, because the fence is part of the shape.
    rows = rendered.splitlines()
    start = next(i for i, row in enumerate(rows) if row.endswith("k"))
    line = chr(10).join(rows[start:])

    #: Both currencies, each number wearing its unit.
    assert "46.948,23 US$" in line and "46.860,55 US$" in line
    assert "67.223,40 R$" in line and "67.231,00 R$" in line
    #: TWO movements — the USD one and the BRL one, each computed from its own pair.
    assert "+0,19 %" in line, line
    assert "-0,01 %" in line, line
    #: And the grammar holds: USD block first, BRL block after, and the BRL block repeats the
    #: first one's rows rather than inventing a shape of its own.
    assert line.index("US$") < line.index("R$")
    assert f"  {template.IN_BRL_WORD}" in line, line
    for word in (template.CLOSED_DAY_WORD, template.PREVIOUS_DAY_WORD):
        assert line.count(f"{word}: ") == 2, line


def test_a_single_currency_kpi_is_untouched_by_od71() -> None:
    """The other direction: a count renders exactly as before — no BRL segment, no regression."""
    rendered = _report(value=Decimal("644"), previous=Decimal("591"), format_type="int")
    line = _kpi_line(rendered)
    assert "R$" not in line
    assert template.IN_BRL_WORD not in rendered
    assert "644" in line and "591" in line
