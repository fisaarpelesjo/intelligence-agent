"""O alerta não afirma sobre dimensões que nunca examinou — medido no produto, 2026-09-07.

## O que saiu para ele, às 08:01 -03, para três destinatários

O alerta carregava três indicadores e fechava assim:

    🔴 Trial conversion (%)   ...
    🔴 Revenue (US$)   Variação: -36,38 %   ...
    🟢 MAU   +0,31 %   ...
    Sem desvios relevantes — nenhuma dimensão fora da banda.

**Dos três, só `Trial conversion (%)` tem dimensão declarada** — `report_governance/breakdown.yaml`
lista `New trials`, `Sales (qty)` e `Trial conversion (%)` e mais nada. O `Revenue (US$)` e o `MAU`
**nunca tiveram uma dimensão examinada**, e o laço que decompõe itera exactamente aquela lista.

A frase não era silêncio. Era uma **afirmação positiva sobre uma medição que não aconteceu**, a três
centímetros de um `Revenue (US$) -36,38 %`. Quem a lê conclui que se olhou às dimensões do Revenue e
nada se achou; não se olhou.

## O enquadramento é dele, e põe a frase noutro produto

O contrato aprovado escreve-a no fecho do **RELATÓRIO** — `docs/exemplos-analise-dimensional.md`,
linhas 43-44, dentro da secção 1 — e diz o que ela pressupõe: *"Num dia quieto, muda só o fecho:
**as quebras continuam**"*. Ela é o que se diz depois de se ter olhado. O alerta é a secção 3 e não
carrega quebras nenhumas.

**A cura é remoção, não invenção.** Uma frase substituta — *"nenhuma dimensão foi examinada"* —
seria vocabulário que ele não deu, e a cura de uma afirmação não sustentada não pode ser outra
afirmação nossa. O alerta fica sem bloco, como já fica com todos os blocos que não tem.

**Este defeito é anterior a nós e chegou ao produto.** Fica aqui datado com o texto que saiu.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import yaml

from daily_reporting.report.contribution import ContributionGovernance, Pull
from daily_reporting.report.summary import render, summarise

REPO = Path(__file__).resolve().parents[4]
GOVERNED = REPO / "report_governance" / "contribution.yaml"

DAY = date(2026, 9, 6)
INSTANT = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)


def _contribution() -> ContributionGovernance:
    return ContributionGovernance.from_document(yaml.safe_load(GOVERNED.read_text("utf-8")))


def _a_pull() -> Pull:
    return Pull(
        value="India",
        kpi_label="New trials",
        column="country",
        before=Decimal(100),
        after=Decimal(79),
        share=Decimal("0.30"),
        format_type="int",
        others_compensated=False,
    )


def _rendered(pulls: tuple[Pull, ...], *, for_alert: bool) -> str:
    summary = summarise([], {}, day=DAY, instant=INSTANT, pulls=pulls)
    return render(
        summary,
        heading="x",
        contribution=_contribution(),
        for_alert=for_alert,
    )


def test_the_alert_without_pulls_says_nothing_about_dimensions() -> None:
    """**A mutação que importa**: a frase do dia quieto num alerta sem puxadas → vermelho.

    É o caso exacto de 2026-09-07: nenhum dos indicadores que cruzaram tinha puxada, e o alerta
    fechou a afirmar que nenhuma dimensão saíra da banda — sobre dois que nunca foram examinados.
    """
    assert _contribution().quiet_day not in _rendered((), for_alert=True)


def test_the_report_without_pulls_still_closes_the_way_he_wrote_it() -> None:
    """**A mutação que protege a resposta legítima.**

    No relatório os indicadores declarados FORAM examinados, e um dia sem nada fora da banda é um
    dia quieto de verdade. A cura não pode calar isso — seria trocar uma afirmação a mais por uma
    ausência a mais.
    """
    assert _contribution().quiet_day in _rendered((), for_alert=False)


def test_no_path_puts_the_reports_sentence_in_the_alert() -> None:
    """A terceira: com puxadas ou sem elas, o alerta nunca leva a frase do relatório.

    Com puxadas o alerta leva o seu próprio cabeçalho; sem elas não leva bloco. Nenhum dos dois
    caminhos passa pelo fecho do outro produto.
    """
    governance = _contribution()
    for pulls in ((), (_a_pull(),)):
        assert governance.quiet_day not in _rendered(pulls, for_alert=True)


def test_the_alert_with_pulls_still_carries_its_own_block() -> None:
    """A remoção é do FECHO, não do bloco: um alerta com puxadas continua a dizer quem puxou."""
    texto = _rendered((_a_pull(),), for_alert=True)
    assert _contribution().heading_alert in texto
    assert "India" in texto


def test_the_two_products_close_differently_on_the_same_empty_input() -> None:
    """A propriedade em uma linha: a mesma entrada vazia, duas respostas, e é isso que se cura."""
    alerta = _rendered((), for_alert=True)
    relatorio = _rendered((), for_alert=False)
    assert alerta != relatorio
    assert _contribution().quiet_day in relatorio
    assert _contribution().quiet_day not in alerta
