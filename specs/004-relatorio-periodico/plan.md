# Implementation Plan: Relatorio periodico

**Branch**: `004-relatorio-periodico` | **Date**: 2026-09-08 | **Spec**: `specs/004-relatorio-periodico/spec.md`

**Input**: Feature specification from `specs/004-relatorio-periodico/spec.md`

## Summary

Construir uma biblioteca Python pura com duas funcoes independentes: `gerar_relatorio_diario()` (agrega uma lista de KPIs para o dia anterior, tolerando indisponibilidade por KPI) e `avaliar_alertas()` (avalia uma lista de regras de limiar contra o mesmo dia, tambem tolerando indisponibilidade por regra). Ambas reusam `catalogo_semantico.decidir()` e `execucao_query.executar()` diretamente — sem depender de `interacao_conversacional` (nao ha linguagem natural aqui, apenas configuracao estruturada).

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: `catalogo_semantico`, `execucao_query`.

**Storage**: N/A.

**Testing**: `pytest`, com `FakeDataSource` de `execucao_query`.

**Target Platform**: Biblioteca Python standalone.

**Project Type**: Library (quarto pacote do monorepo).

**Performance Goals**: Negligivel alem do tempo de `execucao_query` por KPI/regra.

**Constraints**: Nenhuma excecao nao tratada pode escapar por causa de uma metrica indisponivel (FR-004, SC-002); `DailyReport` e `AlertBundle` estruturalmente sem campo em comum (FR-005, SC-004).

**Scale/Scope**: Duas funcoes publicas, tipos de KPI/alerta, sem estado persistente.

## Constitution Check

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | Reusa `catalogo_semantico`/`execucao_query` sem contornar nenhuma checagem. | PASS |
| II. Deterministic First | Sem LLM nesta feature; toda logica e deterministica. | PASS |
| III. Provenance or Abstention | Todo `KpiResult`/`AlertResult` e disponivel-com-proveniencia ou indisponivel-com-motivo — nunca ambigo. | PASS |
| IV. Least Privilege | Nenhuma escrita; somente leitura via `execucao_query`. | PASS |
| V. Idempotent, Auditable Delivery | N/A (sem entrega/mensageria nesta feature); justificado. | PASS (N/A) |

Nenhuma violacao identificada.

## Project Structure

### Documentation (this feature)

```text
specs/004-relatorio-periodico/
├── plan.md
├── spec.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source Code (repository root)

```text
packages/
└── relatorio_periodico/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── relatorio_periodico/
    │       ├── __init__.py
    │       ├── modelos.py       # KpiDefinition, KpiResult, DailyReport, AlertRule, AlertResult, AlertBundle
    │       ├── relatorio.py     # gerar_relatorio_diario()
    │       └── alerta.py        # avaliar_alertas()
    └── tests/
        └── unit/
            ├── conftest.py
            ├── test_relatorio_diario.py
            ├── test_avaliacao_de_alertas.py
            └── test_relatorio_e_alerta_nao_se_fundem.py
```

**Structure Decision**: quarto pacote do monorepo, dependente apenas de `catalogo_semantico` e `execucao_query` — nao depende de `interacao_conversacional` (sem NL nesta feature).

## Complexity Tracking

Nenhuma violacao da Constitution identificada. Tabela nao aplicavel.
