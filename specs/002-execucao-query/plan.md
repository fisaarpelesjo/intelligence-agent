# Implementation Plan: Execucao de query governada

**Branch**: `002-execucao-query` | **Date**: 2026-09-07 | **Spec**: `specs/002-execucao-query/spec.md`

**Input**: Feature specification from `specs/002-execucao-query/spec.md`

## Summary

Construir uma biblioteca Python pura que recebe uma `AccessDecision` ja produzida pelo pacote `catalogo_semantico`, um filtro opcional e um periodo, e decide se pode compilar e executar uma leitura contra uma fonte de dados abstrata (`DataSource`, injetada). Aplica defesa em profundidade (nunca confia que o chamador ja checou a autorizacao ou o operador), estima custo via `dry_run` antes de `execute`, e traduz qualquer falha da fonte de dados em uma recusa nomeada. Nao integra com nenhum warehouse real — usa um `DataSource` abstrato, com uma implementacao falsa em memoria para testes e para uso local ate uma decisao de integracao real (ADR futuro).

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: `catalogo_semantico` (pacote irmao, para os tipos `AccessDecision`/`MetricDefinitionVersion`); nenhuma dependencia de rede/banco nesta feature.

**Storage**: N/A — a fonte de dados e um port abstrato injetado pelo chamador; nenhum estado proprio.

**Testing**: `pytest`, com uma `FakeDataSource` em memoria para exercitar `dry_run`/`execute` de forma deterministica.

**Target Platform**: Biblioteca Python standalone, consumida por pacotes futuros (ex.: interacao conversacional).

**Project Type**: Library (pacote Python independente dentro do monorepo `packages/`).

**Performance Goals**: A validacao (autorizacao, operador, dimensao, dry-run) deve ser negligivel (memoria); o tempo de `execute()` depende inteiramente da implementacao real de `DataSource`, fora do controle desta feature.

**Constraints**: Zero chamada a `execute()` quando qualquer checagem anterior falha (SC-001..SC-003); `DataSource` deve ser estruturalmente somente-leitura (FR-008); nenhuma excecao da fonte de dados pode escapar de `executar()` (FR-007, SC-004).

**Scale/Scope**: Um unico ponto de entrada (`executar()`), um port (`DataSource`), e uma implementacao falsa para teste/uso local.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | Recusa por padrao quando a decisao nao e "permitido" (FR-001, defesa em profundidade); allowlist de operador reforcada aqui de novo, nao so confiada do chamador (FR-002). | PASS |
| II. Deterministic First | Toda a logica de decisao (autorizar/recusar) e deterministica; nenhum LLM envolvido. | PASS |
| III. Provenance or Abstention | `QueryResult` carrega `source_view` e unidade (base da proveniencia que o pacote de interacao usara); recusas sao sempre nomeadas, nunca silenciosas. | PASS |
| IV. Least Privilege | `DataSource` e estruturalmente somente-leitura (FR-008) — nenhum metodo de escrita existe na interface. | PASS |
| V. Idempotent, Auditable Delivery | Nao aplicavel diretamente (sem mensageria nesta feature); N/A justificado. | PASS (N/A) |

Nenhuma violacao identificada. Nenhum item em Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/002-execucao-query/
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
└── execucao_query/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── execucao_query/
    │       ├── __init__.py
    │       ├── modelos.py        # QueryFilter, QueryRequest, CostEstimate, QueryResult, ExecutionOutcome, DataSource (Protocol)
    │       ├── executor.py       # executar(): validacao + dry-run + execute
    │       └── fake_data_source.py  # FakeDataSource para testes e uso local
    └── tests/
        └── unit/
            ├── conftest.py
            ├── test_executa_com_sucesso.py
            ├── test_recusa_autorizacao_e_operador.py
            ├── test_recusa_por_teto_de_custo.py
            └── test_falha_da_fonte_de_dados.py
```

**Structure Decision**: segundo pacote do monorepo `packages/`, seguindo o mesmo padrao de `catalogo_semantico`. Depende de `catalogo_semantico` apenas pelos tipos de dominio (`AccessDecision`, `MetricDefinitionVersion`) — sem depender de `carregar_catalogo` nem de nenhum detalhe de carregamento do catalogo.

## Complexity Tracking

Nenhuma violacao da Constitution identificada nesta feature. Tabela nao aplicavel.
