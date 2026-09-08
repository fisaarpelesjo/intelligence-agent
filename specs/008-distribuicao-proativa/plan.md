# Implementation Plan: Distribuicao proativa

**Branch**: `008-distribuicao-proativa` | **Date**: 2026-09-08 | **Spec**: `specs/008-distribuicao-proativa/spec.md`

**Input**: Feature specification from `specs/008-distribuicao-proativa/spec.md`

## Summary

Construir uma biblioteca Python pura que aplica o gate de 3 condicoes (finding priorizavel, canal habilitado, destinatario na allow-list) e, somente quando todas passam, monta uma mensagem de campos rotulados a partir de um `PrioritizedInsight` (de `priorizacao_insights`) e chama `integracao_canal.entregar()` para envia-la.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: `priorizacao_insights`, `integracao_canal`.

**Storage**: N/A.

**Testing**: `pytest`, com `FakeChannel`/`FakeIdentityRegistry` de `integracao_canal`.

**Target Platform**: Biblioteca Python standalone.

**Project Type**: Library (oitavo pacote do monorepo).

**Performance Goals**: Negligivel — sem I/O real.

**Constraints**: `entregar()` nunca e chamado quando qualquer condicao do gate falha (FR-005); mensagem sempre em campos rotulados (FR-006).

**Scale/Scope**: Uma funcao publica (`distribuir`).

## Constitution Check

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | N/A — nao acessa dado de negocio diretamente. | PASS (N/A) |
| II. Deterministic First | Gate e montagem de mensagem sao deterministicos; sem LLM. | PASS |
| III. Provenance or Abstention | Toda recusa e nomeada; mensagem originada carrega os campos do insight (proveniencia rastreavel ao rank/scores). | PASS |
| IV. Least Privilege | Reusa `integracao_canal` para nunca usar identidade bruta do canal. | PASS |
| V. Idempotent, Auditable Delivery | Gate de 3 condicoes e a garantia central deste principio (PRD FR-007); reusa a entrega idempotente/estruturada de `integracao_canal`. | PASS |

Nenhuma violacao identificada.

## Project Structure

### Documentation (this feature)

```text
specs/008-distribuicao-proativa/
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
└── distribuicao_proativa/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── distribuicao_proativa/
    │       ├── __init__.py
    │       ├── modelos.py       # ChannelGateConfig, DistributionOutcome
    │       └── distribuicao.py  # distribuir()
    └── tests/
        └── unit/
            ├── test_origina_com_as_3_condicoes.py
            ├── test_recusa_por_condicao.py
            └── test_mensagem_com_campos_rotulados.py
```

**Structure Decision**: oitavo pacote do monorepo, dependente de `priorizacao_insights` e `integracao_canal` — nenhuma dependencia de `catalogo_semantico`/`execucao_query` diretamente.

## Complexity Tracking

Nenhuma violacao da Constitution identificada. Tabela nao aplicavel.
