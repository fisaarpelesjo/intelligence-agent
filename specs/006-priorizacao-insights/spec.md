# Feature Specification: Priorizacao de insights

**Feature Branch**: `006-priorizacao-insights`

**Created**: 2026-09-08

**Status**: Draft

**Input**: PRD (FR-006); consome `CandidateFinding` de `deteccao_anomalia` (spec 005) como referencia, mas opera sobre um envelope proprio com magnitude/confianca/alcance

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ordenar insights por tupla, nunca por score unico (Priority: P1)

Dada uma lista de insights candidatos (cada um com magnitude, confianca e alcance conhecidos), o sistema os ordena de forma descendente comparando as tuplas `(magnitude * confianca, alcance * confianca)` termo a termo — nunca reduzindo os dois fatores a um unico numero combinado.

**Why this priority**: E a capacidade central do pacote; sem ela nao ha priorizacao.

**Independent Test**: Chamar `priorizar()` com 3 insights de magnitude/confianca/alcance conhecidos e distintos, e verificar a ordem resultante e o rank atribuido.

**Acceptance Scenarios**:

1. **Given** dois insights, A com `magnitude*confianca` maior que B, **When** priorizados, **Then** A aparece antes de B na lista priorizada, com `rank=1` e `rank=2` respectivamente.
2. **Given** dois insights com o mesmo `magnitude*confianca` mas `alcance*confianca` diferente, **When** priorizados, **Then** o de maior `alcance*confianca` aparece primeiro (segundo termo da tupla usado como desempate).
3. **Given** uma lista vazia de insights, **When** priorizada, **Then** o resultado tem listas vazias, sem erro.

---

### User Story 2 - Recusar priorizar quando a confianca e desconhecida (Priority: P1)

Um insight cuja confianca e `None` nunca e priorizado — nunca e tratado como se tivesse confianca maxima (1.0) por omissao.

**Why this priority**: Assumir confianca maxima por omissao esconderia incerteza real, violando a proveniencia da priorizacao (PRD FR-006).

**Independent Test**: Chamar `priorizar()` com um insight de confianca `None` entre outros validos, e verificar que ele aparece em `not_prioritisable` com o motivo nomeado, nunca na lista priorizada.

**Acceptance Scenarios**:

1. **Given** um insight com `confidence=None`, **When** priorizado junto com outros validos, **Then** ele aparece em `not_prioritisable` com o motivo nomeado "confidence_unknown", e os outros sao priorizados normalmente.

---

### User Story 3 - Recusar priorizar quando o alcance e desconhecido (Priority: P2)

Um insight com confianca conhecida mas alcance `None` tambem nunca e priorizado, pelo mesmo principio.

**Why this priority**: Mesma logica da User Story 2, aplicada ao segundo fator da tupla.

**Independent Test**: Chamar `priorizar()` com um insight de `reach=None` (mas `confidence` presente), e verificar que aparece em `not_prioritisable` com motivo distinto do da confianca desconhecida.

**Acceptance Scenarios**:

1. **Given** um insight com `confidence=0.9` e `reach=None`, **When** priorizado, **Then** ele aparece em `not_prioritisable` com o motivo nomeado "reach_unknown".

---

### Edge Cases

- O que acontece quando `confidence` e `reach` sao ambos `None`? O motivo nomeado e "confidence_unknown" (confianca e checada primeiro, por ser o fator comum aos dois termos da tupla).
- O que acontece com `magnitude` negativa (ex.: uma queda representada como numero negativo)? A funcao nao normaliza sinal — cabe ao chamador decidir se magnitude e sempre um valor absoluto ou com sinal; a ordenacao usa o valor exatamente como fornecido.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE ordenar os insights priorizaveis de forma descendente comparando as tuplas `(magnitude * confidence, reach * confidence)` termo a termo.
- **FR-002**: O sistema NAO DEVE expor nem usar internamente um unico numero que combine magnitude, confianca e alcance em um score fundido para a ordenacao — apenas os dois termos da tupla.
- **FR-003**: O sistema DEVE excluir da priorizacao, com o motivo nomeado "confidence_unknown", qualquer insight cuja `confidence` seja `None` — nunca assumindo um valor padrao.
- **FR-004**: O sistema DEVE excluir da priorizacao, com o motivo nomeado "reach_unknown", qualquer insight cuja `confidence` seja conhecida mas `reach` seja `None`.
- **FR-005**: O sistema DEVE atribuir um `rank` (posicao, comecando em 1) a cada insight priorizavel, na ordem final; insights nao priorizaveis nao recebem rank.
- **FR-006**: O sistema DEVE preservar todo insight de entrada na saida — priorizado (com rank) ou nao-priorizavel (com motivo) — nunca descartando um silenciosamente.

### Key Entities *(include if feature involves data)*

- **InsightCandidate**: identificador (texto livre, ex.: `metric_id` + data), `magnitude` (numero), `confidence` (numero ou `None`), `reach` (numero ou `None`).
- **PrioritizedInsight**: `candidate` (o `InsightCandidate` original), `rank` (inteiro, 1-based), `impact_score` (`magnitude * confidence`), `reach_score` (`reach * confidence`).
- **NotPrioritisableInsight**: `candidate`, `reason_code` (`confidence_unknown` ou `reach_unknown`).
- **PrioritizationOutcome**: `prioritized` (lista de `PrioritizedInsight`, ordenada), `not_prioritisable` (lista de `NotPrioritisableInsight`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos insights com `confidence=None` aparecem em `not_prioritisable` com motivo "confidence_unknown" — nunca priorizados.
- **SC-002**: 100% dos insights com `confidence` presente e `reach=None` aparecem em `not_prioritisable` com motivo "reach_unknown".
- **SC-003**: A ordenacao dos insights priorizados e sempre consistente com a comparacao das tuplas `(impact_score, reach_score)` termo a termo, verificavel recalculando as tuplas a partir da saida.
- **SC-004**: `PrioritizedInsight` nunca expoe um campo de score unico combinado — apenas `impact_score` e `reach_score` separados, verificavel por inspecao de `dataclasses.fields()`.
- **SC-005**: Uma lista vazia de entrada produz um `PrioritizationOutcome` com ambas as listas vazias, sem excecao.

## Assumptions

- `magnitude`, `confidence` e `reach` sao fornecidos pelo chamador — este pacote nao os calcula (nao ha integracao com `deteccao_anomalia` nesta versao; um `CandidateFinding` pode ser mapeado para um `InsightCandidate` por um chamador futuro, fora de escopo aqui).
- `confidence` e `reach`, quando presentes, sao numeros no intervalo `[0, 1]` e `[0, +inf)` respectivamente — a funcao nao valida faixa nesta versao, apenas a presenca (`None` ou nao).
- Nao ha distribuicao nem persistencia nesta spec — isso pertence a `proactive_distribution`, fora de escopo aqui.
