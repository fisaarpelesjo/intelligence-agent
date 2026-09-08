---

description: "Tasks: interacao conversacional"
---

# Tasks: Interacao conversacional

**Input**: `specs/003-interacao-conversacional/plan.md`, `spec.md`, `data-model.md`, `contracts/responder.md`, `quickstart.md`

**Tests**: incluidos.

## Phase 1: Setup

- [x] T001 Criar `packages/interacao_conversacional/` com `pyproject.toml` (dependencias `catalogo-semantico`, `execucao-query`), `src/interacao_conversacional/__init__.py`, `tests/unit/`
- [x] T002 [P] Adicionar `interacao-conversacional` como dependencia do projeto raiz e rodar `uv sync`

## Phase 2: Foundational

- [x] T003 Implementar `QuestionIntent`, `ResolvedPeriod`, `ComparisonResult`, `ClaimClass`, `ClaimSentence`, `NarrationPayload`, `AnswerOutcome`, `LLMProvider` (Protocol) em `modelos.py` (per `data-model.md`)
- [x] T004 [P] Implementar `vocabulario_periodo.py`: resolve as 10 expressoes do vocabulario fechado para `ResolvedPeriod` dado um `reference_today`; retorna `None` para expressao desconhecida — FR-001
- [x] T005 [P] Implementar `comparacao.py`: `percentage_change(current, baseline)`, recusando (retorno especial ou excecao dedicada) quando `baseline == 0` — FR-005
- [x] T006 [P] Implementar `LLMProviderStub` em `llm_provider_stub.py`: narra um `NarrationPayload` em sentencas com `claim_class` fixa e deterministica (FACTUAL_RESULT para o valor, CALCULATED_COMPARISON quando ha comparacao, LIMITATION sempre) — FR-006

**Checkpoint**: tipos, vocabulario, formula e stub prontos.

---

## Phase 3: User Story 1 - Responder com provenencia ou abstencao (Priority: P1) 🎯 MVP

### Tests for User Story 1 ⚠️

- [x] T007 [P] [US1] `test_responde_com_provenencia.py`: cenario 1 (resposta com provenencia)
- [x] T008 [P] [US1] `test_vocabulario_de_periodo.py`: cenarios 2-3 (metrica desconhecida repassada do catalogo; expressao de periodo desconhecida -> clarificacao)

### Implementation for User Story 1

- [x] T009 [US1] Implementar `responder()` — checagens 1-4 do contrato (resolucao de periodo, autorizacao, execucao, montagem de payload e narracao sem comparacao) em `orquestrador.py` — FR-001, FR-002, FR-003, FR-007, FR-008

**Checkpoint**: US1 funcional e testavel isoladamente — MVP entregavel.

---

## Phase 4: User Story 2 - Recusar comparacao invalida (Priority: P1)

### Tests for User Story 2 ⚠️

- [x] T010 [P] [US2] `test_comparacao_invalida.py`: cenarios 1-3 (janela nao comparavel, comparacao parcial-parcial permitida, baseline zero)

### Implementation for User Story 2

- [x] T011 [US2] Implementar o fluxo de comparacao (checagem 5 do contrato: janela comparavel, execucao do baseline, formula, recusa por baseline zero) em `orquestrador.py` (depende de T009, T005) — FR-004, FR-005

**Checkpoint**: US1 e US2 funcionam juntas e isoladamente.

---

## Phase 5: User Story 3 - Narrar com claim classificada e sem dado sensivel (Priority: P2)

### Tests for User Story 3 ⚠️

- [x] T012 [P] [US3] `test_narracao_sem_dado_sensivel.py`: cenarios 1-2 (toda sentenca com claim_class valida; payload sem identidade/texto-livre/credencial)

### Implementation for User Story 3

- [x] T013 [US3] Garantir que `NarrationPayload` so contenha os campos fechados de `data-model.md` (revisar `orquestrador.py` e `modelos.py`) — FR-007, SC-006

**Checkpoint**: todas as 3 user stories funcionais e testadas independentemente.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T014 [P] Escrever `packages/interacao_conversacional/README.md` com o conteudo de `quickstart.md`
- [x] T015 Rodar o gate completo: `ruff format --check`, `ruff check`, `pyright`, `pytest`, `engineering-playbook verify`
- [x] T016 Rodar `engineering-playbook delivery prepare`/`commit`/`publish`/`merge --auto` para converger este recorte

---

## Dependencies & Execution Order

Setup -> Foundational -> US1 -> US2 -> US3 -> Polish. US2 e US3 dependem de US1 (mesma `responder()`).

## Implementation Strategy

MVP = Fases 1-3 (US1). Branch `feat/003-interacao-conversacional`.
