---

description: "Tasks: catalogo semantico — decisao de autorizacao"
---

# Tasks: Catalogo semantico — decisao de autorizacao

**Input**: `specs/001-catalogo-semantico/plan.md`, `spec.md`, `data-model.md`, `contracts/decidir.md`, `quickstart.md`

**Tests**: incluidos — a spec e a constitution (Principio II/III) exigem verificacao por teste para praticamente todo requisito.

**Organization**: tasks agrupadas por user story (US1, US2, US3 da spec), permitindo entrega incremental.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [ ] T001 Criar `packages/catalogo_semantico/` com `pyproject.toml`, `src/catalogo_semantico/__init__.py`, `tests/unit/__init__.py`, `catalog/` (per `plan.md`)
- [ ] T002 [P] Adicionar `packages/catalogo_semantico` como membro do workspace `uv` no `pyproject.toml` da raiz (`[tool.uv.workspace] members = ["packages/*"]`)
- [ ] T003 [P] Configurar `[tool.ruff]`/`[tool.pyright]`/`[tool.pytest.ini_options]` do pacote (herdando os padroes ja usados na raiz do repositorio)

**Checkpoint**: `uv sync` resolve o workspace com o novo pacote; `uv run pytest packages/catalogo_semantico` roda (ainda sem testes reais).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: infraestrutura que TODAS as user stories dependem.

- [ ] T004 Implementar `MetricDefinition`, `MetricDefinitionVersion`, `DimensionDefinition`, `AccessDecision`, `AuditEvent` em `packages/catalogo_semantico/src/catalogo_semantico/modelos.py` (per `data-model.md`)
- [ ] T005 [P] Criar catalogo de exemplo sintetico em `packages/catalogo_semantico/catalog/{metrics,dimensions,owners}.yaml` com as metricas `signups`, `monthly_recurring_revenue`, `active_users` (`signups` com 2 versoes para exercitar US2)
- [ ] T006 Implementar `carregar_catalogo` em `packages/catalogo_semantico/src/catalogo_semantico/carregamento.py`, incluindo a validacao de integridade (IDs duplicados, janelas sobrepostas) — FR-008
- [ ] T007 [P] Criar catalogo minimo de teste em `packages/catalogo_semantico/tests/fixtures/catalogo_exemplo/` (subset deliberadamente pequeno, usado pelos testes unitarios)

**Checkpoint**: fundacao pronta — `carregar_catalogo` funciona contra o fixture de teste; nenhuma user story pode comecar antes disso.

---

## Phase 3: User Story 1 - Decidir se uma pergunta pode ser respondida (Priority: P1) 🎯 MVP

**Goal**: dada uma tupla (metrica, dimensao, periodo), retornar permitido/negado sem I/O, com a definicao de metrica quando permitido.

**Independent Test**: chamar `decidir()` diretamente com o fixture de teste, sem nenhuma dependencia externa.

### Tests for User Story 1 ⚠️

- [ ] T008 [P] [US1] `test_decisao_permite.py`: cenario 1 da spec (metrica+dimensao aprovadas -> permitido com definicao retornada)
- [ ] T009 [P] [US1] `test_decisao_nega.py`: cenarios 2, 3 e 4 da spec (metrica desconhecida; dimensao nao permitida; catalogo vazio -> sempre negado)

### Implementation for User Story 1

- [ ] T010 [US1] Implementar `decidir()` (autorizacao basica: metrica existe, dimensao permitida) em `packages/catalogo_semantico/src/catalogo_semantico/decisao.py` (depende de T004, T006) — FR-001, FR-002, FR-003, FR-004
- [ ] T011 [US1] Teste de garantia "zero I/O" (SC-004): interceptar/mockar chamadas de rede e socket durante `decidir()` e falhar se qualquer uma ocorrer

**Checkpoint**: User Story 1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Resolver a definicao correta de uma metrica ao longo do tempo (Priority: P2)

**Goal**: resolver a versao de metrica vigente para o periodo pedido, incluindo versoes descontinuadas; recusar periodos que cruzam fronteira de versao.

**Independent Test**: catalogo de teste com 2 versoes de `signups` (janelas nao sobrepostas); perguntar por periodos dentro de cada janela e um periodo que cruza a fronteira.

### Tests for User Story 2 ⚠️

- [ ] T012 [P] [US2] `test_versionamento.py`: cenarios 1-4 da spec (versao antiga, versao nova, periodo cruzando fronteira, versao descontinuada ainda resolvivel)
- [ ] T013 [P] [US2] `test_catalogo_invalido.py`: catalogo com IDs de metrica duplicados e com janelas de versao sobrepostas falham na carga (`carregar_catalogo`), nao na decisao

### Implementation for User Story 2

- [ ] T014 [US2] Implementar resolucao de versao por periodo em `decisao.py` (depende de T010) — FR-005, FR-006, FR-007
- [ ] T015 [US2] Implementar as duas checagens de integridade em `carregamento.py` (depende de T006) — FR-008

**Checkpoint**: User Stories 1 e 2 funcionam juntas e isoladamente.

---

## Phase 5: User Story 3 - Auditar toda decisao de autorizacao (Priority: P2)

**Goal**: todo `decidir()` emite exatamente um `AuditEvent`, permitido ou negado, antes de retornar.

**Independent Test**: contar eventos emitidos apos N chamadas de `decidir()` e verificar N == N.

### Tests for User Story 3 ⚠️

- [ ] T016 [P] [US3] `test_auditoria.py`: cenarios 1-3 da spec (evento em permissao, evento em negacao com motivo, contagem exata apos N chamadas)

### Implementation for User Story 3

- [ ] T017 [US3] Implementar `emitir_evento()` em `packages/catalogo_semantico/src/catalogo_semantico/auditoria.py` — FR-009
- [ ] T018 [US3] Integrar `emitir_evento()` dentro de `decidir()`, chamado antes do `return` (depende de T010, T017) — FR-010

**Checkpoint**: todas as 3 user stories funcionais e testadas independentemente.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T019 [P] Escrever `packages/catalogo_semantico/README.md` com o conteudo de `quickstart.md`
- [ ] T020 Rodar o gate completo: `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright`, `uv run pytest`, `uv run python scripts/verify.py`
- [ ] T021 Rodar `engineering-playbook checkpoint` e `engineering-playbook delivery prepare` para converger PRD + spec + plano + tasks + codigo + evidencia (ENGINEERING.md, passo 11-12)

---

## Dependencies & Execution Order

- Setup (Fase 1) -> Foundational (Fase 2) -> User Stories (Fases 3-5, em ordem de prioridade P1 -> P2 -> P2) -> Polish (Fase 6)
- US1 nao depende de US2/US3. US2 depende apenas da Foundational (reusa `decidir()` de US1 mas e testavel com seu proprio fixture). US3 depende apenas da Foundational (pode ser implementada em paralelo a US2, integrando com US1 na Fase 5/T018).

### Parallel Opportunities

- T002, T003 em paralelo apos T001.
- T005, T007 em paralelo apos T004.
- Testes marcados [P] dentro de cada fase rodam em paralelo entre si (arquivos distintos).

## Implementation Strategy

MVP = Fases 1, 2 e 3 (User Story 1). Entrega incremental: US1 -> US2 -> US3 -> Polish, cada uma validada e commitada via `engineering-playbook delivery` antes de avancar (branch `feat/001-catalogo-semantico`, conforme convencao do engineering-playbook).
