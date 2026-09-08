# Implementation Plan: Integracao de canal

**Branch**: `007-integracao-canal` | **Date**: 2026-09-08 | **Spec**: `specs/007-integracao-canal/spec.md`

**Input**: Feature specification from `specs/007-integracao-canal/spec.md`

## Summary

Construir uma biblioteca Python pura com duas capacidades independentes: resolucao de identidade (`resolver_identidade`, via uma porta `IdentityRegistry` e uma implementacao fake em memoria) e planejamento/entrega de mensagens respeitando a capacidade do canal (`planejar_entrega`, `entregar`, via uma porta `Channel` e uma implementacao fake que apenas coleciona o que foi enviado). Nenhuma integracao com Telegram/WhatsApp/etc. — ADR-0001.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: nenhuma alem da stdlib.

**Storage**: N/A (registro e canal fakes sao em memoria).

**Testing**: `pytest`.

**Target Platform**: Biblioteca Python standalone.

**Project Type**: Library (setimo pacote do monorepo).

**Performance Goals**: Negligivel — operacoes em memoria.

**Constraints**: Nunca dividir uma sentenca no meio (FR-003); nunca usar o identificador bruto do canal como identidade (FR-001, FR-006).

**Scale/Scope**: Duas funcoes publicas (`resolver_identidade`, `planejar_entrega`) mais `entregar` que as compoe.

## Constitution Check

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | N/A — nao acessa dado de negocio. | PASS (N/A) |
| II. Deterministic First | Resolucao de identidade e planejamento de entrega sao deterministicos; sem LLM. | PASS |
| III. Provenance or Abstention | Toda recusa (sentenca excede capacidade, canal sem suporte a multiplas mensagens, falha de envio) e nomeada. | PASS |
| IV. Least Privilege | Identidade de canal nunca e usada como identidade interna (FR-001, FR-006) — reforca least privilege de identidade. | PASS |
| V. Idempotent, Auditable Delivery | Resolucao de identidade e idempotente (FR-002); entrega nunca envia parcialmente quando o canal nao suporta (FR-005). | PASS |

Nenhuma violacao identificada.

## Project Structure

### Documentation (this feature)

```text
specs/007-integracao-canal/
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
└── integracao_canal/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── integracao_canal/
    │       ├── __init__.py
    │       ├── modelos.py         # ChannelCapability, DeliveryPlan, DeliveryOutcome, Channel, IdentityRegistry (Protocols)
    │       ├── identidade.py      # resolver_identidade(), FakeIdentityRegistry
    │       ├── entrega.py         # planejar_entrega(), entregar()
    │       └── fake_channel.py    # FakeChannel
    └── tests/
        └── unit/
            ├── test_resolve_identidade.py
            ├── test_planeja_entrega.py
            └── test_canal_sem_multiplas_mensagens.py
```

**Structure Decision**: setimo pacote do monorepo, sem dependencia de nenhum outro pacote (mesma categoria de `priorizacao_insights`) — biblioteca pura de fronteira.

## Complexity Tracking

Nenhuma violacao da Constitution identificada. Tabela nao aplicavel.
