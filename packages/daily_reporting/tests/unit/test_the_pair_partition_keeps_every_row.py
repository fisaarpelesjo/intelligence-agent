"""A partição por PAR de eixos — `T1334`, e a reconciliação é a propriedade que a sustenta.

A peça 5 do contrato aprovado é a interseção: *"uma célula (país por gateway por plano) explicando
metade do desvio é causa, não coincidência"* (`docs/exemplos-analise-dimensional.md`, linha 152).

## O que foi medido antes de esta função existir

* a view **já é por país por jogo**: em 2026-09-06, `New trials` deu 373 linhas para 84 países e 114
  jogos, e **373 células distintas** — cada linha é uma célula;
* as células somam o mesmo que qualquer dos eixos sozinho: `674 = 674 = 674`;
* e o risco real, que não é o dado mas a queda: **o par cai se QUALQUER lado cair.** Seis dias,
  quatro KPIs, 5.520 linhas — zero nulos em `country`, zero em `game`, zero em qualquer dos dois.

**Do exemplo dele, o núcleo é país por gateway por plano, e dois desses eixos estão declarados
INDISPONÍVEIS.** O que a fonte tem é país por jogo. A estrutura é dele; os eixos são os que existem,
e a diferença fica escrita em vez de ser substituída em silêncio.

## Função nova, e o `partition_by` fica como está

Cinco sítios de produção e cinco nós dependem de partir por UMA coluna. Alargar aquela assinatura
deixaria os cinco a poder receber o que nenhum deles pediu, e o nó que a fixa deixaria de proteger
o que protege.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest

from daily_reporting.contracts import ReportRefusal
from daily_reporting.view.reading import partition_by, partition_by_pair

MARKER = "(Total)"


def _row(country: str | None, game: str | None, value: int, **extra: Any) -> dict[str, Any]:
    return {"country": country, "game": game, "value": Decimal(value), **extra}


ROWS = [
    _row("Brasil", "Minecraft", 10),
    _row("Brasil", "Roblox", 20),
    _row("Portugal", "Minecraft", 30),
    _row("Brasil", "Minecraft", 5),
]


def test_each_pair_gets_its_own_bucket() -> None:
    """Uma célula é um par, e duas linhas do mesmo par caem juntas."""
    partido = dict(partition_by_pair(ROWS, "country", "game"))
    assert set(partido) == {
        ("Brasil", "Minecraft"),
        ("Brasil", "Roblox"),
        ("Portugal", "Minecraft"),
    }
    assert len(partido[("Brasil", "Minecraft")]) == 2


def test_every_row_lands_in_exactly_one_cell() -> None:
    """**A reconciliação, e é ela que separa a tabela certa da que parece certa.**

    A soma das células tem de ser a soma das linhas. Se um dia uma linha cair — porque um dos
    eixos vier vazio — este nó acende, e é isso que se quer: a queda tem de ser DITA, não
    absorvida por um total que continua a fechar sozinho.
    """
    celulas = partition_by_pair(ROWS, "country", "game")
    nas_celulas = sum(len(grupo) for _, grupo in celulas)
    assert nas_celulas == len(ROWS)
    soma = sum((cast("Decimal", row["value"]) for _, grupo in celulas for row in grupo), Decimal(0))
    assert soma == sum((cast("Decimal", row["value"]) for row in ROWS), Decimal(0))


def test_the_cells_reconcile_against_each_single_axis() -> None:
    """As células somam o mesmo que qualquer dos dois eixos sozinho — medido, e agora afirmado."""
    por_celula = sum(
        (
            cast("Decimal", row["value"])
            for _, g in partition_by_pair(ROWS, "country", "game")
            for row in g
        ),
        Decimal(0),
    )
    for eixo in ("country", "game"):
        por_eixo = sum(
            (cast("Decimal", row["value"]) for _, g in partition_by(ROWS, eixo) for row in g),
            Decimal(0),
        )
        assert por_celula == por_eixo, eixo


def test_a_row_missing_either_axis_falls_and_the_sum_says_so() -> None:
    """O par cai se QUALQUER lado cair, e a queda aparece na soma.

    Não é um caso hipotético que se documenta: é o que torna a asserção acima um instrumento em
    vez de uma decoração. Hoje não cai nenhuma; quando cair, esta é a diferença que se vê.
    """
    com_buraco = [*ROWS, _row(None, "Minecraft", 99), _row("Brasil", None, 77)]
    celulas = partition_by_pair(com_buraco, "country", "game")
    nas_celulas = sum(len(grupo) for _, grupo in celulas)
    assert nas_celulas == len(ROWS)
    assert nas_celulas < len(com_buraco)


def test_any_pair_touching_an_excluded_marker_is_refused() -> None:
    """**Qualquer par que TOQUE o marcador sai** — não só o par feito de dois marcadores.

    O marcador é o agregado daquele eixo. Uma célula que o contenha soma o agregado junto com as
    partes e conta duas vezes, e isso vale mesmo quando o outro lado do par é uma parte legítima.
    """
    com_marcador = [
        *ROWS,
        _row("Brasil", MARKER, 999),
        _row(MARKER, "Minecraft", 888),
        _row(MARKER, MARKER, 777),
    ]
    celulas = dict(partition_by_pair(com_marcador, "country", "game", (MARKER,), (MARKER,)))
    assert set(celulas) == {
        ("Brasil", "Minecraft"),
        ("Brasil", "Roblox"),
        ("Portugal", "Minecraft"),
    }


def test_the_marker_is_only_excluded_on_the_axis_that_declares_it() -> None:
    """O ficheiro governado declara o marcador POR EIXO, e a função respeita isso.

    Declarado só para o segundo eixo, um par cujo PRIMEIRO lado carrega a mesma string continua a
    entrar — porque nesse eixo aquela string não é um marcador, é uma parte com um nome infeliz.
    """
    com_marcador = [*ROWS, _row(MARKER, "Minecraft", 888), _row("Brasil", MARKER, 999)]
    celulas = dict(partition_by_pair(com_marcador, "country", "game", (), (MARKER,)))
    assert (MARKER, "Minecraft") in celulas
    assert ("Brasil", MARKER) not in celulas


def test_a_snapshot_refuses_here_too() -> None:
    """Uma interseção é uma quebra duas vezes, e um SNAPSHOT não tem quebra.

    A recusa é a mesma do `partition_by` e pela mesma razão: a figura de um SNAPSHOT é o último
    dia que o conjunto INTEIRO cobre, e uma parte que parou antes seria reportada no dia de outra.
    """
    snapshot = [_row("Brasil", "Minecraft", 10, aggregation_class="SNAPSHOT")]
    with pytest.raises(ReportRefusal):
        partition_by_pair(snapshot, "country", "game")


def test_the_single_axis_partition_is_untouched() -> None:
    """A função nova não mexeu na antiga: mesma assinatura, mesmo resultado."""
    assert dict(partition_by(ROWS, "country")).keys() == {"Brasil", "Portugal"}
    assert len(partition_by(ROWS, "country", (MARKER,))) == 2
