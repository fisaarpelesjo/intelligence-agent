"""The message MARKS the number that is a level — `SC-1306`, `FR-1318`, `T1330`.

`test_a_snapshot_is_the_last_day_not_the_sum.py` holds the arithmetic half: a `SNAPSHOT` is
the last day the rows cover, never their sum. This file holds the other half, which is the one
the reader can see. The criterion asks for both, and the second is not decoration: `New trials`
and `MRR` sit in the same message answering different questions — *how many happened over the
period* against *where the level stood at the end of it* — and nothing on the screen tells them
apart. A reader who adds two weekly `MRR` figures is doing the exact arithmetic the aggregate
now refuses to do, and the only thing that stops them is being told.

**The phrase is his and the package does not hold it.** It comes from the example contract
(`docs/exemplos-analise-dimensional.md`) through `report_governance/snapshot_mark.yaml`, the
path the section order and the second reference already take. So there are two separable
questions here, and a node for each: does the LINE know it is a level, and does the RENDERER
say so using only the words it was handed.

**Mutations.** The mark dropped from the rendered line → `3 failed, 4 passed`. Then three more,
one per defect ADVERSARIAL REVIEW found in the first version of this work — each seen red on its
own node, each restored by `cp` + `cmp`, all `1 failed, 9 passed`: the `SNAPSHOT` guard taken out
of `partition_by`, which is the door the breakdown and the contribution actually use while the
guard sat on a function nothing calls; the mark applied without requiring a number, which put
`(snapshot do último dia)` over a dash; and the mark folding case while the arithmetic does not,
which would have marked a row on the page that the number path refuses outright.

Each mutation reddens exactly ONE node, and that is the point: a file whose every node falls to
every mutation is asking one question ten times.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from daily_reporting.contracts import ReportRefusal
from daily_reporting.numbers.variation import VariationUnit
from daily_reporting.report.snapshot import SnapshotMarkGovernance, SnapshotMarkGovernanceError
from daily_reporting.report.summary import Line, Reading, Summary, render, summarise
from daily_reporting.view.reading import aggregate, partition_by

pytestmark = pytest.mark.unit

#: A phrase that is NOT the one in the governed file, so nothing here passes by echoing a
#: literal that also lives in the package. What the node asserts is that whatever the caller
#: hands over is what the reader sees.
A_GOVERNED_PHRASE = "nivel do fim do periodo"

#: Seven SNAPSHOT days, reused from the arithmetic node next door: what must never be added.
SEVEN_DAYS: tuple[dict[str, object], ...] = tuple(
    {"aggregation_class": "SNAPSHOT", "event_date": f"2026-09-{day:02}", "value": 9000 + day}
    for day in range(1, 8)
)

A_CLOSED_DAY = date(2026, 9, 4)
AN_INSTANT = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)


def _line(*, is_snapshot: bool, footnoted: bool = False, threshold: Decimal | None = None) -> Line:
    return Line(
        label="MRR (US$)",
        value=Decimal(52100),
        previous_value=Decimal(50900),
        variation=Decimal("2.36"),
        unit=VariationUnit.RELATIVE_PERCENT,
        footnoted=footnoted,
        format_type="usd_k",
        is_snapshot=is_snapshot,
        threshold=threshold,
        series_periods=90 if threshold is not None else None,
    )


def _rendered(line: Line, *, mark: str = A_GOVERNED_PHRASE) -> str:
    summary = Summary(day=A_CLOSED_DAY, sections=(("Revenue", (line,)),))
    return render(summary, snapshot_mark=mark)


def _kpi_line(line: Line, *, mark: str = A_GOVERNED_PHRASE) -> list[str]:
    """The indicator's own ROWS, found by its label rather than by position — `OD-147`.

    A footnoted line adds a block under the sections, so the last line of the message is not
    the KPI's — the first version of this file asserted on the header and said so.

    Since `OD-147` an indicator is a block of rows rather than one line, so this returns the
    rows: the questions below are about where the mark sits among them.
    """
    rendered = _rendered(line, mark=mark).splitlines()
    found = [i for i, text in enumerate(rendered) if line.label in text and ": " not in text]
    assert len(found) == 1, found
    end = next((i for i in range(found[0] + 1, len(rendered)) if rendered[i] == ""), len(rendered))
    return rendered[found[0] : end]


def test_the_level_carries_the_governed_phrase() -> None:
    """The visible delivery of this half of `SC-1306`."""
    assert A_GOVERNED_PHRASE in _rendered(_line(is_snapshot=True))


def test_an_accumulation_carries_nothing() -> None:
    """`New trials` is a count of things that happened, and marking it would be a lie."""
    assert A_GOVERNED_PHRASE not in _rendered(_line(is_snapshot=False))


def test_no_governed_phrase_means_no_invented_one() -> None:
    """A caller that loads no governed file gets silence, not a default.

    The same refusal the second reference makes when its two words are absent: this package
    authors no word, and a sentence appearing because a file was missing would be one.
    """
    marked = _rendered(_line(is_snapshot=True), mark="")
    unmarked = _rendered(_line(is_snapshot=False), mark="")
    assert marked == unmarked


def test_the_mark_closes_the_block_and_leaves_the_footnote_on_the_label() -> None:
    """Order is the whole design. It qualifies the numbers, so it follows them.

    **`OD-151` (2026-09-06) took it out of the parentheses and gave it a row.** He refused
    merging it into one trailing line with the threshold: they answer different questions —
    one says why the indicator is in the alert, the other says what kind of number the figures
    above are — so each closes the block on a line of its own.

    The footnote star moved WITH the label it is about: since `OD-147` the label has a row of
    its own, and the star is about the SOURCE being short rather than about any one figure, so
    it stays where the reader meets the indicator's name.
    """
    assert _kpi_line(_line(is_snapshot=True))[-1] == A_GOVERNED_PHRASE
    starred = _kpi_line(_line(is_snapshot=True, footnoted=True))
    assert starred[0].endswith(" *"), starred
    assert starred[-1] == A_GOVERNED_PHRASE, starred


def test_the_mark_follows_the_alert_annotation_instead_of_splitting_it() -> None:
    """On an alert block both annotations are present, and the ORDER is his — `OD-151`.

    The threshold row first, because it is the reason the indicator is in the alert; the level
    mark last, because it qualifies every figure above it. Two rows, never one: he refused
    merging them.
    """
    rows = _kpi_line(_line(is_snapshot=True, threshold=Decimal("1.80")))
    threshold = next(i for i, row in enumerate(rows) if row.endswith("90 d"))
    assert threshold < rows.index(A_GOVERNED_PHRASE)
    assert rows[-1] == A_GOVERNED_PHRASE, rows


def test_the_view_s_word_is_what_makes_a_line_a_level() -> None:
    """Read from the source, never inferred from the KPI's name.

    Which metrics are levels is a property of the warehouse. A package that decided it by name
    would mark the wrong lines the day a metric is added, which is the `D-1303` lesson about
    direction said again about shape.
    """
    rows = (
        {"section_name": "Revenue", "kpi_name": "MRR (US$)"},
        {"section_name": "Acquisition", "kpi_name": "New trials"},
        {"section_name": "Retention", "kpi_name": "MAU"},
        {"section_name": "Retention", "kpi_name": "Silent one"},
    )
    readings = {
        "MRR (US$)": Reading(
            format_type="usd_k",
            value=Decimal(52100),
            previous_period=Decimal(50900),
            current_period=Decimal(52100),
            series_is_short=False,
            aggregation_class="SNAPSHOT",
        ),
        "New trials": Reading(
            format_type="qty",
            value=Decimal(4892),
            previous_period=Decimal(4351),
            current_period=Decimal(4892),
            series_is_short=False,
            aggregation_class="COUNT",
        ),
        #: The surrounding space IS tolerated — a column that arrives padded is the same
        #: column. The CASE is not, and the node below says why.
        "MAU": Reading(
            format_type="qty",
            value=Decimal(38204),
            previous_period=Decimal(37050),
            current_period=Decimal(38204),
            series_is_short=False,
            aggregation_class="  SNAPSHOT  ",
        ),
        #: Nothing said, so nothing is marked — the answer `lower_is_better` gives to silence.
        "Silent one": Reading(
            format_type="qty",
            value=Decimal(3),
            previous_period=Decimal(2),
            current_period=Decimal(3),
            series_is_short=False,
        ),
    }
    summary = summarise(rows, readings, day=A_CLOSED_DAY, instant=AN_INSTANT)
    marked = {line.label: line.is_snapshot for _name, lines in summary.sections for line in lines}
    assert marked == {
        "MRR (US$)": True,
        "New trials": False,
        "MAU": True,
        "Silent one": False,
    }


def test_the_governed_file_hands_over_its_word_and_refuses_to_be_empty() -> None:
    """`S-41`: silence in a governed file is refused, never answered for."""
    governance = SnapshotMarkGovernance.from_document({"mark": A_GOVERNED_PHRASE})
    assert governance.words == (A_GOVERNED_PHRASE,)
    for document in ({}, {"mark": "   "}, {"mark": 7}, [1, 2]):
        with pytest.raises(SnapshotMarkGovernanceError):
            SnapshotMarkGovernance.from_document(document)


def test_the_mark_and_the_arithmetic_read_the_column_the_same_way() -> None:
    """**One column, two readers, one spelling** — found by adversarial review of `4a32be8`.

    The first version folded case here and nowhere else. `aggregation_class_of` compares
    ``str(...).strip()`` against the class and REFUSES anything it does not know, so a row
    spelled ``snapshot`` would have been marked on the page by this reader and would have killed
    the delivery in the other — the mark arriving over a number that was never computed.

    The node drives both readers over the same spellings, which is the only way the agreement
    stays true when either one is edited.
    """
    for spelling, is_a_level in (("SNAPSHOT", True), ("  SNAPSHOT  ", True), ("snapshot", False)):
        rows = ({"aggregation_class": spelling, "event_date": "2026-09-05", "value": 9117},)
        marked = (
            summarise(
                ({"section_name": "Revenue", "kpi_name": "MRR (US$)"},),
                {
                    "MRR (US$)": Reading(
                        format_type="usd_k",
                        value=Decimal(9117),
                        previous_period=Decimal(9102),
                        current_period=Decimal(9117),
                        series_is_short=False,
                        aggregation_class=spelling,
                    )
                },
                day=A_CLOSED_DAY,
                instant=AN_INSTANT,
            )
            .sections[0][1][0]
            .is_snapshot
        )
        assert marked is is_a_level, spelling
        #: The arithmetic's answer to the same spelling: the level for the two it knows, and a
        #: refusal for the one it does not. Never a number computed some other way.
        if is_a_level:
            assert aggregate(rows, "value") == Decimal(9117), spelling
        else:
            with pytest.raises(ReportRefusal):
                aggregate(rows, "value")


def test_a_level_with_no_number_carries_no_mark() -> None:
    """`(snapshot do último dia)` over a dash asserts a level nobody measured.

    Reachable, and not by accident: the caller reads the class from the PREVIOUS day when the
    closed day has not loaded yet, exactly so a count keeps its decimals through the pre-rebuild
    window. The class survives the empty day and the number does not, so the mark had a line to
    sit on with nothing under it. Two KPIs lag the closed day by a day and by two.
    """
    unloaded = Line(
        label="MAU",
        value=None,
        previous_value=Decimal(37050),
        variation=None,
        unit=VariationUnit.RELATIVE_PERCENT,
        footnoted=True,
        format_type="qty",
        is_snapshot=True,
    )
    #: The `Line` still carries the fact — a caller may know it is a level — and the RENDERER is
    #: what stays silent. Said the other way round: the mark is about a number, so no number is
    #: no mark, and `summarise` is where the two are known together.
    line = summarise(
        ({"section_name": "Retention", "kpi_name": "MAU"},),
        {
            "MAU": Reading(
                format_type="qty",
                value=None,
                previous_period=Decimal(37050),
                current_period=None,
                series_is_short=False,
                aggregation_class="SNAPSHOT",
            )
        },
        day=A_CLOSED_DAY,
        instant=AN_INSTANT,
    ).sections[0][1][0]
    assert line.value is None
    assert line.is_snapshot is False
    assert unloaded.is_snapshot is True


def test_a_level_is_never_partitioned_by_the_door_the_breakdown_uses() -> None:
    """The guard was one door away from the arithmetic it protects — `1756d11`, reviewed.

    `aggregate_by` carried the refusal and `aggregate_by` has no caller outside its own tests.
    The breakdown and the contribution reach their parts through `partition_by` and then call
    `aggregate` per group, which after `T1330` takes each part's OWN last day: Brazil on one day
    and a smaller country on an older one, added together and called a week.
    """
    week = tuple({**row, "country": "Brazil"} for row in SEVEN_DAYS)
    with pytest.raises(ReportRefusal):
        partition_by(week, "country")
    #: A mixed bag refuses too, and for the same reason rather than for a different one: the
    #: question is *does any row say level*, not *what single class do these rows state*.
    with pytest.raises(ReportRefusal):
        one_count = {"aggregation_class": "COUNT", "country": "Mexico", "value": 1}
        partition_by((*week, one_count), "country")
    #: And nothing that worked stops working.
    counted = ({"aggregation_class": "COUNT", "country": "Brazil", "value": 41},)
    assert partition_by(counted, "country") == (("Brazil", counted),)
