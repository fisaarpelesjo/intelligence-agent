"""The rule alert — one KPI, when it crosses its own `p90` — `T801`, `T818`.

## This module is not the report, and never calls it

`FR-801`, `OD-14-A`. The report says what the numbers are; this says that one of them
moved. **A reader who receives an alert learns something happened; a reader who
receives the report learns everything.** Merging them would make silence ambiguous.

## The level this belongs to, and the gap that is the owner's to close

This is `business_rules` — `docs/intelligence-agent.yaml` marks it `enabled: true`,
`priority: first`. The comparison it performs **is** named there: `previous_week`, with
`percentage_change` or `absolute_change`.

**The `p90` calibration is not.** `006`'s `score/components.py` reads its accepted
methods from `robust_statistics` only, and neither level lists a
percentile. So this module **emits no statistic**: it does not construct a
`MetricStatistics`, because there is no declared method it could name and inventing one
would be authoring his baseline for him. `specs/008-daily-report-and-rule-alerts/spec.md`
§ 10 records the two ways out and picks neither.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from ..numbers.variation import VariationUnit, variation_unit_for
from .threshold import (
    minimum_comparable_periods,
    refuse_unless_series_is_long_enough,
    threshold_from,
)

__all__ = ["Crossing", "evaluate"]


@dataclass(frozen=True, slots=True)
class Crossing:
    """One KPI whose latest movement passed its own threshold."""

    kpi: str
    movement: Decimal
    threshold: Decimal
    unit: VariationUnit


def outside_the_band(movement: Decimal, threshold: Decimal) -> bool:
    """Is one movement outside the band — the single predicate both readings share.

    **Uma função com nome porque DUAS coisas perguntam o mesmo**: `evaluate` pergunta pelo dia
    fechado e `days_outside_the_band` pergunta pelos anteriores. Escrita duas vezes, uma delas
    envelhece sozinha — e a que envelhece é a que ninguém corre em produção todos os dias.

    A regra do zero vem daqui e vale para os dois: **um movimento de exactamente zero nunca
    cruza**, qualquer que seja o limiar. `Semiannual (%)` é zero em 61.038 das suas 61.041 linhas,
    logo o seu próprio `p90` é zero, e sem esta cláusula ele "cruzava" todos os dias sem se mexer.
    Numa contagem de dias seguidos isso não daria um alerta a mais: daria uma persistência de
    noventa dias sobre uma métrica parada.
    """
    return movement != 0 and abs(movement) >= threshold


def days_outside_the_band(history: Sequence[Decimal], latest: Decimal, threshold: Decimal) -> int:
    """Quantos dias SEGUIDOS, terminando no dia fechado, ficaram fora da banda — `T1334`.

    A peça 1 do contrato aprovado dele: *"Severidade e persistência no título — separa acidente
    de tendência"* (`docs/exemplos-analise-dimensional.md`, linha 148). Um desvio de um dia e um
    desvio de três dias leem-se de maneira diferente, e hoje o alerta não sabe dizer qual é qual.

    ## A banda é UMA, e é a que o alerta mostra

    A frase dele diz *fora da banda*, no singular, e o alerta imprime uma banda só. Então o
    limiar é o mesmo para todos os dias contados: o que `threshold_from` derivou da série. **Não
    se re-deriva um limiar por dia** — isso responderia a outra pergunta (*cada dia foi anormal
    para a sua própria história?*) e daria um número que ninguém pode conferir contra a banda
    impressa ao lado.

    ## Derivado da série, nunca guardado entre corridas

    O número sai de ``history`` e de ``latest``, que já estão em mãos. **Um contador persistido
    mentiria no dia em que uma corrida falhasse** — e este repositório já teve duas que não
    chegaram ao fim. Um estado que só está certo quando tudo corre bem não é um estado: é uma
    suposição com um ficheiro à volta.

    Devolve ``0`` quando o dia fechado não cruzou — não há persistência de coisa nenhuma para
    contar, e zero aqui é a resposta e não a ausência dela.
    """
    if not outside_the_band(latest, threshold):
        return 0
    days = 1
    for movement in reversed(history):
        if not outside_the_band(movement, threshold):
            break
        days += 1
    return days


def evaluate(
    kpi: str,
    format_type: str,
    history: Sequence[Decimal],
    latest: Decimal,
    *,
    comparable_periods_across_kpis: Sequence[int],
) -> Crossing | None:
    """Whether ``kpi`` crossed, or ``None`` when it moved within its own noise.

    ``history`` is this KPI's own past movements — the threshold comes from them and
    from nothing else, so no constant appears anywhere on this path. **A KPI with too
    short a series refuses** rather than receiving a smaller threshold; the refusal is
    the caller's to catch, and the report keeps the KPI on the page regardless.
    """
    minimum = minimum_comparable_periods(comparable_periods_across_kpis)
    refuse_unless_series_is_long_enough(kpi, len(history), minimum)
    threshold = threshold_from(history)

    #: **A movement of exactly zero never crosses**, whatever the threshold is. Found on
    #: 2026-08-30 running the twenty: `Semiannual (%)` is zero in 61.038 of its 61.041 rows,
    #: so its own `p90` is **zero**, and `abs(0) < 0` is false — it "crossed" its threshold
    #: every single day while never moving at all.
    #:
    #: The threshold stays derived from the series and nothing is written down; what is
    #: refused is calling *no movement* a finding. It is the same reading `OD-34` already
    #: takes when it paints an exactly-zero movement yellow: neither better nor worse.
    if not outside_the_band(latest, threshold):
        return None
    return Crossing(
        kpi=kpi,
        movement=latest,
        threshold=threshold,
        unit=variation_unit_for(format_type),
    )
