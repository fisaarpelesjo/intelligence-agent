# Feature Specification: Integracao de canal

**Feature Branch**: `007-integracao-canal`

**Created**: 2026-09-08

**Status**: Draft

**Input**: PRD (FR-004); ADR-0001 (canal real adiado, usar `Channel` abstrato + fake)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resolver identidade via registro derivado (Priority: P1)

Dado um identificador bruto de remetente de um canal (ex.: chat-id), o sistema resolve um `RegistryRef` opaco atraves de um registro — nunca expondo ou usando o identificador bruto como identidade interna. O mesmo identificador bruto sempre resolve para o mesmo `RegistryRef` (idempotencia).

**Why this priority**: E a garantia central de "canal nunca e autoridade" (PRD FR-004); sem ela, qualquer parte do sistema que precisasse de identidade usaria o dado bruto do canal diretamente.

**Independent Test**: Chamar `resolver_identidade()` duas vezes com o mesmo par (canal, identificador bruto) e verificar que o `RegistryRef` retornado e identico e nunca igual ao identificador bruto original.

**Acceptance Scenarios**:

1. **Given** um identificador bruto `"12345"` no canal `"fake"`, **When** resolvido, **Then** o `RegistryRef` retornado e diferente de `"12345"`.
2. **Given** o mesmo par (canal, identificador bruto), **When** resolvido duas vezes, **Then** o `RegistryRef` e identico nas duas chamadas.
3. **Given** dois identificadores brutos diferentes no mesmo canal, **When** resolvidos, **Then** os `RegistryRef` retornados sao diferentes entre si.

---

### User Story 2 - Planejar entrega sem resumir ou truncar conteudo (Priority: P1)

Dada uma lista de sentencas (texto ja pronto, ex.: vindo de `interacao_conversacional`) e a capacidade de um canal (tamanho maximo de mensagem), o sistema agrupa sentencas inteiras em blocos que respeitam o limite — nunca cortando uma sentenca no meio, nunca resumindo ou arredondando o conteudo.

**Why this priority**: Degradacao deve ser sempre estrutural (quantas mensagens, como agrupar), nunca uma perda de conteudo (PRD, principio de proveniencia — o destinatario nunca recebe uma versao editada do que foi calculado).

**Independent Test**: Chamar `planejar_entrega()` com sentencas cujo tamanho combinado excede o limite de uma unica mensagem, e verificar que o plano tem multiplos blocos, cada um contendo sentencas inteiras.

**Acceptance Scenarios**:

1. **Given** 3 sentencas curtas cujo total excede o limite de uma mensagem, **When** planejada, **Then** o plano tem 2 ou mais blocos, e a concatenacao de todos os blocos reproduz exatamente as 3 sentencas originais, sem nenhuma removida ou alterada.
2. **Given** uma unica sentenca cujo tamanho sozinho excede o limite do canal, **When** planejada, **Then** a funcao recusa com o motivo nomeado "sentenca_excede_capacidade" — nunca corta a sentenca para caber.

---

### User Story 3 - Canal sem suporte a multiplas mensagens recusa em vez de enviar parcial (Priority: P2)

Quando o canal nao suporta multiplas mensagens e o conteudo nao cabe em uma unica, o sistema recusa a entrega inteira em vez de enviar so uma parte.

**Why this priority**: Enviar so uma parte da resposta calculada seria uma forma de truncamento disfarcado — proibido pelo mesmo principio da User Story 2.

**Independent Test**: Chamar `entregar()` com um canal fake configurado para nao suportar multiplas mensagens e conteudo que exigiria 2+ blocos, e verificar que nada e enviado e a recusa e nomeada.

**Acceptance Scenarios**:

1. **Given** um canal com `supports_multiple_messages=False` e conteudo que exigiria 2 blocos, **When** a entrega e tentada, **Then** a funcao recusa com o motivo nomeado "canal_nao_suporta_multiplas_mensagens" e nenhuma chamada de envio e feita ao canal.

---

### Edge Cases

- O que acontece com uma lista de sentencas vazia? O plano de entrega e uma lista vazia de blocos — nenhuma chamada de envio e feita, sem erro.
- O que acontece se o canal falhar ao enviar um bloco (ex.: erro de rede simulado)? A entrega para naquele bloco e retorna uma recusa nomeada "falha_no_envio", sem tentar reenviar automaticamente (retentativa e responsabilidade de uma camada futura, fora de escopo).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE resolver todo identificador bruto de remetente atraves de um registro, retornando um `RegistryRef` que nunca e igual ao identificador bruto.
- **FR-002**: O sistema DEVE retornar o mesmo `RegistryRef` para o mesmo par (canal, identificador bruto) em chamadas repetidas.
- **FR-003**: O sistema DEVE agrupar sentencas inteiras em blocos que respeitam o `max_message_length` do canal, sem nunca dividir uma sentenca no meio.
- **FR-004**: O sistema DEVE recusar, com o motivo nomeado "sentenca_excede_capacidade", uma unica sentenca cujo tamanho sozinho ultrapassa `max_message_length` — nunca cortando-a para caber.
- **FR-005**: O sistema DEVE recusar, com o motivo nomeado "canal_nao_suporta_multiplas_mensagens", uma entrega que exigiria mais de um bloco quando `supports_multiple_messages=False` — sem enviar nenhum bloco.
- **FR-006**: O sistema NAO DEVE tratar o identificador bruto do canal como identidade de autorizacao em nenhum outro ponto do fluxo de entrega.

### Key Entities *(include if feature involves data)*

- **RegistryRef**: identificador opaco derivado (texto), nunca o identificador bruto do canal.
- **IdentityRegistry** (porta): `resolve(channel_id, raw_sender_id) -> RegistryRef`, idempotente.
- **ChannelCapability**: `channel_id`, `max_message_length` (inteiro), `supports_multiple_messages` (booleano).
- **DeliveryPlan**: lista de blocos (cada bloco uma lista de sentencas inteiras que juntas cabem no limite).
- **Channel** (porta): `capability: ChannelCapability`, `send(registry_ref, text) -> None` (pode levantar excecao simulando falha).
- **DeliveryOutcome**: `success` (booleano), `reason_code` (texto ou nulo).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das resolucoes de identidade retornam um `RegistryRef` diferente do identificador bruto original.
- **SC-002**: 100% das resolucoes repetidas do mesmo par (canal, identificador bruto) retornam o mesmo `RegistryRef`.
- **SC-003**: 100% dos planos de entrega, quando concatenados, reproduzem exatamente o conteudo original das sentencas — nenhum caractere resumido, arredondado ou cortado.
- **SC-004**: 100% das sentencas que sozinhas excedem `max_message_length` sao recusadas nomeadamente, nunca cortadas.
- **SC-005**: 100% das entregas a um canal sem suporte a multiplas mensagens, quando o conteudo exige mais de um bloco, sao recusadas sem nenhuma chamada de envio.

## Assumptions

- O canal real (Telegram, etc.) esta fora de escopo — ADR-0001; esta spec define o contrato (`Channel`, `IdentityRegistry`) e uma implementacao fake para teste/uso local.
- O registro de identidade (`IdentityRegistry`) nesta versao e em memoria (fake) — persistencia real de um registro de identidade e uma decisao de infraestrutura futura, fora de escopo.
- Nao ha reentrega automatica em caso de falha de envio nesta spec.
- Recebimento de mensagem (inbound) esta fora de escopo desta spec — pertence a `memoria_conversa`, que tambem o mantem desligado por decisao de produto (registrada quando essa spec for escrita).
