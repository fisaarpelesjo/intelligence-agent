# Implementation Plan: Priorizacao de insights

**Branch**: `006-priorizacao-insights` | **Date**: 2026-09-08 | **Spec**: `specs/006-priorizacao-insights/spec.md`

**Input**: Feature specification from `specs/006-priorizacao-insights/spec.md`

## Summary

Construir uma biblioteca Python pura, sem nenhuma dependencia de outros pacotes do monorepo (nem `catalogo_semantico`, nem `execucao_query`), que recebe uma lista de `InsightCandidate` e retorna um `PrioritizationOutcome`: os priorizaveis ordenados por comparacao de tupla `(magnitude*confidence, reach*confidence)`, e os nao-priorizaveis com motivo nomeado (confianca ou alcance desconhecidos).

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: nenhuma alem da stdlib.

**Storage**: N/A.

**Testing**: `pytest`.

**Target Platform**: Biblioteca Python standalone.

**Project Type**: Library (sexto pacote do monorepo — o primeiro sem dependencia de outro pacote).

**Performance Goals**: Ordenacao O(n log n) trivial; sem I/O.

**Constraints**: Nunca combinar magnitude/confianca/alcance num unico score (FR-002, SC-004); confianca/alcance ausentes nunca assumem valor padrao (FR-003, FR-004).

**Scale/Scope**: Uma funcao publica (`priorizar`), tres tipos de dado.

## Constitution Check

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | N/A — nao le nenhum dado de negocio, opera sobre estrutura ja fornecida. | PASS (N/A) |
| II. Deterministic First | Ordenacao e comparacao de tupla sao deterministicas; sem LLM. | PASS |
| III. Provenance or Abstention | Todo insight nao-priorizavel carrega motivo nomeado; nenhum e descartado silenciosamente (FR-006). | PASS |
| IV. Least Privilege | N/A — sem acesso a dado externo. | PASS (N/A) |
| V. Idempotent, Auditable Delivery | N/A — sem mensageria nesta feature. | PASS (N/A) |

Nenhuma violacao identificada.

## Project Structure

### Documentation (this feature)

```text
specs/006-priorizacao-insights/
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
└── priorizacao_insights/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── priorizacao_insights/
    │       ├── __init__.py
    │       ├── modelos.py       # InsightCandidate, PrioritizedInsight, NotPrioritisableInsight, PrioritizationOutcome
    │       └── priorizacao.py   # priorizar()
    └── tests/
        └── unit/
            ├── test_ordena_por_tupla.py
            ├── test_confianca_desconhecida.py
            └── test_alcance_desconhecido.py
```

**Structure Decision**: sexto pacote do monorepo — o primeiro sem nenhuma dependencia de outro pacote (fronteira mais simples possivel: entrada estruturada, saida estruturada, zero I/O).

## Complexity Tracking

Nenhuma violacao da Constitution identificada. Tabela nao aplicavel.
