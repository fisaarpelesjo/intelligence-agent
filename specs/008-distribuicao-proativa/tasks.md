---

description: "Tasks: distribuicao proativa"
---

# Tasks: Distribuicao proativa

**Input**: `specs/008-distribuicao-proativa/plan.md`, `spec.md`, `data-model.md`, `contracts/distribuir.md`, `quickstart.md`

**Tests**: incluidos.

## Phase 1: Setup

- [ ] T001 Criar `packages/distribuicao_proativa/` com `pyproject.toml` (dependencias `priorizacao-insights`, `integracao-canal`), `src/distribuicao_proativa/__init__.py`, `tests/unit/`
- [ ] T002 [P] Adicionar `distribuicao-proativa` como dependencia do projeto raiz e rodar `uv sync`

## Phase 2: Foundational

- [ ] T003 Implementar `ChannelGateConfig`, `DistributionOutcome` em `modelos.py` (per `data-model.md`)

**Checkpoint**: tipos prontos.

---

## Phase 3: User Story 1 - Originar com as 3 condicoes (Priority: P1) 🎯 MVP

### Tests for User Story 1 ⚠️

- [ ] T004 [P] [US1] `test_origina_com_as_3_condicoes.py`: cenario 1 (todas as condicoes verdadeiras -> originado e entregue)

### Implementation for User Story 1

- [ ] T005 [US1] Implementar `distribuir()` — gate + montagem de campos rotulados + chamada a `integracao_canal.entregar()` em `distribuicao.py` (depende de T003) — FR-001, FR-006

**Checkpoint**: US1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Recusar por qualquer condicao (Priority: P1)

### Tests for User Story 2 ⚠️

- [ ] T006 [P] [US2] `test_recusa_por_condicao.py`: cenarios 1-3 (insight None, canal desabilitado, destinatario fora da allow-list) — cada um verificando `channel.sent == []`

### Implementation for User Story 2

- [ ] T007 [US2] Implementar as 3 checagens em curto-circuito em `distribuir()` (depende de T005) — FR-002, FR-003, FR-004, FR-005

**Checkpoint**: US1 e US2 funcionam juntas.

---

## Phase 5: User Story 3 - Mensagem com campos rotulados (Priority: P2)

### Tests for User Story 3 ⚠️

- [ ] T008 [P] [US3] `test_mensagem_com_campos_rotulados.py`: cenario 1 (toda sentenca enviada segue `"rotulo: valor"`)

**Checkpoint**: todas as 3 user stories testadas.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T009 [P] Escrever `packages/distribuicao_proativa/README.md` com o conteudo de `quickstart.md`
- [ ] T010 Rodar o gate completo: `ruff format --check`, `ruff check`, `pyright`, `pytest`, `engineering-playbook verify`
- [ ] T011 Rodar `engineering-playbook delivery prepare`/`commit`/`publish`/`merge --auto` para converger este recorte

---

## Dependencies & Execution Order

Setup -> Foundational -> US1 -> US2 -> US3 -> Polish. US2 e US3 dependem de US1 (mesma `distribuir()`).

## Implementation Strategy

MVP = Fases 1-3 (US1). Branch `feat/008-distribuicao-proativa`.
