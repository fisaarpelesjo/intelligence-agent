---

description: "Tasks: relatorio periodico"
---

# Tasks: Relatorio periodico

**Input**: `specs/004-relatorio-periodico/plan.md`, `spec.md`, `data-model.md`, `contracts/relatorio-e-alerta.md`, `quickstart.md`

**Tests**: incluidos.

## Phase 1: Setup

- [x] T001 Criar `packages/relatorio_periodico/` com `pyproject.toml` (dependencias `catalogo-semantico`, `execucao-query`), `src/relatorio_periodico/__init__.py`, `tests/unit/`
- [x] T002 [P] Adicionar `relatorio-periodico` como dependencia do projeto raiz e rodar `uv sync`

## Phase 2: Foundational

- [x] T003 Implementar `KpiDefinition`, `KpiResult`, `DailyReport`, `AlertDirection`, `AlertRule`, `AlertResult`, `AlertBundle` em `modelos.py` (per `data-model.md`, campos sem sobreposicao entre `DailyReport` e `AlertBundle`)
- [x] T004 [P] Implementar helper compartilhado (nao publico) que executa autorizacao+execucao para um `metric_id`/dimensao/dia e retorna valor ou motivo de indisponibilidade, reusado por `relatorio.py` e `alerta.py`

**Checkpoint**: tipos e helper prontos.

---

## Phase 3: User Story 1 - Gerar relatorio diario (Priority: P1) 🎯 MVP

### Tests for User Story 1 ⚠️

- [x] T005 [P] [US1] `test_relatorio_diario.py`: cenarios 1-2 (todos disponiveis; um indisponivel sem abortar)

### Implementation for User Story 1

- [x] T006 [US1] Implementar `gerar_relatorio_diario()` em `relatorio.py` (depende de T003, T004) — FR-001, FR-002

**Checkpoint**: US1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Avaliar alertas independente do relatorio (Priority: P1)

### Tests for User Story 2 ⚠️

- [x] T007 [P] [US2] `test_avaliacao_de_alertas.py`: cenarios 1-3 (dispara acima do limiar, nao dispara abaixo, metrica indisponivel nao avalia)

### Implementation for User Story 2

- [x] T008 [US2] Implementar `avaliar_alertas()` em `alerta.py` (depende de T003, T004) — FR-003, FR-004

**Checkpoint**: US1 e US2 funcionam de forma independente.

---

## Phase 5: User Story 3 - Relatorio e alerta nunca se fundem (Priority: P2)

### Tests for User Story 3 ⚠️

- [x] T009 [P] [US3] `test_relatorio_e_alerta_nao_se_fundem.py`: `dataclasses.fields()` de `DailyReport` e `AlertBundle` nao tem nomes em comum; nenhuma funcao publica do pacote retorna os dois combinados

**Checkpoint**: todas as 3 user stories testadas.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T010 [P] Escrever `packages/relatorio_periodico/README.md` com o conteudo de `quickstart.md`
- [x] T011 Rodar o gate completo: `ruff format --check`, `ruff check`, `pyright`, `pytest`, `engineering-playbook verify`
- [x] T012 Rodar `engineering-playbook delivery prepare`/`commit`/`publish`/`merge --auto` para converger este recorte

---

## Dependencies & Execution Order

Setup -> Foundational -> US1 -> US2 -> US3 -> Polish. US1 e US2 sao independentes entre si (ambas dependem so da Foundational); US3 e uma verificacao estrutural sobre ambas.

## Implementation Strategy

MVP = Fases 1-3 (US1). Branch `feat/004-relatorio-periodico`.
