---

description: "Tasks: memoria de conversa"
---

# Tasks: Memoria de conversa

**Input**: `specs/009-memoria-conversa/plan.md`, `spec.md`, `data-model.md`, `contracts/memoria.md`, `quickstart.md`

**Tests**: incluidos.

## Phase 1: Setup

- [ ] T001 Criar `packages/memoria_conversa/` com `pyproject.toml` (dependencia `integracao-canal`), `src/memoria_conversa/__init__.py`, `tests/unit/`
- [ ] T002 [P] Adicionar `memoria-conversa` como dependencia do projeto raiz e rodar `uv sync`

## Phase 2: Foundational

- [ ] T003 Implementar `ConversationTurn`, `InboundOutcome` em `modelos.py` (per `data-model.md`)

**Checkpoint**: tipos prontos.

---

## Phase 3: User Story 1 - Registrar e recuperar turno (Priority: P1) 🎯 MVP

### Tests for User Story 1 ⚠️

- [ ] T004 [P] [US1] `test_registra_e_recupera_turno.py`: cenarios 1-2 (recupera o proprio turno; isola por identidade)

### Implementation for User Story 1

- [ ] T005 [US1] Implementar `InMemoryConversationMemory` (dict interno por `registry_ref`) em `memoria.py` (depende de T003) — FR-001, FR-005

**Checkpoint**: US1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Turno expira fora da janela (Priority: P1)

### Tests for User Story 2 ⚠️

- [ ] T006 [P] [US2] `test_turno_expira_fora_da_janela.py`: cenarios 1-2 (expira fora da janela, presente dentro de janela maior) + edge case (janela zero/negativa -> vazio)

### Implementation for User Story 2

- [ ] T007 [US2] Implementar o filtro por `max_age` em `turnos_recentes()` (depende de T005) — FR-002, FR-005

**Checkpoint**: US1 e US2 funcionam juntas.

---

## Phase 5: User Story 3 - Inbound sempre recusado, sem acesso a memoria (Priority: P1)

### Tests for User Story 3 ⚠️

- [ ] T008 [P] [US3] `test_inbound_sempre_recusado.py`: cenarios 1-2 (recusa sempre; assinatura sem parametro `ConversationMemory`, via `inspect.signature`)

### Implementation for User Story 3

- [ ] T009 [US3] Implementar `processar_mensagem_inbound()` em `inbound.py`, aceitando apenas `payload: object` — FR-003, FR-004

**Checkpoint**: todas as 3 user stories testadas.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T010 [P] Escrever `packages/memoria_conversa/README.md` com o conteudo de `quickstart.md`
- [ ] T011 Rodar o gate completo: `ruff format --check`, `ruff check`, `pyright`, `pytest`, `engineering-playbook verify`
- [ ] T012 Rodar `engineering-playbook delivery prepare`/`commit`/`publish`/`merge --auto` para converger este recorte — ultimo do pipeline original de 9 pacotes do PRD

---

## Dependencies & Execution Order

Setup -> Foundational -> US1 -> US2 -> US3 -> Polish. US2 depende de US1 (mesma memoria). US3 e independente (modulo `inbound.py` separado).

## Implementation Strategy

MVP = Fases 1-3 (US1). Branch `feat/009-memoria-conversa`.
