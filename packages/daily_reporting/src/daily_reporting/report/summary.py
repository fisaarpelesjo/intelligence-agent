"""The daily report — every line it is given, **no threshold** — `T801`, `T803`, `T807`.

## This module has no threshold, and cannot acquire one

:func:`summarise` takes no threshold parameter, reads none, and imports nothing from
:mod:`daily_reporting.alert`. That is `FR-801` and the owner's `OD-14-A`, and it is
enforced by a node rather than by discipline.

**The failure it prevents is a flag.** Merged now and split later never happens; what
happens is one function growing a keyword argument, and a flag is how a summary
silently becomes an alarm — after which a reader who receives one cannot tell whether
silence means *nothing moved* or *nothing was measured*.

## Every KPI it is given, and WHICH KPIs is not this module's to say

This function carries every line handed to it, including one no reading covered, and it counts
to nothing: not to twenty, not to three. That is the whole of `FR-805`/`SC-801` that lives here,
and `test_every_kpi_the_view_declares_reaches_the_page` measures exactly it, over a fixture.

**Which KPIs reach the 08:00 daily is the CALLER's, and it is governed data** —
`report_governance/daily_scope.yaml` (`T1329`, `OD-107`, `FR-1319`), applied by
:func:`daily_reporting.report.scope.scoped_kpis`, which refuses a name no active contract carries
and refuses an empty list. Since 2026-09-05 the daily carries three of the nineteen active KPIs,
by his decision, and the other sixteen are the weekly's (`T1331`).

**The sentence that stood here until then said the set was the view's and that a KPI missing from
the report was a claim nobody made.** That was true of the product before `T1329` and false after
it, while the node kept passing, because the node measures this module and the decision moved one
layer up (`S-58`, 2026-09-05). The same claim is still written in the spec of `008` — `FR-805`
*"no ACTIVE KPI may be omitted"*, `SC-801` — which `FR-1319` of `013` contradicts: reconciling the
two documents is the owner's, recorded and not repaired here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final
from zoneinfo import ZoneInfo

from ..numbers.period import BUSINESS_ZONE, refuse_unless_closed
from ..numbers.variation import (
    RATE_FORMAT,
    WHOLE_FORMATS,
    VariationUnit,
    value_unit_for,
    variation_between,
    variation_unit_for,
)
from ..view.reading import SNAPSHOT
from ..view.shape import Section, ViewRow, sections_from
from .breakdown import Breakdown, BreakdownGovernance
from .contribution import (
    ContributionGovernance,
    Discarded,
    Pull,
    refuse_unavailable_coverage,
)
from .template import (
    CLOSED_DAY_WORD,
    DAY_COUNT_WORD,
    IN_BRL_WORD,
    MOVED_BADLY,
    MOVED_WELL,
    OVER_PERIOD_WORD,
    PREVIOUS_DAY_WORD,
    SHORT_OR_EMPTY_SOURCE,
    THRESHOLD_LABEL,
    UNMOVED,
    VARIATION_WORD,
)

__all__ = ["Line", "Summary", "render", "summarise"]


@dataclass(frozen=True, slots=True)
class Reading:
    """One KPI as the caller measured it, **with the two periods kept apart**.

    ## The defect this shape exists because of

    It used to carry ``previous`` and ``current`` and nothing else, and the report rendered
    ``current`` beside a header that says *yesterday*. **The caller had measured weeks.** So
    the line read `New trials: 3957.00` under `ontem 2026-08-27`, when yesterday was **515**
    — the arithmetic was right, the numbers were real to the second decimal, and the LABEL
    was wrong.

    **One pair of numbers was doing two jobs.** `OD-14-E` made the COMPARISON weekly because
    the daily series is noisy; it did not make the VALUE weekly, and the form he approved
    shows a daily figure. Splitting the fields is what makes the two periods impossible to
    confuse, rather than a rule somebody has to remember.
    """

    format_type: str

    #: The **closed day's** value — what the header names.
    value: Decimal | None

    #: The two comparison periods the variation is computed from, and what
    #: :class:`Summary` names by date.
    #:
    #: **ONE DAY EACH since 2026-08-30, by `OD-31`**, which supersedes `OD-14-E`: his words
    #: were *"tem que ter ontem, antes de ontem, ai fica o comparativo, sempre vai ser
    #: assim"*. `OD-14-E` had chosen weeks because the daily series is noisy; he saw the
    #: result and asked for days, and his most recent instruction is precedence 1.
    #:
    #: **The cost is named rather than hidden**: a daily series swings more, so a `p90`
    #: derived from daily variation fires more often, and a holiday or a weekend becomes a
    #: large movement that means nothing. The threshold is RECOMPUTED over the daily series —
    #: `FR-811` derives it from the series itself and `FR-812` forbids writing it down — so
    #: the weekly one is not reused.
    previous_period: Decimal | None
    current_period: Decimal | None

    series_is_short: bool

    #: The SECOND reference — `FR-1306`, `SC-1305`, slice `F2`. The same weekday a week back,
    #: measured by the caller from the same read. `None` when that day is not in the window,
    #: and then the line carries one reference instead of inventing a second: a comparison
    #: against a day nobody measured is worse than no comparison.
    week_ago: Decimal | None = None

    #: Which way is good for this KPI, **read from the METRIC'S CONTRACT** and never decided
    #: here — `OD-34`, moved out of the view's column by `D-1303` (`OD-113`) on 2026-09-04.
    #: `None` when nothing declares it, and then the movement carries no mark: a colour over
    #: an unknown direction is an opinion wearing the clothes of data.
    lower_is_better: bool | None = None
    #: **The same KPI in BRL, from the SAME rows — `OD-71`, 2026-08-31**, his words: *"Tem que ter
    #: MRR e Revenue em reais brasileiros tambem, pq trabalhamos tanto em dolar quanto em reais"*.
    #: `None` for every KPI not carried in two currencies. The pair comes from the same view
    #: line's `value_brl` — never a second query, never a rate applied here.
    brl_value: Decimal | None = None
    brl_previous: Decimal | None = None
    #: The view's own format word for the BRL pair, read by the caller from the source. This
    #: module never writes a format name.
    brl_format: str = ""

    #: What the view says this KPI IS — `SC-1306`, `T1330`. Read from the source by the caller,
    #: never inferred here from the KPI's name: which metrics are levels is a property of the
    #: warehouse, and a package that guessed it would mark the wrong lines the day a metric is
    #: added. Empty means the caller did not say, and then the line carries no mark, which is
    #: the same answer `lower_is_better` gives to the same silence.
    aggregation_class: str = ""


@dataclass(frozen=True, slots=True)
class Line:
    """One KPI's line: a label, both days' values, a movement, and no sentence.

    ``previous_value`` arrived with `OD-31`. He asked to SEE both days rather than only the
    movement between them, and a variation whose two terms are invisible is a number the
    reader cannot check — which is the same complaint that produced the period line.
    """

    label: str
    value: Decimal | None
    previous_value: Decimal | None
    variation: Decimal | None
    unit: VariationUnit
    footnoted: bool
    #: The second reference and the movement against it — `FR-1306`. Both or neither: a
    #: variation whose other term is invisible is a number the reader cannot check, which is
    #: the same complaint that produced `previous_value`.
    week_ago_value: Decimal | None = None
    week_ago_variation: Decimal | None = None
    #: `F1` (`FR-1302`): this KPI's breakdowns, already cut. **Deliberately NOT `Line`** — the
    #: node that asserts the report carries every KPI compares the SET of labels, and
    #: sub-lines shaped as `Line` would enter that set and break a guard that is right. A
    #: parallel type keeps the two questions apart: which KPIs exist, and what each one
    #: breaks down into.
    breakdowns: tuple[Breakdown, ...] = ()
    #: `OD-71`: the BRL triplet, rendered after the USD one when present. **The variations are
    #: TWO because they genuinely differ** — measured 2026-08-31 on the real series: Revenue moved
    #: +29,04 % in USD and +3,64 % in BRL between the same two days, because the embedded rate
    #: moved (2,0402 → 1,6387). One variation beside two currencies would describe neither.
    brl_value: Decimal | None = None
    brl_previous: Decimal | None = None
    brl_variation: Decimal | None = None
    #: The FORMAT the BRL pair renders in — the view's own vocabulary, handed in by the caller
    #: that read it from the source. Never a literal here: this module writes no format name.
    brl_format: str = ""

    #: What the source says the number is measured in, so the line can show a COUNT with no
    #: decimals — `OD-35`. There is no half trial.
    format_type: str = ""

    #: Which way is good, from the METRIC'S CONTRACT — `D-1303` moved it out of the view's
    #: own column on 2026-09-04. `None` means the contract did not say.
    lower_is_better: bool | None = None

    #: This number is a LEVEL and not an accumulation — `SC-1306`. **The fact lives here and
    #: the PHRASE does not**: the words are his, and they arrive at `render` from
    #: `report_governance/snapshot_mark.yaml` the way `D-7` and the axis labels do. A `Line`
    #: holding the sentence would be this package authoring it.
    is_snapshot: bool = False

    #: The threshold this KPI's movement crossed, and over how many periods it was derived.
    #: **Present on an ALERT line and absent on a REPORT line** — `OD-43`, and that presence
    #: is what tells the two products apart on screen.
    #:
    #: He received both and asked *"pq esta repetindo duas kpis?"*: they arrived visually
    #: identical — same header, same sections, same line shape — and **only what was left OUT
    #: distinguished them, which nobody can read.** The whole spec is built on two products
    #: that never mix, and on the screen they mixed.
    #:
    #: No new word: the threshold is the `p90` of the KPI's own series (`FR-811`) and the
    #: count is `FR-814`'s, both already computed on the run that prints them (`FR-812`).
    threshold: Decimal | None = None
    series_periods: int | None = None


@dataclass(frozen=True, slots=True)
class Summary:
    """The whole report, and **every period in it is named**.

    ``day`` is what the values are. ``periods`` is what the variations compare, and it is
    carried rather than assumed because a variation over a different span than the value is
    legitimate — `OD-14-E` chose exactly that — and **illegible if nobody says which is
    which**.
    """

    day: date
    sections: tuple[tuple[str, tuple[Line, ...]], ...]

    #: ``((current_start, current_end), (previous_start, previous_end))``, or ``None`` when
    #: no variation is reported at all. Dates, never words: naming a period in prose would
    #: be a third authored string, and `FR-804` allows two.
    #:
    #: **Under `OD-31` each period is ONE DAY**, so both collapse to a single date when
    #: rendered. The rule above is why the second day appears as a DATE and not as a word:
    #: *anteontem* would be that third string, and `FR-804` says any third is a violation.
    periods: tuple[tuple[date, date], tuple[date, date]] | None = None

    #: `F3` (`FR-1308`..`FR-1310`): who pulled the day, as a flat list across KPIs. **Not a
    #: `Line` and not a section** — the same reasoning `Line.breakdowns` records: a parallel
    #: type cannot be mistaken for an indicator by a node that counts indicators.
    #:
    #: Empty means one of two different things, and `render` tells them apart by asking the
    #: governance rather than by guessing: the block was refused, or nothing cleared the bar.
    pulls: tuple[Pull, ...] = ()
    #: O que foi MEDIDO E ELIMINADO -- `T1334`, peça 6. Fica ao lado de ``pulls`` porque é o
    #: complemento dele: as partes que a mesma medição tocou e que NÃO deixaram a própria banda.
    discarded: tuple[Discarded, ...] = ()


def summarise(
    rows: Iterable[ViewRow],
    readings: Mapping[str, Reading],
    *,
    day: date,
    instant: datetime,
    periods: tuple[tuple[date, date], tuple[date, date]] | None = None,
    crossings: Mapping[str, tuple[Decimal, int]] | None = None,
    zone: ZoneInfo = BUSINESS_ZONE,
    declared_order: Sequence[str] = (),
    breakdowns: Mapping[str, tuple[Breakdown, ...]] | None = None,
    pulls: Sequence[Pull] = (),
    discarded: Sequence[Discarded] = (),
) -> Summary:
    """The daily report over ``rows``, for the closed ``day``.

    ``readings`` carries what the caller measured, per KPI label. A KPI the view
    declares and the readings do not cover **still appears**, with no value and the
    footnote: `FR-815`'s reasoning generalised — an absence reported is a fact, and an
    absence omitted is a KPI the reader never learns is missing.

    ``breakdowns`` is per KPI label and comes from the CALLER, already cut (`F1`). The caller
    is who holds the contracts and the governed file; this function positions what it is
    given and computes no breakdown of its own. A KPI absent from the mapping renders exactly
    as it did before `F1`.
    """
    refuse_unless_closed(day, instant, zone)
    sections: list[tuple[str, tuple[Line, ...]]] = []
    for section in sections_from(rows, declared_order=declared_order):
        sections.append(
            (section.name, _lines_of(section, readings, crossings or {}, breakdowns or {}))
        )
    return Summary(
        day=day,
        sections=tuple(sections),
        periods=periods,
        pulls=tuple(pulls),
        discarded=tuple(discarded),
    )


def _lines_of(
    section: Section,
    readings: Mapping[str, Reading],
    crossings: Mapping[str, tuple[Decimal, int]],
    breakdowns: Mapping[str, tuple[Breakdown, ...]],
) -> tuple[Line, ...]:
    lines: list[Line] = []
    for kpi in section.kpis:
        reading = readings.get(kpi)
        if reading is None:
            lines.append(
                Line(
                    label=kpi,
                    value=None,
                    previous_value=None,
                    variation=None,
                    unit=VariationUnit.RELATIVE_PERCENT,
                    footnoted=True,
                    format_type="",
                    lower_is_better=None,
                )
            )
            continue
        unit = variation_unit_for(reading.format_type)
        movement = (
            variation_between(reading.previous_period, reading.current_period, unit)
            if reading.previous_period is not None and reading.current_period is not None
            else None
        )
        against_week = (
            variation_between(reading.week_ago, reading.current_period, unit)
            if reading.week_ago is not None and reading.current_period is not None
            else None
        )
        lines.append(
            Line(
                label=kpi,
                value=reading.value,
                previous_value=reading.previous_period,
                variation=movement,
                week_ago_value=reading.week_ago,
                week_ago_variation=against_week,
                unit=unit,
                footnoted=reading.series_is_short or reading.value is None,
                format_type=reading.format_type,
                lower_is_better=reading.lower_is_better,
                #: **The same spelling rule the ARITHMETIC uses, exactly** — `aggregation_class_of`
                #: compares `str(...).strip()` against the class and refuses anything else. The
                #: first version of this line folded case as well, so a row spelled `snapshot`
                #: would have been MARKED here and REFUSED there: the mark would reach the page
                #: and the number would kill the delivery. Two readers of one column, one rule.
                #:
                #: And the mark needs a NUMBER to be about. A line whose closed day has not
                #: loaded renders a dash with the short-source footnote, and `(snapshot do
                #: último dia)` over a dash asserts a level nobody measured — the class survives
                #: the empty day on purpose (it is read from `anywhere`), which is what made this
                #: reachable. Both found by adversarial review of `4a32be8`.
                is_snapshot=(
                    reading.value is not None and reading.aggregation_class.strip() == SNAPSHOT
                ),
                breakdowns=breakdowns.get(kpi, ()),
                threshold=crossings[kpi][0] if kpi in crossings else None,
                series_periods=crossings[kpi][1] if kpi in crossings else None,
                brl_value=reading.brl_value,
                brl_previous=reading.brl_previous,
                brl_format=reading.brl_format,
                #: `OD-71`: money is a volume, so the BRL movement is relative percent — the same
                #: rule the USD side of these KPIs already follows.
                brl_variation=(
                    variation_between(
                        reading.brl_previous, reading.brl_value, VariationUnit.RELATIVE_PERCENT
                    )
                    if reading.brl_previous is not None and reading.brl_value is not None
                    else None
                ),
            )
        )
    return tuple(lines)


#: How a date reaches him. `OD-33-B`: `dd/mm/yyyy`, everywhere in the message. It is a fact
#: about how he reads a date, the same class as the thousands separator `_shown` already
#: carries, and it authors no word.
def _day_text(day: date) -> str:
    return f"{day.day:02}/{day.month:02}/{day.year}"


def _plain(text: str) -> str:
    """The default style: the text, untouched.

    **Markup is the carrier's business, not the report's** — `OD-48`. A tag written in this
    module would be a string with a letter in it that is nobody's word, and the node that
    counts authored strings said so the moment one appeared. So the report hands its label and
    its running text through a style the caller supplies, and writes no mark of its own.
    """
    return text


def _period_text(period: tuple[date, date]) -> str:
    """One period as a date, or as a range when it spans more than a day."""
    start, end = period
    return _day_text(start) if start == end else f"{_day_text(start)}..{_day_text(end)}"


def _separate(out: list[str]) -> None:
    """Open a new block of content with ONE blank line, whatever the last one left behind.

    `S-46`. Two separators meeting is not a bigger break, it is a hole: on the real message the
    fence under `Acquisition`'s last axis met the blank that opens `Revenue`, and the reader saw
    a gap twice the size of every other. Every junction in this message asks for the same thing
    — one blank — and asking here once is why no caller has to remember what came before it.
    """
    if out and out[-1] != "":
        out.append("")


def render(
    summary: Summary,
    *,
    heading: str = "",
    label_style: Callable[[str], str] = _plain,
    text_style: Callable[[str], str] = _plain,
    tail_label: str = "",
    tail_noun: str = "",
    reference_label: str = "",
    reference_against: str = "",
    reference_was: str = "",
    contribution: ContributionGovernance | None = None,
    for_alert: bool = False,
    breakdowns_governance: BreakdownGovernance | None = None,
    snapshot_mark: str = "",
) -> str:
    """The report as text: a title, the two dates, and a labelled BLOCK per KPI.

    **No sentence is assembled here.** Every fragment is punctuation, a date, a number or a
    single word of his, and ``tests/security/test_no_composed_prose.py`` walks this module's
    syntax tree to keep it that way.

    ## Nothing here is aligned, and that is `OD-44` rather than an omission

    The report was built on columns for a day and **arrived crooked four times**. `S-11` found
    why, and the finding was right: plain text reaches Telegram in a **proportional font**,
    where a space is narrower than a digit, so **no padding aligns anything** — the arithmetic
    can be exact and the screen still wrong. The remedy was a monospaced block, and he
    **refused it**: *"ESQUECE ESSA IDEIA DE MONOESPACO"*, after *"QUEBROU FOI TUDO, EU SO
    QUERIA QUE VOCE ALINHASSE AS COISAS CERTINHO"*.

    So the design stops needing it. **Meaning is carried by ORDER and PUNCTUATION**, which
    survive any font, and since `OD-147` by a WORD on every row as well.

    ## `OD-147` (2026-09-06): the numbers stopped being naked, and he refused monospace again

    The line he read closed as `736 · 695 · +5,90 % · +12,54 %` with a bracketed number after
    it. Four numbers, one separator, and **nothing saying which was which** — order carried all
    of it, and order is exactly what a reader cannot check. He chose a labelled shape from a
    preview built with his own numbers: the mark and the label on one row, then one row per
    number, each opening with the word that names it. :func:`_indicator_lines` builds it.

    **This is not the monospaced block of `OD-44` coming back.** The shape depends on no font
    to align: every row names itself, so nothing has to line up under anything. The refusal
    recorded above stands unchanged, and he restated it.

    ## `OD-146`: no section name is rendered, and the governed order is untouched

    His words: *"arranca a palavra Acquisition ali antes do Sales tbm"*. **A section label
    separates nothing when the report has one section** — since `T1329` the 08:00 daily carries
    three indicators of one family, so `Acquisition` stood alone above all of them, naming a
    partition with one part.

    `report_governance/section_order.yaml` is NOT touched: the KPIs still belong to those
    sections and line 3 of that file carries his own words about the ordering. What was removed
    is the PRINTING. **Reintroduction condition**: the day the governed scope widens back to
    several families — the weekly (`T1331`) is exactly that — a label again separates things
    that need separating, and whoever restores it is fulfilling this reasoning rather than
    undoing the order.

    `S-9`'s display-width ruler stops mattering **for layout** the moment there is no width to
    compute. It is recorded as measured and superseded, not as a debt.
    """
    #: **The product names itself first** — `OD-49`. Title, then the dates, then the
    #: indicators. The caller says which of the two this is; the WORD is his, counted by
    #: `AUTHORED_WORDS`, so a caller cannot invent a heading here.
    #:
    #: **The DESCRIPTION under the title is gone** — `OD-145` for the daily, `OD-149` for the
    #: alert, both on 2026-09-06, and the two are different arguments. `OD-145` reverses his own
    #: `OD-131` of the day before: *"ai esse ontem contra anteontem, arranca essa frase fora"* —
    #: the sentence said in words exactly what the line right below it says in dates. `OD-149`
    #: removed the alert's for another reason entirely: `OD-151` moved that fact onto every
    #: indicator's own threshold line, so the subtitle repeated its own contents. Both strings
    #: stay in `template.py` with their reintroduction conditions beside them; what changed is
    #: that `render` takes a TITLE and no longer a pair.
    out: list[str] = []
    if heading:
        out.append(text_style(heading))
        out.append("")
    if summary.periods is not None:
        current, previous = summary.periods
        out.append(
            text_style(
                f"{CLOSED_DAY_WORD} {_period_text(current)}"
                f" · {PREVIOUS_DAY_WORD} {_period_text(previous)}"
            )
        )
    else:
        out.append(text_style(f"{CLOSED_DAY_WORD} {_day_text(summary.day)}"))

    for _name, lines in summary.sections:
        #: `OD-146`: the section NAME is not printed. The loop still walks the sections,
        #: because the governed ORDER decides which indicator comes first and that decision is
        #: `OD-70`, untouched. What is gone is the label above them.
        for line in lines:
            #: One blank between blocks of content, never two. Since `OD-147` an indicator IS a
            #: block — four or five rows of its own — so the separator that used to sit between
            #: sections now sits between indicators, and `_separate` is what keeps it from
            #: meeting the fence `S-46` puts under a breakdown and reading as a hole.
            _separate(out)
            #: **Not through `text_style`, exactly as the one-line form was not** — the label
            #: has already been through `label_style`, which in the caller escapes and then
            #: marks, and escaping the result would put the tag itself on his screen. Every
            #: other row of the block is his own words, a date word, a number and its unit.
            out.extend(
                _indicator_lines(
                    line,
                    label_style,
                    reference_label,
                    reference_against,
                    reference_was,
                    snapshot_mark=snapshot_mark,
                )
            )
            #: `F1`: the breakdowns sit UNDER the line they belong to, in the order the
            #: governed file declares. A line with none renders exactly as it did before —
            #: which is what makes this safe to ship before every KPI has any.
            #:
            #: `OD-119` and `S-46`: the group of blocks under one indicator is FENCED by blank
            #: lines — one before the first and one after the last.
            #:
            #: The first rule said *before each block and none after the last*, so that an
            #: indicator would not hand a hole to the one below it. He read the result and the
            #: effect was worse: the tail of the last block sat directly against the next
            #: indicator's line — `demais 68 valores: 218` and `Sales (qty)` with nothing
            #: between them. A block of content must not touch a different block of content,
            #: and that is the rule in every junction of this message, not only this one.
            #:
            #: An indicator with no breakdown is untouched, which is what keeps `F1` safe to
            #: ship over KPIs that have no axis.
            if line.breakdowns and breakdowns_governance is not None:
                for breakdown in line.breakdowns:
                    _separate(out)
                    out.extend(
                        text_style(text)
                        for text in _breakdown_lines(
                            breakdown, breakdowns_governance, line.format_type
                        )
                    )
                _separate(out)
    #: `F3`: the block sits AFTER every section, because it speaks about the day rather than
    #: about one indicator. It is emitted only when the caller supplied the governed words —
    #: a block rendered from words nobody approved is what this package refuses to be.
    if contribution is not None:
        _separate(out)
        out.extend(
            text_style(line)
            for line in _contribution_lines(
                summary.pulls, contribution, for_alert, breakdowns_governance
            )
        )
        #: A peça 6 vai SÓ ao alerta, e isso é o contrato dele e não uma escolha de gosto: a
        #: frase "Descartado por medição" está no exemplo do ALERTA (linha 140), e o relatório
        #: diário não afirma hipóteses eliminadas porque não afirma hipóteses. Um relatório que
        #: dissesse o que descartou estaria a responder uma pergunta que ninguém lhe fez.
        descartado = _discarded_lines(
            summary.discarded, contribution, for_alert, breakdowns_governance
        )
        if descartado:
            _separate(out)
            out.extend(text_style(line) for line in descartado)
    if any(line.footnoted for _, lines in summary.sections for line in lines):
        _separate(out)
        out.append(text_style(f"* {SHORT_OR_EMPTY_SOURCE}"))
    return "\n".join(out)


def _contribution_lines(
    pulls: Sequence[Pull],
    governance: ContributionGovernance,
    for_alert: bool = False,
    icons: BreakdownGovernance | None = None,
) -> list[str]:
    """The block, or the one sentence that says the day was quiet — `FR-1310`, `OD-142`.

    **An empty block is never an empty section.** A heading with nothing under it reads as a
    failure of the report; his contract closes a quiet day with a sentence instead, and that
    sentence is his, transcribed with the rest.

    Not one word is composed here. Every token with a letter comes from ``governance`` or from
    the governed breakdown file, and the punctuation between them carries none — which is what
    lets `_every_word_is_his` see a vocabulary rather than an invention.

    ## `OD-142` (2026-09-06): four named groups, sorted by size, where a flat list was

    The block reached him as **thirty-seven lines**, flat, with a country and a game title
    alternating under two different indicators and the whole thing **sorted by NAME** —
    `Belarus +2` above `Poland +11`. He said it twice: *"nem dá pra ler"*, and *"tem que
    separar os jogos e os países, pq está tudo numa coisa só"*.

    So one list became four, each headed by the indicator and the axis it decomposes, each
    ranked by MAGNITUDE and cut to the governed few with a counted tail behind them. **The
    axis words are not written here**: they are the same `axis_labels` the breakdown renders
    from, read out of `report_governance/breakdown.yaml`.

    The group's identity is `(indicator, axis)` and the ORDER of the groups is derived, not
    chosen: the indicators in the order the caller produced them, and inside each indicator the
    axes in the order his governed file declares. Nothing here decides which axis comes first.
    """
    if not pulls:
        #: **O FECHO DO DIA QUIETO É DO RELATÓRIO, E FICA NO RELATÓRIO.**
        #:
        #: Medido no alerta de 2026-09-07, 08:01 -03, que saiu para três destinatários: ele
        #: carregava `Trial conversion (%)`, `Revenue (US$)` e `MAU`, e fechava a afirmar que
        #: nenhuma dimensão saíra da banda. **Dos três, só o primeiro tem dimensão declarada**
        #: (`report_governance/breakdown.yaml`, `kpis:`) — os outros dois nunca foram
        #: examinados. A frase não era uma ausência: era uma afirmação positiva sobre uma
        #: medição que não aconteceu, a três centímetros de um `Revenue (US$) -36,38 %`.
        #:
        #: **E o enquadramento é dele.** O contrato aprovado põe a frase no fecho do RELATÓRIO
        #: (`docs/exemplos-analise-dimensional.md`, 43-44, dentro da secção 1) e diz o que ela
        #: pressupõe: *"muda só o fecho: as quebras continuam"*. Ela é o que se diz quando se
        #: OLHOU e não se achou. O alerta é a secção 3 e não carrega quebras.
        #:
        #: Então o alerta fica **sem bloco**, que é o que ele já faz com todos os blocos que
        #: não tem. Nada de frase substituta: *"nenhuma dimensão foi examinada"* seria
        #: vocabulário que ele não deu, e a cura de uma afirmação não sustentada não pode ser
        #: outra afirmação nossa. O relatório continua a fechar como sempre fechou, porque lá
        #: os KPIs declarados FORAM examinados e a frase é verdadeira.
        return [] if for_alert else [governance.quiet_day]
    heading = governance.heading_alert if for_alert else governance.heading
    out = [f"{governance.heading_emoji} {heading}:"]
    for (kpi, column), group in _pull_groups(pulls, icons):
        out.append("")
        out.extend(_group_lines(kpi, column, group, governance, icons))
    return out


def _discarded_lines(
    discarded: Sequence[Discarded],
    governance: ContributionGovernance,
    for_alert: bool,
    breakdowns_governance: BreakdownGovernance | None = None,
) -> list[str]:
    """As hipóteses medidas e eliminadas — `T1334`, peça 6 do contrato aprovado.

    **Nenhuma palavra é composta aqui**, pela mesma regra do bloco acima: cada token com letra
    sai de ``governance`` — ``discarded_heading``, ``inside_band``, ``none_of``,
    ``concentrated``, ``others`` e a palavra do eixo, que é a que ele deu na `OD-153`.

    ## Duas orações, porque ele escreveu duas coisas diferentes

    A frase dele (`docs/exemplos-analise-dimensional.md`, linhas 140-141) separa as duas com um
    ponto-e-vírgula, e a diferença é medida e não estilística: a primeira oração diz que **houve**
    concentração e que o resto ficou fora dela; a segunda diz que **não houve** nenhuma. Um eixo
    onde nada deixou a própria banda não tem um resto — não tem nada, e a palavra do resto seria
    falsa ali.

    **Nenhuma das duas orações é citada nesta docstring**, e isso não é timidez: `T1334` acendeu
    aqui na primeira escrita, porque uma delas ficou copiada em prosa. Um exemplo dentro do pacote
    é uma cópia da palavra dele que envelhece sozinha, e é exactamente o que o nó vigia.

    **Um eixo sem parte medida não produz oração nenhuma.** Silêncio aqui não é uma terceira
    resposta: é a ausência de medição, e a peça 6 só fala do que foi medido. O eixo que este
    repositório declara INDISPONÍVEL nunca chega a esta função — o relatório já o nomeia com a
    frase governada do `FR-1316`, e as duas afirmações são opostas.
    """
    if not for_alert or not discarded:
        return []
    clauses: list[str] = []
    for one in discarded:
        #: **A recusa mora AQUI e não no chamador**, e é a diferença entre uma garantia e uma
        #: convenção. O chamador de hoje só constrói entradas para eixos permitidos, e isso é
        #: verdade e é frágil: nada o obriga a continuar assim, e um chamador futuro que não
        #: saiba desta regra afirmaria cobertura sobre um eixo que este repositório declara não
        #: conseguir medir — a leitura oposta à que a peça 6 existe para dar.
        refuse_unavailable_coverage(one, breakdowns_governance)
        if not one.inside and one.concentrated:
            continue
        word = (
            governance.plural_for(one.column)
            if one.concentrated
            else governance.singular_for(one.column) or governance.plural_for(one.column)
        )
        clauses.append(
            f"{governance.others} {word} {governance.inside_band}"
            if one.concentrated
            else f"{governance.none_of} {word} {governance.concentrated}"
        )
    if not clauses:
        return []
    return [f"{governance.discarded_heading}: {'; '.join(clauses)}."]


def _worth_naming(pull: Pull) -> bool:
    """`OD-143` (a): a movement of ONE unit is not a puller.

    His words on the real block: fourteen of its thirty-seven lines were a part that went from
    one to two. **A deviation of a single unit explains nothing and costs a whole line**, and
    fourteen of them is what made the twenty-three that meant something unreadable.

    **Only where a unit is a whole thing.** The filter reads the source's own `format_type` and
    applies only to the formats `WHOLE_FORMATS` names, because one unit of a COUNT is one trial
    and one unit of a RATE is a whole percentage point — which on his own alert is a larger
    move than anything the daily has ever shown. A rate's parts are untouched by this, and that
    is a decision recorded rather than a case nobody thought of.
    """
    return not (pull.format_type in WHOLE_FORMATS and abs(pull.deviation) <= 1)


def _pull_groups(
    pulls: Sequence[Pull], icons: BreakdownGovernance | None = None
) -> list[tuple[tuple[str, str], list[Pull]]]:
    """The pulls as `(indicator, axis)` groups, each ranked by MAGNITUDE — `OD-142`, `OD-143`.

    **Sorted by how much it moved, and it was sorted by name.** That is the whole of his
    second complaint: a list ordered alphabetically puts the largest mover wherever its
    country's spelling lands it, so the reader has to read all thirty-seven to find the one
    that matters. The tie-break is the value's own name, which keeps the order stable between
    two runs of one day rather than deciding anything.

    The GROUP order is derived twice over: indicators in the order the caller produced them,
    and axes in the order his governed file declares them. A column his file does not declare
    keeps the order it arrived in, which is the same answer `sections_from` gives an unlisted
    section.
    """
    declared = list(icons.columns) if icons is not None else []
    grouped: dict[tuple[str, str], list[Pull]] = {}
    for pull in pulls:
        if not _worth_naming(pull):
            continue
        grouped.setdefault((pull.kpi_label, pull.column), []).append(pull)
    kpi_order = list(dict.fromkeys(pull.kpi_label for pull in pulls))
    column_order = list(dict.fromkeys([*declared, *(pull.column for pull in pulls)]))
    ordered = sorted(
        grouped.items(),
        key=lambda entry: (kpi_order.index(entry[0][0]), column_order.index(entry[0][1])),
    )
    for _key, group in ordered:
        group.sort(key=lambda pull: (-abs(pull.deviation), pull.value))
    return ordered


def _group_lines(
    kpi: str,
    column: str,
    group: Sequence[Pull],
    governance: ContributionGovernance,
    icons: BreakdownGovernance | None = None,
) -> list[str]:
    """One group: its heading, the largest few, and what was left behind.

    ## The flag is all of them or none of them — `OD-143` (b)

    His words are about what the block LOOKED like: `🇧🇷 Brazil` two lines above a bare
    `Mongolia`, because the governed icon map names the first and not the second. Half a column
    of flags reads as a defect in the message rather than as an absence in a map.

    So the icons are decided **per group**: every value in it has one, or none of them is
    drawn. Nothing is derived from a name and no placeholder stands in for a missing entry —
    the `S-44` refusal is untouched, and what changed is only whether the entries that DO exist
    are used in a group where some do not.

    **This diverges from the breakdown block four lines above it**, which still draws the icons
    it has beside the names it does not. That is a real inconsistency and it is his order:
    `OD-143` names this block. It is recorded here rather than resolved by extending the rule
    to a block he did not mention.
    """
    axis = dict(icons.axis_labels).get(column, "") if icons is not None else ""
    out = [f"{kpi} · {axis}".strip() if axis else kpi]
    #: The cut and the tail both need words his governed file holds. A caller that supplied no
    #: breakdown governance gets every puller and no tail line: a truncation nobody can name is
    #: the shape `SC-1304` refuses, and inventing the word here is what this module never does.
    top = list(group) if icons is None else list(group[: governance.top_n])
    rest = [] if icons is None else list(group[governance.top_n :])
    #: **Decided over what is DRAWN, not over what was measured.** His complaint is about the
    #: column he sees: a flag two rows above a bare name. A value that fell into the counted
    #: tail is on no row of its own, so its absence from the map cannot make the rows above it
    #: look broken.
    lettered = (
        icons is not None and bool(top) and all(icons.icon_for(column, pull.value) for pull in top)
    )
    out.extend(_pull_text(pull, governance, icons if lettered else None, column) for pull in top)
    if rest and icons is not None:
        left = sum((pull.deviation for pull in rest), Decimal(0))
        #: `OD-153`: the word agrees with the count this line prints. A group cuts at his
        #: `top_n` and can leave exactly one part behind, which used to be named with the word
        #: for many because the governed file carried no other.
        out.append(
            f"{icons.tail_label} {len(rest)} {icons.noun_for(column, len(rest))}: "
            f"{_signed(left, rest[0].format_type)}"
        )
    return out


def _signed(value: Decimal, format_type: str = "") -> str:
    """A movement with its SIGN in front of it — `OD-143` (c).

    The block printed `2 → 13` and asked him to do the subtraction himself, on every line, in a
    list thirty-seven long. **The number he wants is the difference**, and the arrow's two terms
    were the two numbers his own indicator line already carries one level up.

    The `+` is written because a bare `11` beside a `-5` does not read as a pair; the `-` comes
    from the number itself. Neither is a word.
    """
    shown = _number(value, format_type)
    return f"+{shown}" if value > 0 else shown


def _pull_text(
    pull: Pull,
    governance: ContributionGovernance,
    icons: BreakdownGovernance | None = None,
    column: str = "",
) -> str:
    """One part's line: what it is, how much it moved, and how much of the day it explains.

    **The icon comes from the SAME governed map the breakdown reads**, and its absence was a
    measured defect that lived one day. `contribution.yaml` refused the flag because the source
    carries a country NAME and not an ISO code, so deriving one would be the hand-written table
    `S-4` forbids. True until `OD-119` put the hand-written map in `breakdown.yaml` the next day
    — his, dated, one entry per value. The refusal outlived its reason, and the same message
    rendered the flag in the breakdown and a bare name four lines below it.

    Whether the icons are drawn at all is `_group_lines`' decision — `OD-143` (b) — and this
    function is handed either the map or nothing. It derives no symbol either way.

    **The indicator's name is gone from the line** and that is `OD-142`: it stands once, at the
    head of the group, instead of once per line under a heading that named neither.
    """
    #: The share is a fraction and reaches the reader as a percentage. The approximation mark
    #: appears only when the shown figure is NOT the measured one — his contract carries it on
    #: a rounded share and not on an exact one, and no rounding rule of his was found, so this
    #: derives the mark from the rounding instead of applying it by taste.
    exact = pull.share * 100
    shown = exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    mark = "" if shown == exact else governance.approximately
    #: The per-cent sign is READ from the governed unit set, never written here: it is the
    #: fourth vocabulary `ADR 0036` names, and typing it would be this module authoring a mark.
    per_cent = value_unit_for(RATE_FORMAT)
    weight = f"{mark}{_shown(shown, Decimal('1'))} {per_cent} {governance.deviation_noun}"
    compensation = (
        f" {governance.dash} {governance.others} {governance.plural_for(pull.column)} "
        f"{governance.compensated}"
        if pull.others_compensated
        else ""
    )
    named = pull.value
    if icons is not None:
        named = f"{icons.icon_for(column or pull.column, pull.value)} {pull.value}".strip()
    return f"{named} {_signed(pull.deviation, pull.format_type)} ({weight}{compensation})"


#: How many decimal places a number reaches the reader with. **Two, and it is a decision
#: about legibility rather than about precision**: the arithmetic stays exact in `Decimal`
#: all the way here, and only the last step rounds.
#:
#: This exists because composing the report against the real warehouse on 2026-08-28
#: produced lines like `New trials: 3963.00 (-5.236728837876614060258249641
#: relative_percent)`. The value had been rounded by the caller and the variation had not,
#: so a number nobody can read was sitting next to one anybody can. **A ratio of two
#: Decimals carries twenty-eight significant digits and none of them is a measurement** --
#: the source has three.
DISPLAYED_PLACES: Final = Decimal("0.01")


def _shown(number: Decimal, places: Decimal = DISPLAYED_PLACES) -> str:
    """``number`` at the displayed precision, rounded once and at the very end.

    Written the way the reader reads numbers: thousands separated by a dot and the decimals
    by a comma. **That is a fact about his locale, not a sentence** — no word is authored
    here, and the rounding still happens exactly once, at the end.
    """
    #: The grouping spec carries no letter ON PURPOSE. `test_only_his_words_are_authored_here`
    #: flags any string constant with a letter in it, and `,f` tripped it -- correctly, by its
    #: own rule. **The guard was not loosened to fit this**: the format spec lost the letter.
    fixed = f"{number.quantize(places, rounding=ROUND_HALF_UP):,}"
    return fixed.translate(str.maketrans({",": ".", ".": ","}))


def _places_for(format_type: str) -> Decimal:
    """How many decimals this KPI's VALUE reaches the reader with."""
    return Decimal("1") if format_type in WHOLE_FORMATS else DISPLAYED_PLACES


#: `dd/mm/yyyy` is ten characters, and each number column has to be at least that wide or the
#: date row slides out from under the numbers it labels.
_DATE_WIDTH: Final = 10


def _number(value: Decimal | None, format_type: str = "") -> str:
    """One figure as the reader sees it, **carrying its own unit** — or the mark for absence.

    `OD-42`, and he found it in one glance: *"0,01 / nao era para ter %?"*. Until then only
    the VARIATION carried a unit, so one column held `644` which is a count, `0,24` which is a
    rate and `46.860,55` which is money, **and the three looked alike**. The KPI's label says
    `(%)` or `(US$)`, but it sits at the far left, columns away from its own number.

    **The unit is DERIVED from the source's `format_type`**, exactly as the number of decimal
    places is, and never chosen line by line.
    """
    if value is None:
        return "-"
    shown = _shown(value, _places_for(format_type))
    unit = value_unit_for(format_type)
    return f"{shown} {unit}" if unit else shown


#: What stands where a mark would, when there is none. Two spaces, because a coloured circle
#: renders about two cells wide: the label column stays put instead of the whole line sliding
#: left on the rows that carry no comparison.
_UNMARKED: Final = "  "


def mark_for(variation: Decimal | None, lower_is_better: bool | None) -> str:
    """The coloured mark for one movement — `OD-34`, and **the colour is derived**.

    Green when the movement goes the way the SOURCE says is good, red when it goes the other
    way, yellow when it is exactly zero, and **nothing when there is no comparison or when
    the source does not say which way is good**. An absence already prints its dash; a colour
    over an unknown is an opinion dressed as a measurement.

    ``lower_is_better`` comes from the metric's own contract — it lived in the view's column
    until `D-1303` on 2026-09-04. **No KPI is named here**, which is the difference between
    reading a declaration and writing a table of opinions.
    """
    if variation is None or lower_is_better is None:
        return ""
    if variation == 0:
        return UNMOVED
    rose = variation > 0
    return MOVED_BADLY if rose == lower_is_better else MOVED_WELL


#: How far the second currency's block sits in from the first — `OD-150`. Two spaces, and it
#: carries no letter, so it is not a word anybody authored. It is the ONE piece of alignment
#: left in the message and it aligns nothing: it marks a block as belonging to the one above
#: it, which a proportional font renders as an indent of whatever width it likes without the
#: meaning moving. That is the difference from the columns `OD-44` refused.
_NESTED: Final = "  "


def _indicator_lines(
    line: Line,
    label_style: Callable[[str], str] = _plain,
    reference_label: str = "",
    reference_against: str = "",
    reference_was: str = "",
    *,
    snapshot_mark: str = "",
) -> list[str]:
    """One KPI as a BLOCK: the mark and the label, then one named row per number — `OD-147`.

    ## The defect, in his own reading

    The line closed as `736 · 695 · +5,90 % · +12,54 %` with a bracketed `654` after it.
    **Four numbers and none of them said what it was.** Position carried all of the meaning —
    first is yesterday, second is the day before — which is exactly the thing a reader cannot
    verify, and the header's one sentence had to rescue twenty lines.

    He chose this shape from a preview built with his own numbers: the mark and the label on
    one row, then `736`, `695`, `+5,90 %` and `+12,54 %` each on a row that opens with the word
    naming it — two of those words are his own day words and the rest arrive governed. **No
    word of the shape is quoted in this docstring**, and that is a node rather than a habit:
    `test_the_words_are_written_in_no_python_file_of_this_package` refuses a governed word
    written anywhere in this package, docstrings included.

    ## Three of its decisions are NOT cosmetic

    * **The reference's bracketed number gains a WORD in front of it** — `OD-147`. It used to
      be a bare figure in brackets at the end of a line already carrying three others; the word
      is what says the bracket holds the OLD number rather than an annotation, and it is
      governed (`report_governance/references.yaml`) because it has a letter in it.
    * **`pp` stays where it is `pp` and `%` where it is `%`.** `Trial conversion` moved
      `-5,65` **percentage points**, not `-5,65 %`, and the two are different quantities. The
      unit is `VariationUnit`, derived from the source's `format_type` by `OD-20-C`, and
      nothing in this shape touches it.
    * **He refused monospace again.** The docstring of :func:`render` records *"ESQUECE ESSA
      IDEIA DE MONOESPACO"* from `OD-44`, and this shape needs no font: every row names itself,
      so nothing has to line up under anything.

    ## `OD-148`: the mark stays a bare symbol

    A word beside 🟢/🔴 was offered and refused — *"verde e vermelho já se leem sozinhos"*.
    Nothing is appended to the mark, and this note is here so the next reader does not read the
    bare circle as an unfinished sentence.
    """
    #: `OD-148`: the mark opens the block and stays a symbol. `OD-36` put it first so a reader
    #: takes the list top to bottom and sees what got worse before reading a number, and with a
    #: block per indicator that matters more than it did on a single line.
    opening = mark_for(line.variation, line.lower_is_better)
    head = f"{opening} " if opening else ""
    footnote = " *" if line.footnoted else ""
    #: **The label lost its colon with the numbers it used to introduce** — `OD-48` had asked
    #: for *"o nome do kpi incluindo : em negrito"* when the label opened a line that continued
    #: into four numbers. It now opens a block, and the colon that pointed at them points at a
    #: line break. The MARK is still not written here: markup belongs to whatever carries the
    #: message, which is why `label_style` exists.
    out = [f"{head}{label_style(line.label)}{footnote}"]
    out.append(f"{CLOSED_DAY_WORD}: {_number(line.value, line.format_type)}")
    out.append(f"{PREVIOUS_DAY_WORD}: {_number(line.previous_value, line.format_type)}")
    if line.variation is not None:
        out.append(f"{VARIATION_WORD}: {_signed_variation(line.variation)} {line.unit.value}")

    #: The SECOND reference — `FR-1306`, `SC-1305`. Same grammar as the row above it: the word
    #: that names what the comparison is against, then the movement, then the other term in
    #: parentheses so the reader can check the arithmetic. **The two words arrive as governed
    #: data** (`report_governance/references.yaml`) for the reason the breakdown's labels do:
    #: `D-7` carries a letter, and a letter with no named vocabulary is refused.
    #:
    #: Printed only when BOTH the variation and the value exist. A movement whose other term is
    #: invisible is the `OD-31` complaint, and a reference against a day nobody measured is
    #: worse than one reference.
    if (
        line.week_ago_variation is not None
        and line.week_ago_value is not None
        and reference_label
        and reference_against
    ):
        #: `OD-147`: `(era 654)`. The word is optional in the governed file and its absence
        #: leaves the bare parentheses the line always had — never a word chosen here.
        was = f"{reference_was} " if reference_was else ""
        out.append(
            f"{reference_against} {reference_label}:"
            f" {_signed_variation(line.week_ago_variation)} {line.unit.value}"
            f" ({was}{_number(line.week_ago_value, line.format_type)})"
        )

    #: `OD-71` gave the KPI a second currency and `OD-150` gave it a block — 2026-09-06, after
    #: he read `MRR` as **nine numbers on one line in two currencies**. He refused both of the
    #: cheap repairs: putting BRL back on one line loses the `D-7` comparison in reais, and
    #: dropping BRL from the alert *"apaga um número que hoje está lá"* — which is losing
    #: information rather than losing lines.
    #:
    #: So the second currency repeats the FIRST block's grammar, indented and fenced. **The two
    #: variations are genuinely different numbers**: measured 2026-08-31 on the real series,
    #: Revenue moved +29,04 % in USD and +3,64 % in BRL between the same two days, because the
    #: embedded rate moved. One variation beside two currencies would describe neither.
    #:
    #: There is no `D-7` row in reais because nobody measured one: the caller reads a BRL pair
    #: from the same view line, and a third BRL number does not exist. An absent reference is
    #: said by being absent, which is the rule the USD row above already follows.
    if line.brl_value is not None or line.brl_previous is not None:
        out.append("")
        out.append(f"{_NESTED}{IN_BRL_WORD}")
        out.append(f"{_NESTED}{CLOSED_DAY_WORD}: {_number(line.brl_value, line.brl_format)}")
        out.append(f"{_NESTED}{PREVIOUS_DAY_WORD}: {_number(line.brl_previous, line.brl_format)}")
        if line.brl_variation is not None:
            out.append(
                f"{_NESTED}{VARIATION_WORD}: {_signed_variation(line.brl_variation)}"
                f" {VariationUnit.RELATIVE_PERCENT.value}"
            )
        out.append("")

    #: **`OD-151`: the threshold is a LINE with a word, and his reasoning is why.**
    #:
    #: It was `(0,40 % · 90 d)` trailing the numbers — the shape `OD-49` had already diagnosed
    #: as *a column somebody forgot to remove*. His point is that **the threshold is the REASON
    #: the indicator is in the alert at all**: it is the first-class fact of this product, not a
    #: footnote on it. So it gets its own row and a word that names it.
    #:
    #: `OD-43` still holds underneath: the PRESENCE of this row is what tells the two products
    #: apart on screen, and a report line never carries it. The `90` wears his `d`
    #: (`DAY_COUNT_WORD`, chosen 2026-08-31) and `OVER_PERIOD_WORD` binds the two.
    if line.threshold is not None and line.series_periods is not None:
        out.append(
            f"{THRESHOLD_LABEL}: {_shown(line.threshold)} {line.unit.value}"
            f" {OVER_PERIOD_WORD} {line.series_periods} {DAY_COUNT_WORD}"
        )

    #: `SC-1306` — the level says it is one, and since `OD-151` **on a line of its own**: he
    #: refused merging it into one trailing line with the threshold, because they answer
    #: different questions. One says why this indicator is here; the other says what kind of
    #: number the figures above are.
    #:
    #: Silent when the caller supplies no phrase, which is not a default standing in for a
    #: decision: the daily's three indicators (`FR-1319`) are all accumulations, so nothing is
    #: marked there, and a caller that renders levels without loading the governed file gets no
    #: invented word — the same refusal the second reference makes when its two words are absent.
    if line.is_snapshot and snapshot_mark:
        out.append(snapshot_mark)
    return out


def _signed_variation(variation: Decimal) -> str:
    """A movement at the displayed precision, with its `+` written and its `-` its own.

    The variation keeps two decimals whatever the KPI counts, because it is a fraction and not
    a count of things. Neither sign is a word.
    """
    shown = _shown(variation)
    return f"+{shown}" if variation > 0 else shown


#: **The three-space indent is gone, and so is the reason it existed** — `OD-119`, `S-45`.
#:
#: It said a dash "would be a character nobody decided", which was true until he decided it.
#: He read the inline form on his phone on 2026-09-04 and called it unreadable; the markers he
#: chose live in the governed file beside his words, one for an axis and two for a value, and
#: this module positions them without owning them.
#:
#: The space AFTER a marker is not decoration. Measured against `_words_in`: a marker separated
#: by a space is dropped for carrying no letter, and a marker glued to a value forms the token
#: `-Brazil`, which matches nothing in the vocabulary and the message is refused for
#: `origination_wording_not_his`.


def _breakdown_lines(
    breakdown: Breakdown,
    governance: BreakdownGovernance,
    format_type: str = "",
) -> list[str]:
    """One breakdown, as the LINES a person reads — `FR-1303`, `SC-1304`, `OD-119`.

    Every WORD in the result came from somewhere that is not this module: the axis label, the
    tail label, the tail noun, the two markers and the icons are read from the governed file,
    and the values are the source's own. What this function contributes is order.

    **One value per line, and the shape is his.** It used to be one line — label, colon, and
    the values joined by a separator — and he read it on a phone on 2026-09-04: *"ficou um
    lixo... extremamente dificil de ler"*. Six of those under three indicators wrapped three
    and four times each on a narrow screen, so the eye had no column to follow.

    The tail keeps BOTH of its numbers and its noun on a line of its own, for the reason
    `Breakdown` carries both: one without the other is a half-truth that reads like a whole
    one, and the noun fell out once (`S-44`) because the origination gate would have refused a
    word nobody governed — so the word was dropped instead of being governed.
    """
    axis = f"{governance.axis_marker} {breakdown.label}".strip()
    out = [axis]
    #: `F5` (`FR-1316`): an axis his file declares unavailable is SAID, never skipped. The
    #: sentence is governed data the caller rendered from the reason-message registry; this
    #: function contributes the marker and nothing else. No value line and no tail follow.
    if breakdown.is_unavailable:
        out.append(f"{governance.value_marker} {breakdown.reason}".strip())
        return out
    for value, number in breakdown.lines:
        icon = governance.icon_for(breakdown.column, value)
        named = f"{icon} {value}".strip()
        out.append(f"{governance.value_marker} {named} {_number(number, format_type)}".strip())
    #: **`OD-144` (2026-09-06): the tail of a RATE is two lines, because it was two
    #: populations.**
    #:
    #: One line used to carry the parts that did not fit the cut AND the parts the sample floor
    #: withheld. The number was arithmetically honest — the tail is aggregated, not summed — and
    #: it was unreadable: on the real message `Australia 0,00 %` ranked visibly above a tail
    #: reading `4,47 %`, and nothing on screen said the tail held partitions whose rate is
    #: deliberately not asserted.
    #:
    #: The shape he chose is two lines where one stood: the first keeps the tail's count and
    #: its aggregate and gains a qualifier saying the parts in it HAVE a sample; the second
    #: counts the withheld and puts his phrase where a rate would be. **Every word of both is
    #: in `report_governance/breakdown.yaml`** and none is quoted here — a governed word
    #: written into this package is what `test_the_words_are_written_in_no_python_file_of_this_
    #: package` refuses, docstrings included.
    #:
    #: **The withheld stay IN**, counted. He refused dropping them, because that contradicts
    #: the reconciliation he approved: `len(lines) + tail_count + withheld_count` is still every
    #: partition the axis had. What they do not get is a number, which is precisely what
    #: `SC-1301`'s floor decided about them.
    #:
    #: **A count's breakdown is untouched.** It has no floor to withhold anything, so it has
    #: one population and keeps the one line it always had — a qualifier distinguishing it from
    #: nothing would be noise. The qualifier is also silent when his file does not state the
    #: three words, which is the declared absence and not a default.
    #: **`OD-153` (2026-09-06): each line asks for the word its OWN count needs.**
    #:
    #: The two lines carry two different counts, and one noun computed once for both of them
    #: was already a latent disagreement — the day one of the populations holds a single
    #: partition and the other does not, the same word would stand over both numbers. So the
    #: word is asked for per line, from the count that line prints.
    #:
    #: The message he read said one partition in the word for many, on both halves. That was a
    #: defect of AGREEMENT and not of invention: the governed file carried exactly one word per
    #: axis, so a count of one had nothing else to reach for. He supplied the missing words and
    #: `noun_for` is what spends them; **not one of them is written here**.
    split = breakdown.has_withheld and governance.splits_the_tail
    if breakdown.has_tail:
        qualifier = f" {governance.sampled_qualifier}" if split else ""
        #: Only the split tail borrows the axis's own word. A count's tail has no floor and no
        #: second population, so it keeps the generic noun and the one line it always had —
        #: `OD-144` scoped that and `OD-153` does not widen it.
        cut = (
            governance.noun_for(breakdown.column, breakdown.tail_count)
            if split
            else governance.tail_noun
        )
        out.append(
            f"{governance.value_marker} {governance.tail_label} {breakdown.tail_count} "
            f"{cut}{qualifier}: {_number(breakdown.tail_total, format_type)}".strip()
        )
    if split:
        withheld = governance.noun_for(breakdown.column, breakdown.withheld_count)
        out.append(
            f"{governance.value_marker} {breakdown.withheld_count} {withheld} "
            f"{governance.withheld_label}: {governance.withheld_value}".strip()
        )
    return out
