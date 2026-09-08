---

description: "Tasks: integracao de canal"
---

# Tasks: Integracao de canal

**Input**: `specs/007-integracao-canal/plan.md`, `spec.md`, `data-model.md`, `contracts/integracao.md`, `quickstart.md`

**Tests**: incluidos.

## Phase 1: Setup

- [x] T001 Criar `packages/integracao_canal/` com `pyproject.toml` (sem dependencia de outro pacote do monorepo), `src/integracao_canal/__init__.py`, `tests/unit/`
- [x] T002 [P] Adicionar `integracao-canal` como dependencia do projeto raiz e rodar `uv sync`

## Phase 2: Foundational

- [x] T003 Implementar `ChannelCapability`, `DeliveryPlan`, `DeliveryOutcome`, `Channel` (Protocol), `IdentityRegistry` (Protocol) em `modelos.py` (per `data-model.md`)
- [x] T004 [P] Implementar `FakeIdentityRegistry` em `identidade.py` (dict interno, contador incremental por par unico)
- [x] T005 [P] Implementar `FakeChannel` em `fake_channel.py` (coleciona `(registry_ref, texto)` enviados numa lista `sent`)

**Checkpoint**: tipos e fakes prontos.

---

## Phase 3: User Story 1 - Resolver identidade via registro (Priority: P1) 🎯 MVP

### Tests for User Story 1 ⚠️

- [x] T006 [P] [US1] `test_resolve_identidade.py`: cenarios 1-3 (diferente do bruto, idempotente, diferentes brutos -> refs diferentes)

### Implementation for User Story 1

- [x] T007 [US1] Implementar `resolver_identidade()` em `identidade.py` (depende de T003, T004) — FR-001, FR-002, FR-006

**Checkpoint**: US1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Planejar entrega sem resumir ou truncar (Priority: P1)

### Tests for User Story 2 ⚠️

- [x] T008 [P] [US2] `test_planeja_entrega.py`: cenarios 1-2 (multiplos blocos preservam conteudo exato; sentenca isolada excede capacidade -> recusa) + edge case (lista vazia)

### Implementation for User Story 2

- [x] T009 [US2] Implementar `planejar_entrega()` em `entrega.py` (depende de T003) — FR-003, FR-004

**Checkpoint**: US1 e US2 funcionam juntas e isoladamente.

---

## Phase 5: User Story 3 - Canal sem multiplas mensagens recusa (Priority: P2)

### Tests for User Story 3 ⚠️

- [x] T010 [P] [US3] `test_canal_sem_multiplas_mensagens.py`: cenario 1 (recusa sem nenhuma chamada de envio) + edge case de falha de envio (`falha_no_envio`)

### Implementation for User Story 3

- [x] T011 [US3] Implementar `entregar()` em `entrega.py` (compoe `resolver_identidade` + `planejar_entrega` + checagem de `supports_multiple_messages` + envio bloco a bloco com tratamento de excecao) (depende de T007, T009) — FR-005

**Checkpoint**: todas as 3 user stories testadas.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T012 [P] Escrever `packages/integracao_canal/README.md` com o conteudo de `quickstart.md`
- [x] T013 Rodar o gate completo: `ruff format --check`, `ruff check`, `pyright`, `pytest`, `engineering-playbook verify`
- [x] T014 Rodar `engineering-playbook delivery prepare`/`commit`/`publish`/`merge --auto` para converger este recorte

---

## Dependencies & Execution Order

Setup -> Foundational -> US1 -> US2 -> US3 -> Polish. US3 depende de US1 e US2 (compoe as duas).

## Implementation Strategy

MVP = Fases 1-3 (US1). Branch `feat/007-integracao-canal`.
