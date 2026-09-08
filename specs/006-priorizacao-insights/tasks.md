---

description: "Tasks: priorizacao de insights"
---

# Tasks: Priorizacao de insights

**Input**: `specs/006-priorizacao-insights/plan.md`, `spec.md`, `data-model.md`, `contracts/priorizar.md`, `quickstart.md`

**Tests**: incluidos.

## Phase 1: Setup

- [ ] T001 Criar `packages/priorizacao_insights/` com `pyproject.toml` (sem dependencia de outro pacote do monorepo), `src/priorizacao_insights/__init__.py`, `tests/unit/`
- [ ] T002 [P] Adicionar `priorizacao-insights` como dependencia do projeto raiz e rodar `uv sync`

## Phase 2: Foundational

- [ ] T003 Implementar `InsightCandidate`, `PrioritizedInsight`, `NotPrioritisableInsight`, `PrioritizationOutcome` em `modelos.py` (per `data-model.md`)

**Checkpoint**: tipos prontos.

---

## Phase 3: User Story 1 - Ordenar por tupla, nunca score unico (Priority: P1) 🎯 MVP

### Tests for User Story 1 ⚠️

- [ ] T004 [P] [US1] `test_ordena_por_tupla.py`: cenarios 1-3 (ordem por impact_score, desempate por reach_score, lista vazia)

### Implementation for User Story 1

- [ ] T005 [US1] Implementar `priorizar()` — calculo de impact_score/reach_score e ordenacao por tupla em `priorizacao.py` (depende de T003) — FR-001, FR-002, FR-005, FR-006

**Checkpoint**: US1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Confianca desconhecida nunca prioriza (Priority: P1)

### Tests for User Story 2 ⚠️

- [ ] T006 [P] [US2] `test_confianca_desconhecida.py`: cenario 1 (confidence=None -> not_prioritisable, motivo confidence_unknown)

### Implementation for User Story 2

- [ ] T007 [US2] Implementar a checagem de `confidence is None` em `priorizacao.py` (depende de T005) — FR-003

**Checkpoint**: US1 e US2 funcionam juntas.

---

## Phase 5: User Story 3 - Alcance desconhecido nunca prioriza (Priority: P2)

### Tests for User Story 3 ⚠️

- [ ] T008 [P] [US3] `test_alcance_desconhecido.py`: cenario 1 (reach=None com confidence presente -> not_prioritisable, motivo reach_unknown) + edge case (ambos None -> confidence_unknown)

### Implementation for User Story 3

- [ ] T009 [US3] Implementar a checagem de `reach is None` em `priorizacao.py` (depende de T007) — FR-004

**Checkpoint**: todas as 3 user stories testadas.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T010 [P] Escrever `packages/priorizacao_insights/README.md` com o conteudo de `quickstart.md`
- [ ] T011 Rodar o gate completo: `ruff format --check`, `ruff check`, `pyright`, `pytest`, `engineering-playbook verify`
- [ ] T012 Rodar `engineering-playbook delivery prepare`/`commit`/`publish`/`merge --auto` para converger este recorte

---

## Dependencies & Execution Order

Setup -> Foundational -> US1 -> US2 -> US3 -> Polish. US2 e US3 dependem de US1 (mesma `priorizar()`, camadas adicionais de checagem).

## Implementation Strategy

MVP = Fases 1-3 (US1). Branch `feat/006-priorizacao-insights`.
