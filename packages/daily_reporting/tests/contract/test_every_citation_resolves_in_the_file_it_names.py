"""Cada citação governada aponta para um arquivo que REALMENTE contém a frase — `OD-133`.

## O defeito medido que criou este arquivo

`report_governance/*.yaml` transcreve as palavras dele e cita, linha a linha, o contrato de onde
cada uma veio. Em 2026-09-06 mediu-se que **as citações apontavam para um arquivo fora da
árvore**, e que existiam **dois** contratos, não duas versões de um: 177 linhas contra 387, com
o **bloco do ALERTA reescrito**. As linhas 22 a 28 do antigo — o cabeçalho do alerta, os dois
movers com emoji por eixo, o plural em `pts` e a frase dos demais — não existem no novo.

`heading_alert` está **em produção**: sai no alerta das 08:00. Reapontar a citação dele para o
contrato novo faria o arquivo governado dizer que a palavra vem de um documento que não a
contém — e trocar a palavra mudaria o que ele lê, sem ele ter pedido. Por `OD-133` cada chave
cita o arquivo de onde a palavra dela veio **de fato**, e este nó é o que impede a mistura.

**A citação velha era verdadeira contra o arquivo dela; uma citação reapontada sem remedição
seria falsa contra os dois.** É o defeito que o `ed3e8a9` consertou uma vez, e este nó é para
não precisar consertar de novo.

**Mutações, cada uma vermelha num nó diferente e restaurada por `cp` + `cmp`** — todas
`1 failed, 8 passed`, medidas em 2026-09-06:

* `heading_alert` reapontado para o contrato atual — o defeito que a `OD-133` proíbe;
* a razão apagada de ao lado da chave, deixando só a citação ao documento antigo, que é o que
  faz a próxima pessoa "arrumar";
* uma citação para uma linha que o arquivo não tem;
* a palavra do alerta trocada pela redação do contrato atual, que é a decisão dele e não minha.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
GOVERNANCE = REPO / "report_governance"
ATUAL = REPO / "docs" / "exemplos-analise-dimensional.md"
HISTORICO = REPO / "docs" / "contrato-013-exemplos.md"

#: `docs/<arquivo>.md ... linha(s) N`, com o número podendo vir a várias palavras do caminho.
_CITACAO = re.compile(r"(docs/[\w.-]+\.md)[^\n]{0,80}?linhas?\s+(\d+)")


def _achatado(texto: str) -> str:
    """Sem acento, sem caixa, sem espaço duplo — como a comparação de palavras já faz."""
    decomposto = unicodedata.normalize("NFD", texto)
    return " ".join(
        "".join(c for c in decomposto if unicodedata.category(c) != "Mn").casefold().split()
    )


def _governados() -> list[Path]:
    return sorted(GOVERNANCE.glob("*.yaml"))


def test_os_dois_contratos_estao_na_arvore_e_sao_documentos_diferentes() -> None:
    """Um deles vivia fora do git, e por isso toda citação pendurava fora da árvore."""
    assert ATUAL.is_file() and HISTORICO.is_file()
    atual = ATUAL.read_text(encoding="utf-8")
    historico = HISTORICO.read_text(encoding="utf-8")
    assert atual != historico
    #: **Não são duas versões de um texto.** A diferença de tamanho é a prova barata; a cara
    #: está no nó seguinte, que mede frase por frase.
    assert len(atual.splitlines()) > len(historico.splitlines())


@pytest.mark.parametrize("arquivo", _governados(), ids=lambda p: p.name)
def test_toda_citacao_aponta_para_uma_linha_que_existe(arquivo: Path) -> None:
    """Um número de linha maior que o arquivo é uma citação que ninguém conferiu."""
    texto = arquivo.read_text(encoding="utf-8")
    #: Junta as linhas do comentário: uma citação quebra em duas linhas com frequência, e um
    #: casamento por linha isolada perderia exatamente as que mais erram.
    corrido = " ".join(texto.split())
    for caminho, numero in _CITACAO.findall(corrido):
        citado = REPO / caminho
        assert citado.is_file(), f"{arquivo.name} cita {caminho}, que não está na árvore"
        total = len(citado.read_text(encoding="utf-8").splitlines())
        assert 1 <= int(numero) <= total, (
            f"{arquivo.name} cita {caminho} linha {numero}, e o arquivo tem {total}"
        )


def test_a_palavra_do_alerta_vem_do_historico_e_a_do_diario_do_atual() -> None:
    """**O par que decidiu a `OD-133`, afirmado nos dois sentidos.**

    Uma metade sozinha passaria por acidente: afirmar só que `heading_alert` está no histórico
    não impede alguém de reapontar a citação, e afirmar só que `heading` está no atual não diz
    nada sobre o alerta. O que se afirma é que **os dois documentos não são intercambiáveis**.
    """
    documento = yaml.safe_load((GOVERNANCE / "contribution.yaml").read_text(encoding="utf-8"))
    atual = _achatado(ATUAL.read_text(encoding="utf-8"))
    historico = _achatado(HISTORICO.read_text(encoding="utf-8"))

    do_alerta = _achatado(str(documento["heading_alert"]))
    assert do_alerta in historico, "a forma do alerta saiu do contrato histórico"
    assert do_alerta not in atual, (
        "a forma do alerta passou a existir no contrato atual; se ele reescreveu o alerta, a "
        "citação e a decisão de trocar a palavra são dele, e este nó é onde isso aparece"
    )

    do_diario = _achatado(str(documento["heading"]))
    assert do_diario in atual, "o cabeçalho do diário saiu do contrato atual"


def test_a_chave_do_alerta_cita_o_historico_e_diz_por_que() -> None:
    """A razão fica **ao lado da citação**, não num relatório que ninguém reabre.

    `OD-133` pediu a razão escrita. Sem ela, a próxima pessoa lê uma citação a um documento
    antigo e "arruma" — que é o defeito, não o conserto.
    """
    linhas = (GOVERNANCE / "contribution.yaml").read_text(encoding="utf-8").splitlines()
    onde = next(i for i, linha in enumerate(linhas) if linha.startswith("heading_alert:"))
    #: O bloco de comentário imediatamente acima da chave.
    bloco: list[str] = []
    for linha in reversed(linhas[:onde]):
        if not linha.startswith("#"):
            break
        bloco.append(linha)
    comentario = _achatado(" ".join(bloco))
    assert "docs/contrato-013-exemplos.md" in comentario
    assert "nao ocorre no contrato novo" in comentario or "nao existe no novo" in comentario
