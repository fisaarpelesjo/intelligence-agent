# Feature Specification: Catalogo semantico — decisao de autorizacao

**Feature Branch**: `001-catalogo-semantico`

**Created**: 2026-09-07

**Status**: Draft

**Input**: PRD `docs/requirements/project-requirements.md` (FR-001, FR-013, FR-014, FR-015, BR-001, CON-001); Constitution `.specify/memory/constitution.md` (Principio I: Governed Semantic Access)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Decidir se uma pergunta pode ser respondida (Priority: P1)

Um consumidor (a camada de interacao conversacional, em uma feature futura) submete uma pergunta ja traduzida em um formato estruturado: uma metrica, uma dimensao opcional de quebra e um periodo. O catalogo semantico decide, sem ler nenhum dado real, se essa combinacao e permitida — e se for, retorna a definicao da metrica necessaria para montar a query; se nao for, retorna uma negacao com motivo nomeado.

**Why this priority**: E a capacidade central do produto (Constitution Principio I e IV) — sem ela, nenhuma outra parte do pipeline pode operar com seguranca, porque nao ha ponto de autorizacao antes da leitura de dado.

**Independent Test**: Pode ser testada isoladamente chamando a funcao de decisao com uma tupla (metrica, dimensao, periodo) e verificando a decisao retornada, sem qualquer dependencia de banco de dados ou rede — testavel 100% em memoria com um catalogo de exemplo carregado em teste.

**Acceptance Scenarios**:

1. **Given** um catalogo com a metrica `signups` aprovada e a dimensao `country` na lista de dimensoes permitidas dessa metrica, **When** a pergunta pede `signups` quebrado por `country` num periodo valido, **Then** a decisao e "permitido" e inclui a definicao da metrica (fonte, agregacao, unidade).
2. **Given** o mesmo catalogo, **When** a pergunta pede uma metrica que nao existe no catalogo, **Then** a decisao e "negado" com o motivo nomeado "metrica desconhecida".
3. **Given** a metrica `signups` aprovada mas sem a dimensao `payment_method` na sua lista de dimensoes permitidas, **When** a pergunta pede `signups` quebrado por `payment_method`, **Then** a decisao e "negado" com o motivo nomeado "dimensao nao permitida para esta metrica".
4. **Given** um catalogo vazio (nenhuma metrica aprovada ainda), **When** qualquer pergunta e avaliada, **Then** a decisao e sempre "negado" — nunca "permitido" por omissao.

---

### User Story 2 - Resolver a definicao correta de uma metrica ao longo do tempo (Priority: P2)

Uma metrica pode ter mais de uma versao publicada ao longo do tempo (por exemplo, a formula de calculo mudou numa certa data). O catalogo deve resolver, para um periodo perguntado, exatamente a versao da definicao que estava vigente naquele periodo — mesmo que a metrica ja tenha sido descontinuada ou substituida por uma versao mais nova.

**Why this priority**: Sustenta a confianca em numeros ja comunicados no passado (PRD FR-014); sem isso, uma mudanca de definicao reescreveria silenciosamente respostas historicas.

**Independent Test**: Pode ser testada isoladamente carregando um catalogo com duas versoes fechadas de uma mesma metrica (cada uma com uma janela de vigencia) e verificando que uma pergunta sobre um periodo dentro da janela antiga resolve para a definicao antiga.

**Acceptance Scenarios**:

1. **Given** uma metrica com uma versao fechada vigente de `2026-01-01` a `2026-06-30` e uma nova versao vigente a partir de `2026-07-01`, **When** a pergunta e sobre o periodo `2026-03`, **Then** a decisao resolve e retorna a definicao da versao antiga.
2. **Given** o mesmo catalogo, **When** a pergunta e sobre o periodo `2026-08`, **Then** a decisao resolve e retorna a definicao da versao nova.
3. **Given** o mesmo catalogo, **When** a pergunta pede um periodo que cruza a fronteira entre as duas versoes (ex.: `2026-06-15` a `2026-07-15`), **Then** a decisao e "negado" com o motivo nomeado "periodo cruza fronteira de versao de metrica" — a pergunta deve ser refeita com um periodo dentro de uma unica versao.
4. **Given** uma metrica cuja unica versao foi descontinuada (deprecated) mas permanece fechada e valida para seu periodo historico, **When** a pergunta e sobre um periodo dentro dessa janela, **Then** a decisao ainda resolve normalmente — descontinuada nao significa inacessivel para o passado.

---

### User Story 3 - Auditar toda decisao de autorizacao (Priority: P2)

Toda decisao tomada pelo catalogo (permitida ou negada) produz um evento de auditoria estruturado, contendo a pergunta avaliada, a decisao, o motivo (quando negado) e um timestamp — antes de a decisao ser retornada ao chamador.

**Why this priority**: E o que torna a promessa de governanca do produto verificavel externamente (PRD FR-015, NEED-004); sem isso, nao ha como provar que uma regra foi de fato aplicada.

**Independent Test**: Pode ser testada isoladamente contando os eventos de auditoria emitidos apos N chamadas de decisao e verificando que o numero de eventos e exatamente N, com o conteudo correto em cada um.

**Acceptance Scenarios**:

1. **Given** qualquer chamada de decisao, **When** a decisao e "permitido", **Then** um evento de auditoria e emitido com decisao="permitido" e o identificador da metrica/dimensao/periodo avaliado.
2. **Given** qualquer chamada de decisao, **When** a decisao e "negado", **Then** um evento de auditoria e emitido com decisao="negado" e o motivo nomeado da negacao.
3. **Given** N chamadas de decisao em sequencia, **When** todas completam, **Then** exatamente N eventos de auditoria foram emitidos — nenhum a mais, nenhum a menos.

---

### Edge Cases

- O que acontece quando o catalogo tem duas metricas com o mesmo identificador (conflito de definicao)? O sistema deve recusar carregar um catalogo invalido dessa forma, em vez de escolher uma das duas silenciosamente.
- O que acontece quando a dimensao pedida existe no catalogo, mas nao esta associada a nenhuma metrica (dimensao "orfa")? A decisao deve negar citando "dimensao nao associada a metrica" quando pedida junto com uma metrica que nao a lista.
- O que acontece quando o periodo pedido nao tem nenhuma versao de metrica cobrindo-o (antes da primeira versao existir, ou apos a metrica ser removida sem substituta)? A decisao nega com o motivo "sem definicao de metrica vigente para o periodo".
- O que acontece quando duas versoes de uma mesma metrica tem janelas de vigencia sobrepostas (erro de configuracao do catalogo)? O sistema deve recusar carregar o catalogo nesse estado, citando a sobreposicao, em vez de escolher uma versao arbitrariamente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE, dada uma tupla (metrica, dimensao opcional, periodo), retornar uma decisao de "permitido" ou "negado" sem realizar nenhuma leitura de dado externo (rede ou banco de dados) durante a decisao.
- **FR-002**: O sistema DEVE negar por padrao qualquer metrica que nao exista no catalogo carregado, com o motivo nomeado "metrica desconhecida".
- **FR-003**: O sistema DEVE negar qualquer dimensao que nao esteja na lista de dimensoes permitidas da metrica pedida, com o motivo nomeado "dimensao nao permitida para esta metrica".
- **FR-004**: O sistema DEVE, quando a decisao e "permitido", retornar a definicao completa da metrica necessaria para montar a query subsequente (fonte, agregacao, unidade, dimensoes permitidas).
- **FR-005**: O sistema DEVE resolver, para um periodo perguntado, a versao da definicao de metrica cuja janela de vigencia contem integralmente esse periodo.
- **FR-006**: O sistema DEVE negar, com o motivo nomeado "periodo cruza fronteira de versao de metrica", qualquer pergunta cujo periodo abranja mais de uma versao de uma mesma metrica.
- **FR-007**: O sistema DEVE continuar resolvendo uma versao de metrica descontinuada (deprecated) para perguntas sobre periodos dentro da janela de vigencia dessa versao.
- **FR-008**: O sistema DEVE recusar carregar um catalogo que contenha duas metricas com o mesmo identificador, ou duas versoes de uma mesma metrica com janelas de vigencia sobrepostas.
- **FR-009**: O sistema DEVE emitir exatamente um evento de auditoria estruturado para cada decisao tomada (permitida ou negada), contendo a tupla avaliada, a decisao e o motivo quando negado.
- **FR-010**: O sistema NAO DEVE emitir a decisao ao chamador antes do evento de auditoria correspondente ter sido emitido.

### Key Entities *(include if feature involves data)*

- **Metric Definition**: representa uma metrica de negocio aprovada — nome/identificador, rotulo legivel, fonte, granularidade, agregacao, unidade, dimensoes permitidas, uma ou mais versoes com janela de vigencia (`effective_from` / `effective_until` opcional), e um estado (ativa ou descontinuada).
- **Dimension Definition**: representa uma dimensao de quebra permitida — identificador, tipo (enumerado, texto aberto, temporal) e a lista de metricas as quais esta associada.
- **Access Decision**: o resultado de uma avaliacao — decisao ("permitido"/"negado"), motivo nomeado quando negado, e a definicao de metrica resolvida quando permitido.
- **Audit Event**: registro imutavel de uma decisao tomada — tupla avaliada, decisao, motivo, timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das combinacoes de metrica+dimensao explicitamente aprovadas no catalogo de teste retornam decisao "permitido" — nenhum falso negativo para uma combinacao aprovada.
- **SC-002**: 100% das combinacoes envolvendo uma metrica ou dimensao nao aprovada retornam decisao "negado" com um motivo nomeado — nenhuma passagem silenciosa.
- **SC-003**: 100% das perguntas sobre um periodo dentro da janela de uma versao fechada de metrica (incluindo versoes descontinuadas) resolvem para a definicao correta dessa versao, verificado por teste com pelo menos duas versoes de uma mesma metrica.
- **SC-004**: A decisao nunca realiza uma chamada de rede ou banco de dados — verificavel por teste que falha se qualquer chamada externa for detectada durante a avaliacao.
- **SC-005**: O numero de eventos de auditoria emitidos e sempre exatamente igual ao numero de decisoes tomadas, verificado por teste com multiplas chamadas em sequencia.

## Assumptions

- O dominio de negocio usado nos exemplos e testes desta spec e sintetico/ilustrativo (metricas de um produto SaaS generico: `signups`, `monthly_recurring_revenue`, `active_users`) e nao representa nenhuma empresa real, conforme registrado no PRD.
- O conteudo inicial do catalogo (quais metricas/dimensoes existem de fato) e definido durante o plano e a implementacao desta spec, nao nesta especificacao — aqui se define o comportamento de decisao, nao o conteudo do catalogo.
- A forma de persistencia do catalogo (arquivo versionado no repositorio vs. banco de dados) e uma decisao de implementacao a tomar no plano; esta spec e agnostica a essa escolha.
- A execucao real de uma query contra um data warehouse esta fora do escopo desta spec — pertence ao proximo pacote do pipeline (execucao de query governada), que consome a decisao "permitido" e a definicao de metrica retornadas aqui.
- Nao ha ainda decisao sobre o primeiro canal de distribuicao real nem sobre observabilidade (OpenTelemetry) — irrelevantes para o escopo desta spec, que nao emite nenhuma comunicacao externa.
