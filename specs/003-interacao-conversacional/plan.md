# Implementation Plan: Interacao conversacional

**Branch**: `003-interacao-conversacional` | **Date**: 2026-09-07 | **Spec**: `specs/003-interacao-conversacional/spec.md`

**Input**: Feature specification from `specs/003-interacao-conversacional/spec.md`

## Summary

Construir uma biblioteca Python pura que orquestra `catalogo_semantico` e `execucao_query` para responder uma `QuestionIntent` ja estruturada: resolve a expressao de periodo contra um vocabulario fechado, autoriza, executa, opcionalmente compara contra um periodo baseline (com as duas regras de seguranca — janela comparavel e baseline nao-zero), classifica cada sentenca da resposta, e monta um payload de narracao estritamente limitado a evidencia agregada antes de chamar um `LLMProvider` (stub para o MVP, ADR-0005).

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: `catalogo_semantico`, `execucao_query` (pacotes irmaos).

**Storage**: N/A.

**Testing**: `pytest`, com `FakeDataSource` (de `execucao_query`) e um `LLMProviderStub` proprio, deterministico.

**Target Platform**: Biblioteca Python standalone.

**Project Type**: Library (terceiro pacote do monorepo `packages/`).

**Performance Goals**: Negligivel (memoria) alem do tempo de `execucao_query`, ja fora do controle desta feature.

**Constraints**: Zero calculo numerico dentro do `LLMProvider` (FR-008); `NarrationPayload` deve ser uma estrutura fechada sem campo de identidade/texto-livre (FR-007, SC-006).

**Scale/Scope**: Um ponto de entrada (`responder()`), resolucao de vocabulario de periodo, formula de comparacao, classificador de claim, e um `LLMProviderStub`.

## Constitution Check

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | Delega inteiramente a `catalogo_semantico`/`execucao_query`; nao contorna nenhuma checagem delas. | PASS |
| II. Deterministic First | Resolucao de periodo, comparacao e classificacao de claim sao 100% deterministicas; `LLMProvider` so narra um payload ja calculado (FR-008). | PASS |
| III. Provenance or Abstention | Toda resposta tem proveniencia ou abstencao nomeada (SC-002); janela nao comparavel e baseline zero sao recusados explicitamente (FR-004, FR-005). | PASS |
| IV. Least Privilege | `NarrationPayload` e estruturalmente fechado, sem identidade/credencial/texto-livre (FR-007, SC-006). | PASS |
| V. Idempotent, Auditable Delivery | N/A nesta feature (sem mensageria); justificado. | PASS (N/A) |

Nenhuma violacao identificada.

## Project Structure

### Documentation (this feature)

```text
specs/003-interacao-conversacional/
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
└── interacao_conversacional/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── interacao_conversacional/
    │       ├── __init__.py
    │       ├── modelos.py          # QuestionIntent, ResolvedPeriod, ComparisonResult, NarrationPayload, ClaimSentence, AnswerOutcome
    │       ├── vocabulario_periodo.py  # resolve expressao de periodo -> ResolvedPeriod | None
    │       ├── comparacao.py       # percentage_change com recusa de baseline zero
    │       ├── orquestrador.py     # responder(): pipeline completo
    │       └── llm_provider_stub.py  # LLMProviderStub (ADR-0005)
    └── tests/
        └── unit/
            ├── conftest.py
            ├── test_responde_com_provenencia.py
            ├── test_vocabulario_de_periodo.py
            ├── test_comparacao_invalida.py
            └── test_narracao_sem_dado_sensivel.py
```

**Structure Decision**: terceiro pacote do monorepo, dependente de `catalogo_semantico` e `execucao_query` — nenhuma dependencia circular (fronteira unidirecional: `interacao_conversacional -> execucao_query -> catalogo_semantico`).

## Complexity Tracking

Nenhuma violacao da Constitution identificada. Tabela nao aplicavel.
