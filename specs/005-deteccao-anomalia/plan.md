# Implementation Plan: Deteccao de anomalia

**Branch**: `005-deteccao-anomalia` | **Date**: 2026-09-08 | **Spec**: `specs/005-deteccao-anomalia/spec.md`

**Input**: Feature specification from `specs/005-deteccao-anomalia/spec.md`

## Summary

Construir uma biblioteca Python pura que calcula uma baseline de media movel (N dias anteriores ao dia observado) para uma metrica, compara com o valor observado, e produz um `CandidateFinding` quando o desvio percentual ultrapassa um limiar configurado — sem afirmar causa, sem escrever nada, e sem importar nenhum modulo de scheduling/timer/thread (garantido por teste de AST). Reusa `catalogo_semantico`/`execucao_query` do mesmo jeito que `relatorio_periodico`, com seu proprio helper de execucao por dia.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: `catalogo_semantico`, `execucao_query`.

**Storage**: N/A.

**Testing**: `pytest` + `FakeDataSource`; um teste de AST (`ast` da stdlib) para a garantia de nao-auto-origem.

**Target Platform**: Biblioteca Python standalone.

**Project Type**: Library (quinto pacote do monorepo).

**Performance Goals**: Negligivel alem de `window_days + 1` chamadas a `execucao_query` por avaliacao.

**Constraints**: Baseline nunca parcial (FR-002); zero import de `threading`/`sched`/`time` (FR-006, verificado por teste, nao so por revisao).

**Scale/Scope**: Uma funcao publica (`detectar`), tipos de regra/finding/resultado.

## Constitution Check

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | Reusa `catalogo_semantico`/`execucao_query` sem contornar nenhuma checagem. | PASS |
| II. Deterministic First | Media movel e desvio percentual sao calculos deterministicos simples; nenhum LLM envolvido. | PASS |
| III. Provenance or Abstention | `DetectionOutcome` sempre carrega o motivo quando nao dispara por indisponibilidade; finding carrega os parametros da regra aplicada. | PASS |
| IV. Least Privilege | Somente leitura via `execucao_query`. | PASS |
| V. Idempotent, Auditable Delivery | N/A nesta feature (sem mensageria); justificado. | PASS (N/A) |

Nenhuma violacao identificada. A regra de baseline em si (ADR-0006) e uma decisao de produto `Proposed`, nao uma violacao de principio.

## Project Structure

### Documentation (this feature)

```text
specs/005-deteccao-anomalia/
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
└── deteccao_anomalia/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── deteccao_anomalia/
    │       ├── __init__.py
    │       ├── modelos.py       # AnomalyRule, CandidateFinding, DetectionOutcome
    │       ├── _execucao.py     # helper de execucao por dia (mesmo padrao de relatorio_periodico)
    │       └── deteccao.py      # detectar(): baseline + comparacao
    └── tests/
        └── unit/
            ├── conftest.py
            ├── test_detecta_desvio_acima_do_limiar.py
            ├── test_nao_detecta_dentro_do_limiar.py
            └── test_sem_auto_origem.py
```

**Structure Decision**: quinto pacote do monorepo, dependente apenas de `catalogo_semantico` e `execucao_query` — mesma fronteira de `relatorio_periodico`, sem depender de `interacao_conversacional`.

## Complexity Tracking

Nenhuma violacao da Constitution identificada. Tabela nao aplicavel.
