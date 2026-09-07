"""The report over the two products' entry point — `T807`, `T817`, `T822`.

**A measured zero is a fact about the business, and omitting it hides one.**
`Semiannual (%)` holds 60.641 zero rows of 60.644 and is reported as zero with the
footnote — `FR-815`, `OD-14-G`, and his own words for the choice.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from daily_reporting.contracts import ReportReasonCode, ReportRefusal
from daily_reporting.numbers.variation import RATE_FORMAT, VariationUnit
from daily_reporting.report.summary import Reading, render, summarise
from daily_reporting.report.template import (
    CLOSED_DAY_WORD,
    PREVIOUS_DAY_WORD,
    SHORT_OR_EMPTY_SOURCE,
)
from daily_reporting.view.shape import ViewRow

pytestmark = pytest.mark.unit

AN_INSTANT = datetime(2026, 8, 28, 3, 5, tzinfo=UTC)
A_CLOSED_DAY = date(2026, 8, 27)

ROWS: tuple[ViewRow, ...] = (
    {"section_name": "alpha", "kpi_name": "a_rate"},
    {"section_name": "alpha", "kpi_name": "a_volume"},
    {"section_name": "beta", "kpi_name": "a_short_one"},
    {"section_name": "beta", "kpi_name": "an_unmeasured_one"},
)

READINGS = {
    "a_rate": Reading(
        format_type=RATE_FORMAT,
        value=Decimal("0.0"),
        previous_period=Decimal("0.0"),
        current_period=Decimal("0.0"),
        series_is_short=False,
    ),
    "a_volume": Reading(
        format_type="qty",
        value=Decimal("600"),
        previous_period=Decimal("500"),
        current_period=Decimal("600"),
        series_is_short=False,
    ),
    "a_short_one": Reading(
        format_type="qty",
        value=Decimal("11"),
        previous_period=Decimal("10"),
        current_period=Decimal("11"),
        series_is_short=True,
    ),
}


def _summary():
    return summarise(ROWS, READINGS, day=A_CLOSED_DAY, instant=AN_INSTANT)


def test_every_kpi_the_view_declares_reaches_the_page() -> None:
    """Including the one no reading covered. `SC-801`.

    **This measures the RENDERER, over the rows of this fixture** — it says nothing about which
    KPIs reach the 08:00 daily, which is the caller's governed decision since `T1329`
    (`report_governance/daily_scope.yaml`); the node for that is
    `tests/unit/test_the_daily_carries_only_the_three_indicators.py`.
    """
    carried = {line.label for _, lines in _summary().sections for line in lines}
    assert carried == {str(row["kpi_name"]) for row in ROWS}


def test_a_measured_zero_is_reported_as_zero_and_never_omitted() -> None:
    """`FR-815`. **The zero is verdade medida, not a failure.**"""
    line = next(
        line for _, lines in _summary().sections for line in lines if line.label == "a_rate"
    )
    assert line.value == Decimal("0.0")
    assert line.variation == Decimal("0.0")
    assert line.unit is VariationUnit.PERCENTAGE_POINTS


def test_the_short_series_and_the_unmeasured_one_carry_the_footnote() -> None:
    """And they are still on the page — the alert is what a short series loses."""
    marked = {line.label for _, lines in _summary().sections for line in lines if line.footnoted}
    assert marked == {"a_short_one", "an_unmeasured_one"}


def test_a_volume_moves_in_relative_percent_and_a_rate_in_points() -> None:
    lines = {line.label: line for _, lines in _summary().sections for line in lines}
    assert lines["a_volume"].unit is VariationUnit.RELATIVE_PERCENT
    assert lines["a_volume"].variation == Decimal("20")
    assert lines["a_rate"].unit is VariationUnit.PERCENTAGE_POINTS


def test_the_sections_keep_the_views_order() -> None:
    assert [name for name, _ in _summary().sections] == ["alpha", "beta"]


def test_the_report_refuses_the_day_still_in_progress() -> None:
    """`FR-802`. It speaks of the closed day, and the source's window ends yesterday."""
    with pytest.raises(ReportRefusal) as refused:
        summarise(ROWS, READINGS, day=date(2026, 8, 28), instant=AN_INSTANT)
    assert refused.value.code is ReportReasonCode.REPORT_DAY_NOT_CLOSED


def test_the_rendering_is_his_two_words_the_date_and_the_labels() -> None:
    """No sentence anywhere: a header, section names, and label-and-value lines.

    **RE-DERIVADO em 2026-08-30 pelo `OD-33-B`**: a data sai `dd/mm/yyyy` e nao ISO. O que
    este no mede -- que o cabecalho e a palavra dele mais a data, e nada mais -- nao mudou;
    mudou como a data e escrita, que e fato do local dele.
    """
    text = render(_summary())
    head = text.splitlines()[0]
    assert head.startswith(f"{CLOSED_DAY_WORD} "), head
    assert head == f"{CLOSED_DAY_WORD} 27/08/2026", head
    assert SHORT_OR_EMPTY_SOURCE in text
    for row in ROWS:
        assert str(row["kpi_name"]) in text


def test_a_report_with_nothing_short_carries_no_footnote_line() -> None:
    """The footnote appears because something needed it, never as decoration."""
    complete = {
        "a_rate": READINGS["a_rate"],
        "a_volume": READINGS["a_volume"],
    }
    rows = ROWS[:2]
    text = render(summarise(rows, complete, day=A_CLOSED_DAY, instant=AN_INSTANT))
    assert SHORT_OR_EMPTY_SOURCE not in text


def test_the_variation_reaches_the_reader_rounded_like_the_value() -> None:
    """**Found by composing the report against the real warehouse on 2026-08-28.**

    The value was rounded by the caller and the variation was not, so a line came out as
    `New trials: 3963.00 (-5.236728837876614060258249641 relative_percent)` -- a number
    nobody can read sitting next to one anybody can. **A ratio of two `Decimal`s carries
    twenty-eight significant digits and none of them is a measurement.**

    The arithmetic stays exact all the way to here; only the last step rounds.
    """
    rows: tuple[ViewRow, ...] = ({"section_name": "s", "kpi_name": "k"},)
    readings = {
        "k": Reading(
            format_type="qty",
            value=Decimal("3963"),
            previous_period=Decimal("4182"),
            current_period=Decimal("3963"),
            series_is_short=False,
        )
    }
    text = render(summarise(rows, readings, day=A_CLOSED_DAY, instant=AN_INSTANT))
    #: `OD-147` (2026-09-06): the indicator is a BLOCK of named rows, so what this node reads
    #: is the block. The property it measures is unchanged — the variation reaches the reader
    #: rounded exactly as the value is — and reading the whole block rather than one row keeps
    #: it from having to be edited again the next time the shape moves.
    printed = text.splitlines()
    start = next(i for i, row in enumerate(printed) if row.endswith("k"))
    end = next((i for i in range(start + 1, len(printed)) if printed[i] == ""), len(printed))
    line = chr(10).join(printed[start:end])
    #: The unit word is READ from the enum rather than transcribed: `OD-20-C` changed it
    #: from `relative_percent` to `%`, and a node carrying the old spelling would have gone
    #: red for the wording decision rather than for the rounding it measures.
    #:
    #: **RE-DERIVADO em 2026-08-30 pelo `OD-31` e pelo `OD-32`**, e o que este no mede nao
    #: mudou: a variacao chega ao leitor arredondada COMO O VALOR, uma casa a mais nunca. O
    #: que mudou foi a linha em volta -- os dois dias aparecem agora, e os numeros sao
    #: escritos como ele os le, milhar com ponto e decimal com virgula. Por isso a assercao
    #: passa a ser sobre O QUE ESTE NO MEDE em vez de sobre a linha inteira: uma assercao
    #: sobre a linha inteira reprova a cada mudanca de formatacao e ensina a edita-la.
    assert f"-5,24 {VariationUnit.RELATIVE_PERCENT.value}" in line, line
    assert "-5,236" not in line, line
    assert "3.963,00" in line, line


def test_a_long_ratio_would_fail_this_unrounded() -> None:
    """**Proof it bites**: the exact quotient, unrounded, is what the defect looked like."""
    exact = (Decimal("3963") - Decimal("4182")) / Decimal("4182") * Decimal(100)
    assert len(str(exact)) > 20, "the fixture no longer produces a long quotient"
    assert str(exact) not in render(
        summarise(
            ({"section_name": "s", "kpi_name": "k"},),
            {
                "k": Reading(
                    format_type="qty",
                    value=Decimal("3963"),
                    previous_period=Decimal("4182"),
                    current_period=Decimal("3963"),
                    series_is_short=False,
                )
            },
            day=A_CLOSED_DAY,
            instant=AN_INSTANT,
        )
    ), "the unrounded quotient reached the reader"


def test_the_value_is_the_day_and_the_variation_is_the_weeks() -> None:
    """**The defect the reviewer found in the message that would have gone to his chat.**

    The report opened with `ontem 2026-08-27` and the line read `New trials: 3957.00`.
    Measured against the view: 3957 is the week 21-27, and **yesterday was 515**. The
    arithmetic was right and the numbers were real to the second decimal; the LABEL was
    wrong, and a reader who sees *yesterday* over a weekly total reads a business that is
    almost eight times bigger than it is.

    `OD-14-E` made the COMPARISON weekly because the daily series is noisy. It did not make
    the VALUE weekly, and the form he approved shows a daily figure.
    """
    rows: tuple[ViewRow, ...] = ({"section_name": "s", "kpi_name": "k"},)
    readings = {
        "k": Reading(
            format_type="qty",
            value=Decimal("515"),
            previous_period=Decimal("4204"),
            current_period=Decimal("3957"),
            series_is_short=False,
        )
    }
    line = next(
        line
        for _, lines in summarise(rows, readings, day=A_CLOSED_DAY, instant=AN_INSTANT).sections
        for line in lines
    )
    assert line.value == Decimal("515"), "the day's value is not what reached the line"

    # Computed here from the same two weeks rather than transcribed: a 28-digit literal in
    # a node is the F136 bait this feature already caught once, and it would go stale on
    # any change to Decimal's context while asserting nothing about the property.
    expected = (Decimal("3957") - Decimal("4204")) / Decimal("4204") * Decimal(100)
    assert line.variation == expected, line.variation
    assert line.variation != Decimal(0), "the variation collapsed to nothing"


def test_where_the_two_periods_differ_both_are_named() -> None:
    """A comparison beside a daily value is **illegible** unless the report says which span
    each number covers. Dates, never words: naming a period in prose would be a third
    authored string.

    ## RE-DERIVADO em 2026-08-30 pelo `OD-31`, e o que mudou foi a DISPOSICAO

    A propriedade -- **os dois periodos aparecem, e por data** -- nao mudou uma virgula. O que
    mudou foi a ordem e o separador: o periodo ANTERIOR vem primeiro e o mais novo depois,
    porque o leitor le da esquerda para a direita e o tempo anda nesse sentido. Ele pediu
    *"ontem, antes de ontem, ai fica o comparativo"* e chamou a versao anterior de zoado.

    E um periodo de UM DIA aparece como UMA DATA em vez de `d..d`, que e a mesma data escrita
    duas vezes -- ruido, nao informacao. O caso de intervalo continua exercido abaixo.
    """
    rows: tuple[ViewRow, ...] = ({"section_name": "s", "kpi_name": "k"},)
    readings = {
        "k": Reading(
            format_type="qty",
            value=Decimal("515"),
            previous_period=Decimal("4204"),
            current_period=Decimal("3957"),
            series_is_short=False,
        )
    }
    periods = ((date(2026, 8, 21), A_CLOSED_DAY), (date(2026, 8, 14), date(2026, 8, 20)))
    text = render(summarise(rows, readings, day=A_CLOSED_DAY, instant=AN_INSTANT, periods=periods))
    head = text.splitlines()
    #: RE-DERIVADO em 2026-08-30 pelo `OD-33`: a data sai `dd/mm/yyyy`, o periodo MAIS NOVO
    #: vem primeiro -- a mesma ordem em que a linha mostra os dois numeros --, e cada um vem
    #: com a palavra dele, porque data nua nao desfaz uma inversao.
    #: RE-DERIVADO em 2026-08-30 pelo `OD-41`: as palavras rotulam as COLUNAS na primeira
    #: linha e as datas ficam SOB elas na segunda, e nenhuma das duas aparece duas vezes.
    #: RE-DERIVADO em 2026-08-30 pelo `OD-44`: as colunas sairam, entao as duas palavras e as
    #: duas datas voltam para UMA linha corrida, e o mais novo continua vindo primeiro -- a
    #: mesma ordem em que a linha do KPI apresenta os dois numeros.
    assert CLOSED_DAY_WORD in head[0] and PREVIOUS_DAY_WORD in head[0], head[0]
    assert "21/08/2026..27/08/2026" in head[0], head[0]
    assert "14/08/2026..20/08/2026" in head[0], head[0]
    assert head[0].index("14/08/2026") > head[0].index("21/08/2026"), head[0]

    #: E o caso que o `OD-31` trouxe: um dia contra o outro, cada periodo de UM dia, escrito
    #: como uma data e nao como `d..d`.
    um_dia = ((A_CLOSED_DAY, A_CLOSED_DAY), (date(2026, 8, 26), date(2026, 8, 26)))
    diario = render(
        summarise(rows, readings, day=A_CLOSED_DAY, instant=AN_INSTANT, periods=um_dia)
    ).splitlines()
    assert CLOSED_DAY_WORD in diario[0] and PREVIOUS_DAY_WORD in diario[0], diario[0]
    assert "27/08/2026" in diario[0] and "26/08/2026" in diario[0], diario[0]
    assert diario[0].index("26/08/2026") > diario[0].index("27/08/2026"), diario[0]


def test_a_report_with_no_variation_names_no_period_it_does_not_have() -> None:
    """The line is absent rather than empty: a period named over no comparison is a claim."""
    rows: tuple[ViewRow, ...] = ({"section_name": "s", "kpi_name": "k"},)
    readings = {
        "k": Reading(
            format_type="qty",
            value=Decimal("515"),
            previous_period=None,
            current_period=None,
            series_is_short=False,
        )
    }
    text = render(summarise(rows, readings, day=A_CLOSED_DAY, instant=AN_INSTANT))
    assert text.splitlines()[1] == "", text.splitlines()[:3]
