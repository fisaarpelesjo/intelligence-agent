"""A peça 6 do contrato aprovado: o que foi MEDIDO e ELIMINADO — `T1334`, `FR-1320`.

O alerta que ele leu nomeia quem puxou o desvio e **não diz o que foi descartado**. A razão de a
peça existir está escrita no próprio contrato (`docs/exemplos-analise-dimensional.md`, linha 154):
*as hipóteses medidas e eliminadas; é o que impede o leitor de duvidar*. Sem ela o leitor refaz à
mão o trabalho que a medição já fez.

## Das três orações do exemplo dele, uma só tem medição que a sustente hoje

Medido em 2026-09-07, antes de escrever uma linha:

* *o crescimento não explica* — é a evidência de taxa-antes-de-contagem e **exige um par
  declarado**. O `report_governance/rate_before_count.yaml` diz `pairs: {}`: nenhuma taxa governa
  contagem nenhuma, logo não existe hipótese eliminada para afirmar;
* *os outros valores de um eixo indisponível* — o cron de 2026-09-06 11:00:02Z imprimiu
  ``eixos ditos indisponiveis: 2 (gateway, plan)``. **«Indisponível» e «medido e descartado» são
  afirmações opostas**, e o relatório já nomeia os indisponíveis com a frase governada do
  `FR-1316`;
* o que sobra — as partes que o eixo mediu e que não deixaram a própria banda — **já está
  calculado** no ponto onde o alerta se monta, e é o que este nó afirma.

E os dois eixos que restam são `country` e `game`, que são exactamente os dois cujas palavras ele
deu na `OD-153`. Não é coincidência: são os que a fonte tem.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from daily_reporting.report.breakdown import BreakdownGovernance
from daily_reporting.report.contribution import (
    ContributionGovernance,
    Discarded,
    DiscardedCoverageError,
    refuse_unavailable_coverage,
)
from daily_reporting.report.summary import render, summarise

REPO = Path(__file__).resolve().parents[4]

GOVERNED = REPO / "report_governance" / "contribution.yaml"
BREAKDOWN = REPO / "report_governance" / "breakdown.yaml"

DAY = date(2026, 9, 6)
INSTANT = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)


def _contribution() -> ContributionGovernance:
    return ContributionGovernance.from_document(yaml.safe_load(GOVERNED.read_text("utf-8")))


def _breakdown() -> BreakdownGovernance:
    return BreakdownGovernance.from_document(yaml.safe_load(BREAKDOWN.read_text("utf-8")))


def _rendered(discarded: tuple[Discarded, ...], *, for_alert: bool = True) -> str:
    summary = summarise(
        [],
        {},
        day=DAY,
        instant=INSTANT,
        discarded=discarded,
    )
    return render(
        summary,
        heading="x",
        contribution=_contribution(),
        breakdowns_governance=_breakdown(),
        for_alert=for_alert,
    )


def _an_unavailable_pair(governance: BreakdownGovernance) -> tuple[str, str]:
    """Um par (indicador, eixo) que o ficheiro governado declara INDISPONÍVEL, derivado.

    **Derivado e não escrito**, e a primeira versão deste nó ensinou porquê: fixei
    ``Chargeback (qty)``, que não carrega eixo indisponível nenhum, e os dois nós que provam a
    recusa vieram `SKIPPED` — verdes na contagem, sem terem afirmado nada. Um nó que pula é um nó
    que não mediu, e era exactamente a metade que o revisor pediu.

    Se o ficheiro deixar de declarar qualquer eixo indisponível, isto **pula nomeando o que não
    foi medido** — que é a resposta honesta a uma pergunta que a governança já não faz.
    """
    for axis in governance.unavailable_axes:
        if axis.kpis:
            return axis.kpis[0], axis.column
    pytest.skip("o ficheiro governado declara nenhum eixo indisponivel; nada foi medido")


def test_the_alert_names_what_stayed_inside_its_band() -> None:
    """A oração que HÁ hoje: o eixo concentrou, e o resto ficou dentro da própria banda."""
    governance = _contribution()
    text = _rendered(
        (Discarded(kpi_label="Chargeback (qty)", column="country", inside=41, concentrated=True),)
    )
    assert governance.discarded_heading in text
    assert governance.others in text
    assert governance.plural_for("country") in text
    assert governance.inside_band in text


def test_an_axis_where_nothing_concentrated_says_so_in_the_singular() -> None:
    """A segunda oração dele, e é uma afirmação DIFERENTE da primeira.

    Um eixo onde nenhuma parte deixou a própria banda não tem um resto — não houve nada de que
    ser o resto. Ele escreveu as duas separadas por ponto-e-vírgula, e são medidas diferentes.
    """
    governance = _contribution()
    text = _rendered(
        (Discarded(kpi_label="Chargeback (qty)", column="game", inside=930, concentrated=False),)
    )
    assert governance.none_of in text
    assert governance.singular_for("game") in text
    assert governance.concentrated in text
    assert governance.inside_band not in text


def test_an_axis_that_measured_nothing_produces_no_clause() -> None:
    """Silêncio aqui não é uma terceira resposta: é ausência de medição.

    A peça 6 só fala do que foi medido. Um eixo sem parte medida e sem concentração não descartou
    hipótese nenhuma, e afirmar que descartou seria a invenção que ela existe para impedir.
    """
    text = _rendered(
        (Discarded(kpi_label="Chargeback (qty)", column="country", inside=0, concentrated=True),)
    )
    assert _contribution().discarded_heading not in text


def test_the_daily_report_does_not_claim_to_have_discarded_anything() -> None:
    """A peça 6 é do ALERTA, e isso é o contrato dele e não gosto.

    A frase está no exemplo do alerta; o relatório diário não afirma hipóteses eliminadas porque
    não afirma hipóteses. Um relatório que dissesse o que descartou responderia uma pergunta que
    ninguém lhe fez.
    """
    text = _rendered(
        (Discarded(kpi_label="Chargeback (qty)", column="country", inside=41, concentrated=True),),
        for_alert=False,
    )
    assert _contribution().discarded_heading not in text


def test_an_unavailable_axis_can_never_be_offered_as_discarded() -> None:
    """**«Indisponível» e «medido e descartado» são afirmações opostas** — `T1334`.

    O relatório já nomeia os eixos indisponíveis com a frase governada do `FR-1316`. Oferecer um
    deles como hipótese eliminada afirmaria ter medido exactamente aquilo que este repositório
    declara não conseguir medir, e ao leitor isso lê-se como COBERTURA — o contrário do que a peça
    existe para dar.

    **Recusa, e não linha silenciosamente descartada.** Uma lista que encolhe sem ninguém saber
    porquê é o defeito que este repositório passa o tempo a fechar.
    """
    governance = _breakdown()
    kpi, column = _an_unavailable_pair(governance)
    one = Discarded(kpi_label=kpi, column=column, inside=7, concentrated=True)
    with pytest.raises(DiscardedCoverageError):
        refuse_unavailable_coverage(one, governance)


def test_the_refusal_reaches_the_render_and_not_only_the_helper() -> None:
    """A recusa tem de morder por onde o bloco sai, senão vigia uma porta que ninguém usa."""
    kpi, column = _an_unavailable_pair(_breakdown())
    with pytest.raises(DiscardedCoverageError):
        _rendered((Discarded(kpi_label=kpi, column=column, inside=7, concentrated=True),))


def test_no_word_of_the_block_is_written_in_this_file() -> None:
    """O bloco é montado de palavras dele, e este nó não pode carregar nenhuma.

    Cada asserção acima compara contra ``governance.<palavra>`` e nunca contra um literal. Se
    alguém escrever aqui a frase que espera ver, o nó passa a afirmar a sua própria cópia — que é
    exactamente como uma palavra governada envelhece sem ninguém notar.
    """
    source = __file__
    governance = _contribution()
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    for word in (
        governance.discarded_heading,
        governance.inside_band,
        governance.concentrated,
        governance.others,
    ):
        assert word not in text, f"a palavra governada {word!r} esta copiada neste no"


def test_the_complement_is_what_the_block_counts() -> None:
    """`inside` é o COMPLEMENTO das partes que saíram, e a conta é do chamador.

    Aqui fica só a propriedade que o resto depende: uma parte não pode estar nos dois lados. O nó
    que mede o complemento contra a série real é o do chamador, em `apps/telegram-bot`.
    """
    medidas = frozenset({"Brasil", "Portugal", "Angola"})
    sairam = frozenset({"Brasil"})
    dentro = medidas - sairam
    assert len(dentro) == 2
    assert not (dentro & sairam)
    assert Decimal(len(dentro)) + Decimal(len(sairam)) == Decimal(len(medidas))
