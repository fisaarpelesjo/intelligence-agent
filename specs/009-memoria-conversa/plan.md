# Implementation Plan: Memoria de conversa

**Branch**: `009-memoria-conversa` | **Date**: 2026-09-08 | **Spec**: `specs/009-memoria-conversa/spec.md`

**Input**: Feature specification from `specs/009-memoria-conversa/spec.md`

## Summary

Construir uma biblioteca Python pura com uma memoria de turno de conversa em memoria (`InMemoryConversationMemory`), indexada por `RegistryRef` (tipo de `integracao_canal`), com expiracao por janela de retencao configurada, e uma funcao `processar_mensagem_inbound()` que sempre recusa e que, por assinatura, nao tem como acessar a memoria — tornando o desligamento do inbound uma garantia estrutural, nao apenas comportamental.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: `integracao-canal` (apenas pelo tipo `RegistryRef`).

**Storage**: Em memoria (dict), nao persistida entre processos nesta versao.

**Testing**: `pytest`, incluindo um teste de assinatura (`inspect.signature`) para a garantia estrutural do inbound.

**Target Platform**: Biblioteca Python standalone.

**Project Type**: Library (nono e ultimo pacote do pipeline original do PRD).

**Performance Goals**: Negligivel — operacoes em memoria sobre uma lista por identidade.

**Constraints**: `processar_mensagem_inbound()` nunca aceita uma referencia a `ConversationMemory` (FR-004); expiracao e sempre relativa a um `reference_now` injetado, nunca `datetime.now()` direto.

**Scale/Scope**: Dois pontos de entrada publicos (`registrar_turno`/`turnos_recentes` como metodos da memoria, e `processar_mensagem_inbound` como funcao livre).

## Constitution Check

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | N/A — nao acessa dado de negocio. | PASS (N/A) |
| II. Deterministic First | Armazenamento e filtragem por idade sao deterministicos; sem LLM. | PASS |
| III. Provenance or Abstention | `processar_mensagem_inbound` sempre retorna motivo nomeado explicito, nunca silencioso. | PASS |
| IV. Least Privilege | Memoria indexada por `RegistryRef`, nunca por identificador bruto de canal (FR-001); inbound estruturalmente sem acesso a memoria (FR-004) — reforca least privilege. | PASS |
| V. Idempotent, Auditable Delivery | N/A — sem mensageria nesta feature. | PASS (N/A) |

Nenhuma violacao identificada.

## Project Structure

### Documentation (this feature)

```text
specs/009-memoria-conversa/
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
└── memoria_conversa/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── memoria_conversa/
    │       ├── __init__.py
    │       ├── modelos.py      # ConversationTurn, InboundOutcome
    │       ├── memoria.py      # InMemoryConversationMemory
    │       └── inbound.py      # processar_mensagem_inbound()
    └── tests/
        └── unit/
            ├── test_registra_e_recupera_turno.py
            ├── test_turno_expira_fora_da_janela.py
            └── test_inbound_sempre_recusado.py
```

**Structure Decision**: nono pacote do monorepo, dependente apenas de `integracao_canal` (pelo tipo `RegistryRef`) — ultimo recorte do pipeline original de 9 pacotes do PRD.

## Complexity Tracking

Nenhuma violacao da Constitution identificada. Tabela nao aplicavel.
