---

description: "Tasks: execucao de query governada"
---

# Tasks: Execucao de query governada

**Input**: `specs/002-execucao-query/plan.md`, `spec.md`, `data-model.md`, `contracts/executar.md`, `quickstart.md`

**Tests**: incluidos.

## Phase 1: Setup

- [ ] T001 Criar `packages/execucao_query/` com `pyproject.toml`, `src/execucao_query/__init__.py`, `tests/unit/` (per `plan.md`); adicionar dependencia em `catalogo-semantico`
- [ ] T002 [P] Adicionar `catalogo-semantico` como dependencia de `execucao-query` e re-rodar `uv sync` para resolver o workspace

## Phase 2: Foundational

- [ ] T003 Implementar `Operator`, `QueryFilter`, `QueryRequest`, `CostEstimate`, `QueryResult`, `ExecutionOutcome`, `ExecutionReasonCode`, `DataSource` (Protocol) em `packages/execucao_query/src/execucao_query/modelos.py` (per `data-model.md`)
- [ ] T004 [P] Implementar `FakeDataSource` em `packages/execucao_query/src/execucao_query/fake_data_source.py` — retorna estimativas/valores configuraveis no construtor, para uso em teste e localmente

**Checkpoint**: tipos e fake pronta; nenhuma user story pode comecar antes disso.

---

## Phase 3: User Story 1 - Executar uma pergunta ja autorizada (Priority: P1) 🎯 MVP

### Tests for User Story 1 ⚠️

- [ ] T005 [P] [US1] `test_executa_com_sucesso.py`: cenarios 1-2 da spec (com e sem filtro de dimensao)

### Implementation for User Story 1

- [ ] T006 [US1] Implementar `executar()` (checagens 1-2 e 6 do contrato: autorizacao, filtro valido, chamada a `execute`) em `packages/execucao_query/src/execucao_query/executor.py` — FR-001, FR-002, FR-003, FR-006

**Checkpoint**: US1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Recusar operador ou filtro nao permitido (Priority: P1)

### Tests for User Story 2 ⚠️

- [ ] T007 [P] [US2] `test_recusa_autorizacao_e_operador.py`: cenarios 1-2 da spec (operador fora da allowlist; decisao "negado")

### Implementation for User Story 2

- [ ] T008 [US2] Garantir curto-circuito: nenhuma chamada a `data_source` quando a autorizacao ou o operador falham (depende de T006) — SC-001, SC-002

**Checkpoint**: US1 e US2 funcionam juntas e isoladamente.

---

## Phase 5: User Story 3 - Recusar execucao que excederia o teto de custo (Priority: P2)

### Tests for User Story 3 ⚠️

- [ ] T009 [P] [US3] `test_recusa_por_teto_de_custo.py`: cenarios 1-3 da spec (excede bytes, excede linhas, dentro do teto)
- [ ] T010 [P] [US3] `test_falha_da_fonte_de_dados.py`: `dry_run`/`execute` levantando excecao viram recusa nomeada, nunca propagam (edge case da spec)

### Implementation for User Story 3

- [ ] T011 [US3] Implementar checagens 3-5 do contrato (`dry_run`, tetos de bytes/linhas) em `executor.py` (depende de T006) — FR-004, FR-005
- [ ] T012 [US3] Envolver as chamadas a `data_source` em tratamento de excecao, traduzindo para `data_source_unavailable` (depende de T006) — FR-007

**Checkpoint**: todas as 3 user stories funcionais e testadas independentemente.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T013 [P] Escrever `packages/execucao_query/README.md` com o conteudo de `quickstart.md`
- [ ] T014 Rodar o gate completo: `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright`, `uv run pytest`, `uv run engineering-playbook verify`
- [ ] T015 Rodar `engineering-playbook delivery prepare`/`commit`/`publish`/`merge --auto` para converger este recorte

---

## Dependencies & Execution Order

Setup -> Foundational -> US1 -> US2 -> US3 -> Polish. US2 depende de US1 (mesma funcao `executar()`, camadas adicionais de checagem). US3 idem.

## Implementation Strategy

MVP = Fases 1-3 (US1). Entrega incremental US1 -> US2 -> US3 -> Polish, cada uma validada antes de avancar, branch `feat/002-execucao-query`.
