# Feature Specification: Interacao conversacional

**Feature Branch**: `003-interacao-conversacional`

**Created**: 2026-09-07

**Status**: Draft

**Input**: PRD (FR-003, FR-010, FR-011, FR-012, BR-002, BR-003, BR-004, BR-005, NFR-001); Constitution (Principios II, III); consome `catalogo_semantico` (spec 001) e `execucao_query` (spec 002); ADR-0005 (LLM provider stub)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Responder uma pergunta direta com proveniencia ou abstencao (Priority: P1)

Dada uma pergunta ja estruturada (metrica, dimensao/valor opcional, expressao de periodo em portugues), o sistema resolve o periodo, autoriza via `catalogo_semantico`, executa via `execucao_query`, e narra a resposta com valor, unidade e proveniencia — ou se abstem explicitamente quando qualquer etapa recusar.

**Why this priority**: E o fluxo central do produto (Constitution Principio III); sem ele nao ha resposta nenhuma.

**Independent Test**: Chamar `responder()` com uma pergunta valida, um catalogo de teste, uma `FakeDataSource` e um `LLMProviderStub` injetados, e verificar a resposta com proveniencia.

**Acceptance Scenarios**:

1. **Given** uma pergunta sobre `signups` com expressao de periodo "mes passado" (dentro do vocabulario aprovado), **When** processada, **Then** a resposta contem o valor, a unidade, o `source_view` e a expressao de periodo resolvida (data-as-of).
2. **Given** uma pergunta sobre uma metrica desconhecida, **When** processada, **Then** o sistema retorna uma abstencao com motivo nomeado, nunca um numero.
3. **Given** uma expressao de periodo fora do vocabulario aprovado (ex.: "mes que vem"), **When** processada, **Then** o sistema retorna um pedido de clarificacao estruturado, nunca adivinha o periodo.

---

### User Story 2 - Recusar comparacao invalida (Priority: P1)

Dada uma pergunta de comparacao entre dois periodos, o sistema recusa quando um periodo e completo e o outro parcial (em andamento), e recusa quando o periodo baseline teria valor zero (divisao por zero).

**Why this priority**: Impede a classe de erro mais enganosa do produto — uma comparacao que parece um numero valido mas nao significa nada (Constitution Principio III, BR-004).

**Independent Test**: Chamar `responder()` com uma pergunta de comparacao cujos periodos sejam um completo e um parcial (relativo a uma data de referencia injetada), e verificar a recusa nomeada.

**Acceptance Scenarios**:

1. **Given** uma comparacao entre um periodo completo e um periodo que ainda nao terminou (parcial), relativo a data de referencia, **When** processada, **Then** o sistema recusa com o motivo nomeado "janela nao comparavel", sem retornar nenhum numero de comparacao.
2. **Given** uma comparacao entre dois periodos igualmente parciais (mesma posicao relativa a data de referencia), **When** processada, **Then** a comparacao e permitida e calculada.
3. **Given** uma comparacao cujo periodo baseline resulta em valor zero, **When** a formula de variacao percentual e aplicada, **Then** o sistema recusa com o motivo nomeado "baseline zero", sem retornar infinito ou indefinido.

---

### User Story 3 - Narrar com claim classificada e sem dado sensivel (Priority: P2)

Toda sentenca narrada na resposta final e classificada em uma das classes aprovadas, e o payload enviado ao `LLMProvider` (mesmo o stub) contem somente evidencia agregada — nunca a pergunta original em texto livre, identidade do usuario, credencial ou token.

**Why this priority**: Sustenta a auditabilidade da narrativa (FR-011) e o Principio IV (Least Privilege / NFR-001).

**Independent Test**: Inspecionar o payload passado ao `LLMProvider` injetado e a resposta final, verificando que toda sentenca tem uma `claim_class` valida e que o payload nao contem nenhum campo de identidade ou texto livre da pergunta original.

**Acceptance Scenarios**:

1. **Given** uma resposta bem-sucedida, **When** inspecionada, **Then** toda sentenca narrada tem uma `claim_class` de `FACTUAL_RESULT`, `CALCULATED_COMPARISON`, `INTERPRETATION` ou `LIMITATION`.
2. **Given** qualquer chamada a `responder()`, **When** o payload enviado ao `LLMProvider` e inspecionado, **Then** ele contem apenas campos de evidencia agregada (valor, unidade, periodo, fonte) — nenhum campo de identidade de usuario, texto livre da pergunta original, credencial ou token.

---

### Edge Cases

- O que acontece quando a pergunta nao especifica dimensao? O sistema trata como agregado total do periodo (comportamento ja suportado por `execucao_query`).
- O que acontece quando a autorizacao do catalogo recusa (`catalogo_semantico`) ou a execucao recusa (`execucao_query`)? O sistema traduz a recusa recebida numa abstencao nomeada equivalente, sem reinterpretar o motivo.
- O que acontece com uma pergunta de comparacao onde uma das duas metricas/periodos e desconhecida? O sistema recusa citando a etapa que falhou (autorizacao ou execucao), antes de tentar aplicar qualquer formula.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE resolver expressoes de periodo somente atraves de um vocabulario fechado e aprovado (ex.: hoje, ontem, semana, mes, trimestre, ano, e suas variantes "passado(a)"), com semana comecando na segunda-feira e mes seguindo o calendario civil; expressoes fora do vocabulario retornam um pedido de clarificacao, nunca uma adivinhacao.
- **FR-002**: O sistema DEVE chamar `catalogo_semantico.decidir()` antes de qualquer execucao, e traduzir uma decisao negada numa abstencao com o mesmo motivo nomeado.
- **FR-003**: O sistema DEVE chamar `execucao_query.executar()` somente quando a decisao de autorizacao for permitida, e traduzir uma recusa de execucao numa abstencao com o mesmo motivo nomeado.
- **FR-004**: O sistema DEVE recusar, com o motivo nomeado "janela nao comparavel", qualquer comparacao entre um periodo completo (ja terminado, relativo a uma data de referencia) e um periodo parcial (ainda em andamento).
- **FR-005**: O sistema DEVE aplicar somente a formula de comparacao `percentage_change` (variacao percentual) e recusar, com o motivo nomeado "baseline zero", qualquer comparacao cujo periodo baseline tenha valor zero.
- **FR-006**: O sistema DEVE classificar toda sentenca da resposta final numa das claim classes aprovadas (`FACTUAL_RESULT`, `CALCULATED_COMPARISON`, `INTERPRETATION`, `LIMITATION`) antes de incluir a sentenca na resposta.
- **FR-007**: O sistema DEVE montar o payload enviado ao `LLMProvider` contendo somente evidencia agregada (valor, unidade, periodo resolvido, fonte, claim classes) — nunca a pergunta original em texto livre, identidade do usuario, credencial ou token.
- **FR-008**: O sistema NAO DEVE calcular nenhum valor numerico dentro do `LLMProvider` — todo calculo (variacao percentual, agregacao) e feito antes de montar o payload, por codigo deterministico.

### Key Entities *(include if feature involves data)*

- **QuestionIntent**: metrica, dimensao/valor de filtro (opcional), expressao de periodo (texto), expressao de periodo baseline para comparacao (opcional).
- **ResolvedPeriod**: periodo (inicio/fim), se e parcial (ainda em andamento) relativo a uma data de referencia.
- **ComparisonResult**: valor atual, valor baseline, variacao percentual, direcao.
- **NarrationPayload**: estrutura fechada de campos permitidos enviados ao `LLMProvider` (sem texto livre nem identidade).
- **ClaimSentence**: texto narrado + `claim_class`.
- **AnswerOutcome**: sucesso (booleano), sentencas narradas (`ClaimSentence[]`) e proveniencia quando bem-sucedido, ou motivo nomeado de abstencao/clarificacao quando nao.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das perguntas com expressao de periodo fora do vocabulario aprovado retornam pedido de clarificacao, nunca uma resposta com numero.
- **SC-002**: 100% das respostas bem-sucedidas contem proveniencia completa (fonte, unidade, periodo); 100% das recusas contem um motivo nomeado — nunca nenhum dos dois, nunca os dois ausentes.
- **SC-003**: 100% das comparacoes entre periodo completo e parcial sao recusadas antes de qualquer calculo de variacao.
- **SC-004**: 100% das comparacoes com baseline zero sao recusadas, nunca retornando infinito ou indefinido.
- **SC-005**: 100% das sentencas da resposta final tem uma `claim_class` valida associada.
- **SC-006**: 0% dos payloads enviados ao `LLMProvider` contem qualquer campo de identidade de usuario, texto livre da pergunta original, credencial ou token — verificavel por inspecao estrutural do tipo `NarrationPayload`.

## Assumptions

- Esta feature recebe a pergunta ja estruturada em `QuestionIntent` (metrica, filtro opcional, expressoes de periodo em texto) — o parsing de linguagem natural livre para `QuestionIntent` (ex.: via um LLM real) e uma preocupacao de uma camada anterior, fora do escopo desta spec, e usa o `LLMProvider` stub (ADR-0005) apenas para a etapa de narracao final, nunca para interpretar a pergunta nesta versao.
- A data de referencia ("hoje") e um parametro injetavel (nunca `date.today()` direto no dominio), para manter o pacote deterministico e testavel.
- Depende de `001-catalogo-semantico` e `002-execucao-query` para autorizacao e execucao; nao reimplementa nenhuma logica dessas specs.
- O canal de entrega (Telegram, etc.) e a integracao de identidade (`channel_integration`) estao fora do escopo desta spec — adiados por ADR-0001.
