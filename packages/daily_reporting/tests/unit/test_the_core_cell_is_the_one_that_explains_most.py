"""O núcleo: a célula que explica a maior fatia — `T1334`, peça 5 do contrato aprovado.

*"A interseção (o núcleo) — o insight de verdade: uma célula explicando metade do desvio é causa,
não coincidência"* (`docs/exemplos-analise-dimensional.md`, linha 152).

## Só o cálculo. A frase espera a palavra dele.

O que ele lê — o rótulo do núcleo e a forma como os dois nomes aparecem lado a lado — é vocabulário
dele e **não existe na governança**. Por isso a identidade da célula fica guardada como **par**, e
não junta numa string: guardá-la junta seria este pacote a escolher a forma por ele, que é o mesmo
defeito que acabou de sair do alerta hoje.

## Uma régua só

`Contribution` e `Cell` fazem a mesma aritmética, e fazem-na **por construção**: as duas chamam
`deviation_between` e `share_of_deviation`. Escritas duas vezes, uma envelheceria sozinha.
"""

from __future__ import annotations

from decimal import Decimal

from daily_reporting.report.contribution import (
    Cell,
    Contribution,
    cells_reconcile,
    core_cell_of,
)

TOTAL = Decimal(-100)
TOLERANCE = Decimal("0.01")


def _cell(first: str, second: str, before: int | None, after: int | None) -> Cell:
    return Cell(
        pair=(first, second),
        before=None if before is None else Decimal(before),
        after=None if after is None else Decimal(after),
    )


def test_the_core_is_the_cell_with_the_largest_movement() -> None:
    """A célula que mais moveu é o núcleo, e é a resposta que a peça 5 existe para dar."""
    celulas = [
        _cell("Brasil", "Minecraft", 100, 45),
        _cell("Brasil", "Roblox", 50, 40),
        _cell("Portugal", "Minecraft", 30, 5),
    ]
    nucleo = core_cell_of(celulas, TOTAL)
    assert nucleo is not None
    assert nucleo.pair == ("Brasil", "Minecraft")
    assert nucleo.share_of(TOTAL) == Decimal("0.55")


def test_a_rise_and_a_fall_of_the_same_size_concentrate_the_same() -> None:
    """A fatia compara-se em MAGNITUDE: o sinal diz para que lado, não quanto."""
    subiu = [_cell("Brasil", "Minecraft", 10, 65), _cell("Brasil", "Roblox", 50, 40)]
    nucleo = core_cell_of(subiu, Decimal(100))
    assert nucleo is not None
    assert nucleo.pair == ("Brasil", "Minecraft")


def test_a_tie_has_no_core_and_that_is_the_answer() -> None:
    """**Duas células com o mesmo peso não têm núcleo.**

    Escolher uma delas seria este módulo a decidir qual causa contar, e a peça existe justamente
    para separar causa de coincidência. Um empate é coincidência por definição.
    """
    empate = [
        _cell("Brasil", "Minecraft", 100, 50),
        _cell("Portugal", "Roblox", 100, 50),
    ]
    assert core_cell_of(empate, TOTAL) is None


def test_a_cell_seen_on_one_side_only_is_never_the_core() -> None:
    """Ela conta para a conservação, mas dizer que é o núcleo afirmaria um movimento não observado.

    Uma interseção que *"passou de nada para sessenta"* é uma frase sobre um período em que
    ninguém a viu. A mesma distinção que as partes de um eixo já fazem.
    """
    so_um_lado = [_cell("Brasil", "Minecraft", None, 60), _cell("Brasil", "Roblox", 50, 45)]
    nucleo = core_cell_of(so_um_lado, TOTAL)
    assert nucleo is not None
    assert nucleo.pair == ("Brasil", "Roblox")


def test_with_no_cell_measured_twice_there_is_no_core() -> None:
    """Se nenhuma foi vista dos dois lados, não há núcleo — e não se promove a menos má."""
    assert core_cell_of([_cell("Brasil", "Minecraft", None, 60)], TOTAL) is None


def test_a_still_total_has_no_core_because_a_share_of_nothing_is_not_a_number() -> None:
    """Não se divide por zero para descobrir isso: recusa-se antes."""
    assert core_cell_of([_cell("Brasil", "Minecraft", 10, 40)], Decimal(0)) is None


def test_a_single_still_cell_is_not_a_core() -> None:
    """**Uma célula parada, sozinha, não é núcleo — e este caso quase me escapou.**

    A primeira escrita deste ficheiro só tinha o caso de DUAS paradas, e aí é o empate que
    devolve ``None``: a verificação do zero nunca era exercida. A mutação que a removia ficou
    VERDE. Com uma célula só, o empate não existe e o zero é a única coisa a segurar a resposta.

    Zero não explica coisa nenhuma, e um núcleo que explica zero por cento do desvio é uma frase
    que diz ao leitor que encontrou a causa quando não encontrou nada.
    """
    assert core_cell_of([_cell("Brasil", "Minecraft", 10, 10)], TOTAL) is None


def test_cells_that_never_moved_have_no_core() -> None:
    """Todas paradas: a maior fatia é zero, e zero não explica coisa nenhuma."""
    paradas = [_cell("Brasil", "Minecraft", 10, 10), _cell("Portugal", "Roblox", 5, 5)]
    assert core_cell_of(paradas, TOTAL) is None


def test_no_cells_at_all_answers_none() -> None:
    """Nada medido, nenhum núcleo. Uma célula inventada seria pior do que nenhuma."""
    assert core_cell_of([], TOTAL) is None


def test_the_cells_reconcile_against_the_total_movement() -> None:
    """A conservação, e é ela que impede a grelha de mentir por omissão."""
    fecha = [
        _cell("Brasil", "Minecraft", 100, 45),
        _cell("Brasil", "Roblox", 50, 40),
        _cell("Portugal", "Minecraft", 30, 5),
        _cell("Portugal", "Roblox", 20, 10),
    ]
    assert cells_reconcile(fecha, TOTAL, TOLERANCE)


def test_a_missing_cell_breaks_the_reconciliation() -> None:
    """**A asserção que torna a de cima um instrumento.**

    Tira-se uma célula e a soma deixa de fechar. Sem este nó, *"as células reconciliam"* passaria
    a verde para sempre no dia em que uma caísse — que é exactamente o que acontece quando um dos
    dois eixos vier vazio.
    """
    faltando = [
        _cell("Brasil", "Minecraft", 100, 45),
        _cell("Brasil", "Roblox", 50, 40),
        _cell("Portugal", "Minecraft", 30, 5),
    ]
    assert not cells_reconcile(faltando, TOTAL, TOLERANCE)


def test_the_two_shapes_measure_the_same_movement_with_the_same_ruler() -> None:
    """**Uma célula e uma parte de um eixo dão o mesmo número para os mesmos lados.**

    Não é coincidência aritmética: as duas chamam as mesmas duas funções. Este nó é o que impede
    que uma delas passe a calcular à sua maneira sem ninguém ver.
    """
    for antes, depois in ((100, 45), (None, 60), (30, None), (0, 0)):
        celula = _cell("Brasil", "Minecraft", antes, depois)
        parte = Contribution(
            value="Brasil",
            before=None if antes is None else Decimal(antes),
            after=None if depois is None else Decimal(depois),
        )
        assert celula.deviation == parte.deviation, (antes, depois)
        assert celula.was_measured_twice == parte.was_measured_twice, (antes, depois)
        if parte.deviation != 0:
            assert celula.share_of(TOTAL) == parte.share_of(TOTAL), (antes, depois)


def test_the_pair_is_kept_apart_and_never_joined_here() -> None:
    """A identidade é o par, e este pacote não escolhe como os dois nomes aparecem juntos.

    A forma que ele lê é palavra dele e ainda não existe na governança. Guardar a chave já junta
    seria decidir por ele — o mesmo defeito que saiu do alerta hoje.
    """
    nucleo = core_cell_of([_cell("Brasil", "Minecraft", 100, 45)], TOTAL)
    assert nucleo is not None
    assert nucleo.pair == ("Brasil", "Minecraft")
    assert isinstance(nucleo.pair, tuple)
