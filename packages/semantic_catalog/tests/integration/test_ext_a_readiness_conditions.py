"""As condições 2-4 do T109/D-12, medidas contra o armazém REAL — ciclo 539.

A condição 1 (as duas tabelas existem, governadas e populadas) foi medida satisfeita em
ciclo anterior. Aqui: (2) o mapeamento declarado coluna-a-coluna casa com o
`INFORMATION_SCHEMA` VIVO, nas duas direções; (3) o PRÓPRIO pacote lê as duas tabelas com
a identidade dedicada e devolve os SEUS contratos (`is_fixture=False`); (4) a
reconciliação roda contra o `metric_availability` VIVO — e o que ela encontra HOJE é
divergência REAL, afirmada como tal: **o dia em que a reconciliação limpar, o nó da
divergência fica vermelho e o d_12 vira declarável** — essa é a função dele, herdada do
nó-premissa da 007.

Sem credencial: skip honesto nomeando o que NÃO foi medido (o padrão da casa, e a
partição declarada no workflow do catálogo cobre exatamente estes skips). O AMBIENTE é
lido AQUI, no teste — o src do pacote recebe a credencial injetada (regra do d_15).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from semantic_catalog.freshness.warehouse_read import (
    LIVE_AVAILABILITY_COLUMNS,
    LIVE_FRESHNESS_COLUMNS,
    client_from_credentials,
    live_information_schema,
    read_freshness_records,
    read_observed_coverage,
)

pytestmark = pytest.mark.integration

#: Os pares fantasmas da era FR-005 (fontes cujos pipelines nao existem — medido em
#: fr005-views-fantasma, ciclo 523). Uma divergencia NESTES pares e historia datada;
#: uma divergencia FORA deles e o mundo mudando debaixo do catalogo.
GHOST_SOURCES = frozenset(
    {"android_app", "ios_app", "website", "google_play", "apple_app_store", "galaxy_store"}
)


def _client():  # type: ignore[no-untyped-def] - provider client, typed as the protocol
    """O TESTE lê o ambiente e INJETA — o src do pacote não conhece a variável (d_15)."""
    import os

    configured = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not configured:
        pytest.skip("no Google credential is configured; the D-12 conditions were NOT measured")
    return client_from_credentials(configured)


def test_condition_2_the_declared_column_mapping_matches_the_live_schema() -> None:
    """As duas direções: coluna viva fora do mapa, e mapa citando coluna que não existe."""
    live = live_information_schema(_client())
    assert set(live["source_freshness"]) == set(LIVE_FRESHNESS_COLUMNS), (
        "source_freshness moveu de schema; o mapa declarado deve ser re-derivado"
    )
    assert set(live["metric_availability"]) == set(LIVE_AVAILABILITY_COLUMNS), (
        "metric_availability moveu de schema; o mapa declarado deve ser re-derivado"
    )


def test_condition_3_the_package_reads_both_tables_through_its_own_path() -> None:
    """A leitura é do PACOTE, com a identidade dedicada — não do executor do bot (d_15)."""
    client = _client()
    records = read_freshness_records(client)
    assert records, "source_freshness devolveu zero linhas"
    sources = {record.source for record in records}
    assert "subscription_daily" in sources, sources

    coverage = read_observed_coverage(client)
    assert coverage.is_fixture is False, "a leitura viva jamais se apresenta como fixture"
    assert len(coverage.rows) >= 19, (
        f"{len(coverage.rows)} pares vivos; o produto serve ao menos os 19 decididos"
    )
    assert all(row.source == "subscription_daily" for row in coverage.rows), (
        "um par vivo aponta para fonte que o armazem de hoje nao produz"
    )


def test_condition_4_reconciliation_against_live_finds_the_measured_divergence() -> None:
    """Nome histórico fincado; o corpo é a verdade de 2026-09-03 DEPOIS do OD-106: o
    censo ZEROU de verdade — os dois cliques do dono (19 servidas declaradas como JANELA
    DESLIZANTE lidas do vivo; 28 fantasmas aposentadas como histórico datado; new_trials
    convertida) limparam os 29 erros. O que resta, e é afirmado por NOME, é UM aviso: a
    cobertura viva de cac_brl sem declaração — a própria decisão governada de 2026-08-30
    (numerador ausente na fonte) reportada, nunca recusada. Este nó agora VIGIA: um erro
    novo de reconciliação — uma declaração sem par vivo, um predates num não-sliding —
    acende aqui primeiro."""
    import subprocess
    from datetime import date
    from pathlib import Path

    from semantic_catalog.compliance.report import compliance_report

    client = _client()
    observed = read_observed_coverage(client)
    repo = Path(__file__).resolve().parents[4]
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    report = compliance_report(
        repo / "semantic", current_commit=commit, on=date(2026, 9, 2), coverage=observed
    )
    errors = [line for line in report.validation.render() if "[L3/error]" in line]
    assert errors == [], (
        "a reconciliacao contra o vivo DIVERGIU de novo — o censo do OD-106 era zero; "
        f"re-derive com a lista: {errors}"
    )
    warnings = [line for line in report.validation.render() if "[L3/warning]" in line]
    for line in warnings:
        assert "coverage_without_declaration" in line and "cac_brl" in line, (
            f"um aviso fora do nomeado (cac_brl, decisao de 2026-08-30) apareceu: {line}"
        )
    # E a limitation eterna morreu NESTE modo: cobertura viva suprida, e nao e fixture.
    assert not report.observed_is_fixture
    assert all("no observed coverage was supplied" not in text for text in report.limitations)


def test_the_sliding_declarations_cover_the_live_pairs_exactly() -> None:
    """OD-106: toda declaração AVAILABLE aponta um par VIVO, e as vivas de
    subscription_daily estão declaradas (a exceção nomeada é cac_brl, indisponível por
    decisão própria). A próxima declaração sem par vivo acende aqui."""
    import yaml as yaml_reader

    client = _client()
    observed = read_observed_coverage(client)
    live_pairs = {(row.metric, row.source) for row in observed.rows}

    repo = Path(__file__).resolve().parents[4]
    declared: set[tuple[str, str]] = set()
    sliding_count = 0
    for path in sorted((repo / "semantic" / "metrics").glob("*.yaml")):
        loaded: object = yaml_reader.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            continue
        doc: dict[str, object] = {str(k): v for k, v in loaded.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        if doc.get("kind") != "metric":
            continue
        raw_entries: object = doc.get("source_availability") or []
        if not isinstance(raw_entries, list):
            continue
        for item in raw_entries:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(item, dict):
                continue
            entry: dict[str, object] = {str(k): v for k, v in item.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            if entry.get("status") == "available":
                declared.add((str(doc["name"]), str(entry.get("source"))))
                if entry.get("sliding"):
                    sliding_count += 1
    assert declared <= live_pairs, f"declaracoes sem par vivo: {sorted(declared - live_pairs)}"
    undeclared_live = {pair for pair in live_pairs if pair not in declared}
    assert undeclared_live == {("cac_brl", "subscription_daily")}, (
        f"pares vivos sem declaracao alem do nomeado: {sorted(undeclared_live)}"
    )
    assert sliding_count >= 19, f"{sliding_count} deslizantes; o OD-106 declarou 19+1"
