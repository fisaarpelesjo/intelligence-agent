"""Persistência: quantos dias seguidos fora da banda — `T1334`, peça 1 do contrato aprovado.

*"Severidade e persistência no título — separa acidente de tendência"*
(`docs/exemplos-analise-dimensional.md`, linha 148). Um desvio de um dia e um desvio de três lêem-se
de maneira diferente, e até aqui o alerta não sabia dizer qual era qual.

## O que este ficheiro afirma, e o que deliberadamente não afirma

Afirma a CONTAGEM, que é aritmética sobre a série já carregada. Não afirma o título — a frase que
o leitor vê é vocabulário dele e entra pela governança, como toda a outra.

**E afirma que a régua é uma só.** `evaluate` e `days_outside_the_band` perguntam a mesma coisa a
dias diferentes; escrita duas vezes, uma delas envelhece sozinha, e a que envelhece é a que ninguém
corre em produção todos os dias.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from daily_reporting.alert.rule import days_outside_the_band, evaluate, outside_the_band

BAND = Decimal(10)


def test_a_day_inside_the_band_has_no_persistence_to_count() -> None:
    """Zero é a RESPOSTA e não a ausência dela: não houve desvio de que contar dias."""
    assert days_outside_the_band([Decimal(50), Decimal(50)], Decimal(1), BAND) == 0


def test_one_day_out_after_a_calm_run_counts_one() -> None:
    """O acidente: saiu hoje, e ontem estava dentro."""
    assert days_outside_the_band([Decimal(1), Decimal(2), Decimal(3)], Decimal(50), BAND) == 1


def test_three_days_out_in_a_row_count_three() -> None:
    """A tendência — o caso do exemplo dele, e o que a peça 1 existe para separar do acidente."""
    history = [Decimal(1), Decimal(2), Decimal(40), Decimal(45)]
    assert days_outside_the_band(history, Decimal(50), BAND) == 3


def test_the_run_stops_at_the_first_day_back_inside() -> None:
    """Seguidos quer dizer seguidos: um dia dentro corta a série, mesmo com desvios atrás dele."""
    history = [Decimal(99), Decimal(99), Decimal(1), Decimal(40)]
    assert days_outside_the_band(history, Decimal(50), BAND) == 2


def test_a_movement_of_exactly_zero_never_counts() -> None:
    """A regra do zero vale para os dias anteriores como vale para o de hoje.

    `Semiannual (%)` é zero em 61.038 das suas 61.041 linhas, logo o seu próprio `p90` é zero.
    Sem esta cláusula, um limiar de zero faria dele uma persistência de noventa dias sobre uma
    métrica que nunca se mexeu.
    """
    assert not outside_the_band(Decimal(0), Decimal(0))
    assert days_outside_the_band([Decimal(0), Decimal(0)], Decimal(0), Decimal(0)) == 0


def test_a_movement_exactly_on_the_threshold_is_out() -> None:
    """A fronteira é a do `evaluate`, e é `>=` — medida, não escolhida aqui."""
    assert outside_the_band(BAND, BAND)
    assert days_outside_the_band([BAND], BAND, BAND) == 2


def test_the_whole_history_can_be_the_run() -> None:
    """Sem nenhum dia dentro, a contagem é a série inteira mais o dia fechado."""
    assert days_outside_the_band([Decimal(50)] * 4, Decimal(50), BAND) == 5


def test_an_empty_history_counts_only_the_closed_day() -> None:
    """Primeiro dia de série: um dia fora é um dia fora, e não zero nem erro."""
    assert days_outside_the_band([], Decimal(50), BAND) == 1


def test_the_two_readings_share_one_ruler() -> None:
    """**A propriedade que mantém as duas honestas.**

    Se `evaluate` diz que o dia fechado cruzou, a contagem tem de ser pelo menos 1; se diz que
    não, tem de ser 0. Duas réguas dariam um título a falar de persistência num dia que o alerta
    não considerou desvio nenhum.
    """
    history = [Decimal(1), Decimal(2), Decimal(3), Decimal(4)]
    for latest in (Decimal(0), Decimal(1), Decimal(10), Decimal(50), Decimal(-50)):
        crossing = evaluate(
            "x", "int", history, latest, comparable_periods_across_kpis=[len(history)]
        )
        days = days_outside_the_band(history, latest, BAND)
        if crossing is None:
            assert days == 0, (latest, days)
        else:
            assert days >= 1, (latest, days)


def test_the_count_reads_the_series_and_holds_no_state() -> None:
    """Duas chamadas iguais dão o mesmo, e nada fora dos argumentos entra na conta.

    Um contador persistido mentiria no dia em que uma corrida falhasse — e este repositório já
    teve duas que não chegaram ao fim.
    """
    history = [Decimal(40), Decimal(45)]
    primeiro = days_outside_the_band(history, Decimal(50), BAND)
    segundo = days_outside_the_band(history, Decimal(50), BAND)
    assert primeiro == segundo == 3
    assert history == [Decimal(40), Decimal(45)]


@pytest.mark.parametrize("threshold", [Decimal(1), Decimal(10), Decimal(100)])
def test_the_band_that_counts_is_the_one_handed_in(threshold: Decimal) -> None:
    """A banda é a que o alerta imprime, não uma re-derivada por dia.

    Re-derivar responderia a outra pergunta — *cada dia foi anormal para a sua própria
    história?* — e daria um número que ninguém confere contra a banda escrita ao lado.
    """
    history = [Decimal(50), Decimal(50)]
    esperado = 3 if threshold <= Decimal(50) else 0
    assert days_outside_the_band(history, Decimal(50), threshold) == esperado
