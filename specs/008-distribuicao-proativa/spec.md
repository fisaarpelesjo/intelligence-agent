# Feature Specification: Distribuicao proativa

**Feature Branch**: `008-distribuicao-proativa`

**Created**: 2026-09-08

**Status**: Draft

**Input**: PRD (FR-007); consome `PrioritizedInsight` de `priorizacao_insights` (spec 006) e `entregar()` de `integracao_canal` (spec 007)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Originar mensagem somente quando as 3 condicoes passam (Priority: P1)

Um insight priorizado so vira mensagem de saida quando: (1) o finding e priorizavel, (2) o canal esta habilitado, e (3) o destinatario esta explicitamente na allow-list do canal. As 3 condicoes sao simultaneas — nenhuma sozinha basta.

**Why this priority**: E o unico ponto do pipeline que origina comunicacao nao solicitada; as 3 condicoes previnem ruido e vazamento para destinatario nao autorizado (PRD FR-007).

**Independent Test**: Chamar `distribuir()` com um insight priorizado, canal habilitado e destinatario na allow-list, com um canal fake injetado, e verificar que a mensagem foi enviada.

**Acceptance Scenarios**:

1. **Given** um `PrioritizedInsight` valido, canal habilitado e destinatario na allow-list, **When** distribuido, **Then** a mensagem e originada e entregue, com `originated=True`.

---

### User Story 2 - Recusar quando qualquer condicao falha (Priority: P1)

Se qualquer uma das 3 condicoes falhar, nenhuma mensagem e originada, e a chamada de entrega (`integracao_canal.entregar`) nunca acontece.

**Why this priority**: A garantia so vale se for absoluta — uma condicao que "quase" passa ainda deve bloquear.

**Independent Test**: Chamar `distribuir()` variando cada condicao isoladamente (insight ausente, canal desabilitado, destinatario fora da allow-list) e verificar `originated=False` com o motivo nomeado correto em cada caso, e que o canal fake nunca recebeu nenhuma chamada de envio.

**Acceptance Scenarios**:

1. **Given** nenhum insight priorizavel (`None`), **When** distribuido, **Then** `originated=False`, motivo "finding_nao_priorizavel", nenhuma chamada ao canal.
2. **Given** um insight priorizavel mas canal desabilitado, **When** distribuido, **Then** `originated=False`, motivo "canal_desabilitado", nenhuma chamada ao canal.
3. **Given** um insight priorizavel, canal habilitado, mas destinatario fora da allow-list, **When** distribuido, **Then** `originated=False`, motivo "destinatario_nao_autorizado", nenhuma chamada ao canal.

---

### User Story 3 - Mensagem sempre com campos rotulados, nunca frase livre (Priority: P2)

Quando a mensagem e originada, seu conteudo e sempre uma lista de campos rotulados (`"rotulo: valor"`) — nunca uma frase composta livremente.

**Why this priority**: Garante que o destinatario recebe dado estruturado e auditavel, nao uma narrativa livre nao rastreavel a um campo especifico.

**Independent Test**: Inspecionar as sentencas enviadas ao canal fake apos uma distribuicao bem-sucedida e verificar que cada uma segue o formato `"rotulo: valor"`.

**Acceptance Scenarios**:

1. **Given** uma distribuicao bem-sucedida, **When** as sentencas enviadas sao inspecionadas, **Then** cada uma comeca com um rotulo conhecido seguido de `": "` e o valor correspondente do insight — nunca uma frase narrativa livre.

---

### Edge Cases

- O que acontece se `integracao_canal.entregar()` recusar (ex.: canal sem suporte a multiplas mensagens)? `distribuir()` repassa o motivo recebido, sem reinterpretar.
- O que acontece se a mesma allow-list tiver o destinatario duplicado? Nao ha efeito — e apenas uma checagem de pertencimento a um conjunto.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE originar uma mensagem somente quando as 3 condicoes (finding priorizavel, canal habilitado, destinatario na allow-list) forem todas verdadeiras.
- **FR-002**: O sistema DEVE recusar com o motivo nomeado "finding_nao_priorizavel" quando nenhum insight priorizavel for fornecido.
- **FR-003**: O sistema DEVE recusar com o motivo nomeado "canal_desabilitado" quando o canal nao estiver habilitado.
- **FR-004**: O sistema DEVE recusar com o motivo nomeado "destinatario_nao_autorizado" quando o destinatario nao estiver na allow-list.
- **FR-005**: O sistema NAO DEVE chamar `integracao_canal.entregar()` quando qualquer uma das 3 condicoes falhar.
- **FR-006**: O sistema DEVE montar a mensagem como uma lista de campos rotulados (`"rotulo: valor"`) a partir dos dados do insight — nunca uma frase composta livremente.

### Key Entities *(include if feature involves data)*

- **ChannelGateConfig**: `channel_id`, `enabled` (booleano), `allowed_raw_sender_ids` (conjunto de texto).
- **DistributionOutcome**: `originated` (booleano), `reason_code` (texto ou nulo), `delivery_outcome` (`DeliveryOutcome` de `integracao_canal`, ou nulo quando nao originado).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das distribuicoes com as 3 condicoes verdadeiras originam a mensagem.
- **SC-002**: 100% das distribuicoes com qualquer condicao falsa retornam `originated=False` com motivo nomeado correto, e 0% delas chamam `integracao_canal.entregar()`.
- **SC-003**: 100% das sentencas enviadas seguem o formato `"rotulo: valor"` — verificavel por inspecao das strings enviadas ao canal fake.

## Assumptions

- `ChannelGateConfig` (habilitado/allow-list) e configuracao injetada pelo chamador — nao ha persistencia de configuracao nesta spec.
- O canal real continua adiado (ADR-0001); esta spec usa o `FakeChannel`/`FakeIdentityRegistry` de `integracao_canal`.
- Retentativa apos falha de entrega esta fora de escopo — mesma assuncao de `integracao_canal`.
