---

description: "Tasks: deteccao de anomalia"
---

# Tasks: Deteccao de anomalia

**Input**: `specs/005-deteccao-anomalia/plan.md`, `spec.md`, `data-model.md`, `contracts/detectar.md`, `quickstart.md`

**Tests**: incluidos.

## Phase 1: Setup

- [ ] T001 Criar `packages/deteccao_anomalia/` com `pyproject.toml` (dependencias `catalogo-semantico`, `execucao-query`), `src/deteccao_anomalia/__init__.py`, `tests/unit/`
- [ ] T002 [P] Adicionar `deteccao-anomalia` como dependencia do projeto raiz e rodar `uv sync`

## Phase 2: Foundational

- [ ] T003 Implementar `AnomalyRule`, `Direction`, `CandidateFinding`, `DetectionOutcome` em `modelos.py` (per `data-model.md`)
- [ ] T004 [P] Implementar `_execucao.py`: helper de execucao por dia (mesmo padrao de `relatorio_periodico/_execucao.py`)

**Checkpoint**: tipos e helper prontos.

---

## Phase 3: User Story 1 - Detectar desvio acima do limiar (Priority: P1) 🎯 MVP

### Tests for User Story 1 ⚠️

- [ ] T005 [P] [US1] `test_detecta_desvio_acima_do_limiar.py`: cenarios 1-2 (aumento e queda disparam com direcao correta)

### Implementation for User Story 1

- [ ] T006 [US1] Implementar `detectar()` — calculo de baseline (media dos `window_days` dias) e desvio percentual em `deteccao.py` (depende de T003, T004) — FR-001, FR-003, FR-005

**Checkpoint**: US1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Nao detectar dentro do limiar / baseline invalida (Priority: P1)

### Tests for User Story 2 ⚠️

- [ ] T007 [P] [US2] `test_nao_detecta_dentro_do_limiar.py`: cenarios 1-3 (dentro do limiar, baseline incompleta, baseline zero) + edge cases (observado indisponivel, janela invalida)

### Implementation for User Story 2

- [ ] T008 [US2] Implementar as recusas nomeadas (`observado_indisponivel`, `baseline_incompleta`, `baseline_zero`, `janela_invalida`) em `deteccao.py` (depende de T006) — FR-002, FR-004

**Checkpoint**: US1 e US2 funcionam juntas e isoladamente.

---

## Phase 5: User Story 3 - Nunca se auto-origina (Priority: P1)

### Tests for User Story 3 ⚠️

- [ ] T009 [P] [US3] `test_sem_auto_origem.py`: percorre `packages/deteccao_anomalia/src` com `ast` e falha se `threading`, `sched` ou `time` forem importados — FR-006

**Checkpoint**: todas as 3 user stories testadas.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T010 [P] Escrever `packages/deteccao_anomalia/README.md` com o conteudo de `quickstart.md`
- [ ] T011 Rodar o gate completo: `ruff format --check`, `ruff check`, `pyright`, `pytest`, `engineering-playbook verify`
- [ ] T012 Rodar `engineering-playbook delivery prepare`/`commit`/`publish`/`merge --auto` para converger este recorte

---

## Dependencies & Execution Order

Setup -> Foundational -> US1 -> US2 -> US3 -> Polish. US2 depende de US1 (mesma `detectar()`). US3 e uma verificacao estrutural independente.

## Implementation Strategy

MVP = Fases 1-3 (US1). Branch `feat/005-deteccao-anomalia`.
