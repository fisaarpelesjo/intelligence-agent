# Feature Specification: Memoria de conversa

**Feature Branch**: `009-memoria-conversa`

**Created**: 2026-09-08

**Status**: Draft

**Input**: PRD (FR-009); usa `RegistryRef` de `integracao_canal` (spec 007) como chave de identidade

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar e recuperar turno por identidade derivada (Priority: P1)

O sistema registra um turno de conversa (metrica perguntada, expressao de periodo, quando) indexado pelo `RegistryRef` do remetente — nunca por um identificador bruto de canal — e permite recuperar os turnos recentes dessa identidade.

**Why this priority**: E a capacidade central do pacote; sem ela nao ha memoria.

**Independent Test**: Registrar um turno para um `RegistryRef` e verificar que `turnos_recentes()` o retorna.

**Acceptance Scenarios**:

1. **Given** um turno registrado para um `RegistryRef`, **When** `turnos_recentes()` e chamado para essa mesma identidade, **Then** o turno registrado esta na lista retornada.
2. **Given** turnos registrados para dois `RegistryRef` diferentes, **When** `turnos_recentes()` e chamado para um deles, **Then** somente os turnos daquela identidade sao retornados.

---

### User Story 2 - Turnos fora da janela de retencao expiram (Priority: P1)

Um turno registrado ha mais tempo que a janela de retencao configurada nao aparece mais em `turnos_recentes()`.

**Why this priority**: Memoria de conversa e definida como "curto prazo" (PRD FR-009); sem expiracao, a memoria cresceria indefinidamente e deixaria de ser "recente".

**Independent Test**: Registrar um turno com um timestamp antigo, chamar `turnos_recentes()` com uma janela de retencao menor que a idade do turno, e verificar que ele nao e retornado.

**Acceptance Scenarios**:

1. **Given** um turno registrado ha 2 dias e uma janela de retencao de 1 dia, **When** `turnos_recentes()` e chamado com uma data de referencia atual, **Then** o turno nao esta na lista retornada.
2. **Given** o mesmo turno e uma janela de retencao de 3 dias, **When** `turnos_recentes()` e chamado, **Then** o turno esta na lista retornada.

---

### User Story 3 - Mensagens inbound sao sempre recusadas (Priority: P1)

Qualquer tentativa de processar uma mensagem recebida (inbound) e recusada, com um motivo nomeado fixo — e a funcao que processa inbound nao tem nenhuma forma de acessar a memoria (nao recebe uma referencia a ela), tornando estruturalmente impossivel que uma mensagem inbound afete a memoria nesta versao.

**Why this priority**: PRD FR-009 e a Constitution exigem que o inbound fique desligado ate decisao explicita; a garantia deve ser estrutural, nao apenas comportamental.

**Independent Test**: Inspecionar a assinatura de `processar_mensagem_inbound()` e confirmar que nenhum parametro de tipo `ConversationMemory` existe; chamar a funcao e verificar que ela sempre recusa.

**Acceptance Scenarios**:

1. **Given** qualquer payload de mensagem, **When** `processar_mensagem_inbound()` e chamada, **Then** o resultado e sempre uma recusa com o motivo nomeado "inbound_desabilitado".
2. **Given** a assinatura publica de `processar_mensagem_inbound()`, **When** inspecionada, **Then** nenhum dos seus parametros e do tipo `ConversationMemory`.

---

### Edge Cases

- O que acontece ao chamar `turnos_recentes()` para um `RegistryRef` sem nenhum turno registrado? Retorna uma lista vazia, sem erro.
- O que acontece com uma janela de retencao de zero ou negativa? E tratado como "nenhum turno e recente" — `turnos_recentes()` sempre retorna vazio nesse caso.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE indexar todo turno de conversa pelo `RegistryRef` do remetente — nunca por um identificador bruto de canal.
- **FR-002**: O sistema DEVE retornar, em `turnos_recentes()`, somente os turnos cuja idade (relativa a uma data de referencia injetada) seja menor ou igual a janela de retencao configurada.
- **FR-003**: O sistema DEVE recusar todo processamento de mensagem inbound com o motivo nomeado "inbound_desabilitado", independente do conteudo do payload.
- **FR-004**: A funcao publica de processamento de mensagem inbound NAO DEVE aceitar nenhum parametro que referencie a memoria de conversa.
- **FR-005**: O sistema DEVE retornar uma lista vazia (nunca erro) quando nao houver turno registrado para uma identidade, ou quando a janela de retencao for zero ou negativa.

### Key Entities *(include if feature involves data)*

- **ConversationTurn**: `registry_ref`, `metric_id`, `period_expression`, `recorded_at` (data/hora).
- **ConversationMemory** (porta): `registrar_turno(turn) -> None`, `turnos_recentes(registry_ref, reference_now, max_age) -> list[ConversationTurn]`.
- **InMemoryConversationMemory**: implementacao inicial em memoria (nao persistida entre processos — decisao de armazenamento real fica para quando houver infraestrutura, fora de escopo aqui).
- **InboundOutcome**: `accepted` (sempre `False` nesta versao), `reason_code` (sempre `"inbound_desabilitado"`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos turnos registrados para um `RegistryRef` sao recuperaveis via `turnos_recentes()` para essa mesma identidade, dentro da janela de retencao.
- **SC-002**: 0% dos turnos fora da janela de retencao aparecem em `turnos_recentes()`.
- **SC-003**: 100% das chamadas a `processar_mensagem_inbound()` retornam recusa "inbound_desabilitado", para qualquer payload.
- **SC-004**: A assinatura de `processar_mensagem_inbound()` nunca inclui um parametro do tipo `ConversationMemory` — verificavel por inspecao (`inspect.signature`).

## Assumptions

- O armazenamento e em memoria (nao persistido) nesta versao — persistencia real (arquivo, banco) e uma decisao de infraestrutura futura, fora de escopo.
- A janela de retencao (`max_age`) e a data de referencia (`reference_now`) sao sempre parametros injetados pelo chamador — nunca um valor padrao fixo no codigo, nem `datetime.now()` direto.
- Habilitar o processamento de mensagens inbound e uma decisao de produto futura, explicitamente fora de escopo desta versao (PRD, waiting room).
