# Feature Specification: Execucao de query governada

**Feature Branch**: `002-execucao-query`

**Created**: 2026-09-07

**Status**: Draft

**Input**: PRD `docs/requirements/project-requirements.md` (FR-002, FR-013, NFR-004, CON-001); Constitution (Principio I); consome a saida de `catalogo_semantico` (spec `001-catalogo-semantico`)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Executar uma pergunta ja autorizada (Priority: P1)

Dada uma decisao de autorizacao ja "permitido" do catalogo semantico (versao de metrica resolvida), mais um filtro estruturado opcional (dimensao, operador, valores) e o periodo, o sistema compila uma consulta somente-leitura restrita a essa definicao e retorna o resultado agregado.

**Why this priority**: E o unico ponto do pipeline que efetivamente le dado de negocio (Constitution Principio I) — sem ele, a decisao do catalogo nunca produz uma resposta.

**Independent Test**: Chamar `executar()` com uma decisao permitida (produzida por um fixture) e uma fonte de dados falsa (`FakeDataSource`) injetada, e verificar o resultado retornado, sem tocar em nenhuma fonte de dados real.

**Acceptance Scenarios**:

1. **Given** uma decisao "permitido" com a versao de metrica de `signups`, um filtro `country = "BR"` e um periodo valido, **When** a query e executada, **Then** o resultado contem o valor agregado, a fonte (`source_view`) e a unidade da metrica.
2. **Given** a mesma decisao, sem filtro de dimensao, **When** a query e executada, **Then** o resultado e retornado sem quebra por dimensao (agregado total do periodo).

---

### User Story 2 - Recusar operador ou filtro nao permitido (Priority: P1)

O sistema recusa qualquer filtro que use um operador fora da allowlist (`eq`, `ne`, `in`, `not_in`) — em particular pattern/regex e checagem de nulo — antes de compilar qualquer consulta.

**Why this priority**: E a defesa estrutural contra query livre disfarcada de filtro (PRD FR-013); sem ela, a allowlist de operadores do catalogo e apenas decorativa.

**Independent Test**: Chamar `executar()` com um operador fora da allowlist e verificar que a execucao e recusada sem qualquer chamada a fonte de dados (nem `dry_run`, nem `execute`).

**Acceptance Scenarios**:

1. **Given** um filtro com operador `regex`, **When** a query e avaliada, **Then** a execucao e recusada com o motivo nomeado "operador nao permitido", e nem `dry_run` nem `execute` da fonte de dados sao chamados.
2. **Given** uma decisao "negado" vinda do catalogo semantico (autorizacao nao concedida), **When** `executar()` e chamado mesmo assim, **Then** o sistema recusa com o motivo nomeado "acesso nao autorizado" — defesa em profundidade, nunca confia apenas no chamador ter checado a decisao antes.

---

### User Story 3 - Recusar execucao que excederia o teto de custo (Priority: P2)

Antes de executar de fato, o sistema consulta um `dry_run` na fonte de dados para estimar bytes faturados e linhas retornadas; se qualquer teto configurado seria excedido, a execucao real nunca acontece.

**Why this priority**: Protege custo operacional e evita truncamento silencioso de resultado (PRD NFR-004).

**Independent Test**: Injetar uma `FakeDataSource` cujo `dry_run` retorna uma estimativa acima do teto configurado, e verificar que `execute()` da fonte de dados nunca e chamado.

**Acceptance Scenarios**:

1. **Given** um `dry_run` que estima mais bytes do que o teto configurado, **When** a query e avaliada, **Then** a execucao e recusada com o motivo nomeado "teto de custo excedido" e `execute()` nunca e chamado.
2. **Given** um `dry_run` que estima mais linhas do que o teto configurado, **When** a query e avaliada, **Then** a execucao e recusada com o motivo nomeado "teto de linhas excedido" e `execute()` nunca e chamado.
3. **Given** um `dry_run` dentro de ambos os tetos, **When** a query e avaliada, **Then** `execute()` e chamado exatamente uma vez e seu resultado e retornado.

---

### Edge Cases

- O que acontece quando a fonte de dados falha durante `dry_run` ou `execute` (excecao de infraestrutura)? O sistema deve propagar uma recusa nomeada ("fonte de dados indisponivel"), nunca deixar uma excecao crua vazar como se fosse um resultado.
- O que acontece quando o filtro usa uma dimensao que nao esta em `allowed_dimensions` da versao de metrica resolvida (o catalogo ja deveria ter negado isso, mas o chamador pode montar a chamada errado)? O sistema recusa de novo aqui — defesa em profundidade, mesma logica de "nunca confiar so no chamador".
- O que acontece com um filtro `in`/`not_in` com lista de valores vazia? Recusado com "operador nao permitido" (lista vazia nunca produz um filtro util, tratado como uso invalido do operador).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE recusar a execucao, com o motivo nomeado "acesso nao autorizado", quando a decisao de autorizacao recebida nao for "permitido" — independente do que o chamador afirme.
- **FR-002**: O sistema DEVE permitir somente os operadores `eq`, `ne`, `in`, `not_in` num filtro; qualquer outro operador (incluindo pattern, regex, checagem de nulo, ou lista vazia em `in`/`not_in`) e recusado com o motivo nomeado "operador nao permitido", sem compilar nem executar nenhuma query.
- **FR-003**: O sistema DEVE recusar, com o motivo "dimensao nao permitida", um filtro cuja dimensao nao esteja em `allowed_dimensions` da versao de metrica resolvida.
- **FR-004**: O sistema DEVE, antes de executar a query real, obter uma estimativa de custo (`dry_run`) da fonte de dados injetada.
- **FR-005**: O sistema DEVE recusar a execucao, com o motivo "teto de custo excedido" ou "teto de linhas excedido" conforme o caso, quando a estimativa de `dry_run` ultrapassar o teto configurado — sem chamar `execute()`.
- **FR-006**: O sistema DEVE chamar `execute()` da fonte de dados exatamente uma vez quando `dry_run` estiver dentro dos tetos, e retornar o resultado ao chamador.
- **FR-007**: O sistema DEVE capturar qualquer excecao levantada pela fonte de dados (em `dry_run` ou `execute`) e traduzi-la para uma recusa nomeada "fonte de dados indisponivel", nunca deixando a excecao original propagar.
- **FR-008**: O sistema NAO DEVE ter nenhum metodo de escrita na interface de fonte de dados — a interface e estruturalmente somente leitura.

### Key Entities *(include if feature involves data)*

- **QueryFilter**: dimensao (opcional), operador (`eq`/`ne`/`in`/`not_in`), valor(es).
- **QueryRequest**: decisao de autorizacao do catalogo (com a versao de metrica resolvida), `QueryFilter` opcional, periodo.
- **CostEstimate**: bytes estimados, linhas estimadas (retornado por `dry_run`).
- **QueryResult**: valor agregado, `source_view`, unidade, contagem de linhas retornadas.
- **ExecutionOutcome**: sucesso (booleano), motivo nomeado quando recusado, `QueryResult` quando bem-sucedido.
- **DataSource** (porta/interface): `dry_run(request) -> CostEstimate`, `execute(request) -> QueryResult`. Nenhum metodo de escrita.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das execucoes com decisao de autorizacao "negado" sao recusadas antes de qualquer chamada a fonte de dados.
- **SC-002**: 100% dos filtros com operador fora da allowlist sao recusados sem nenhuma chamada a `dry_run` ou `execute`.
- **SC-003**: 100% das execucoes cujo `dry_run` excede qualquer teto configurado nunca chamam `execute()`.
- **SC-004**: 100% das excecoes levantadas pela fonte de dados injetada sao traduzidas em uma recusa nomeada — nenhuma excecao crua atravessa a fronteira publica de `executar()`.
- **SC-005**: Uma execucao bem-sucedida chama `execute()` exatamente uma vez — nunca zero, nunca mais de uma.

## Assumptions

- Esta feature nao integra com nenhum data warehouse real (BigQuery ou equivalente); a interface `DataSource` e um port abstrato, e os testes usam uma implementacao falsa em memoria (`FakeDataSource`). A escolha e integracao do data warehouse real e uma decisao de implementacao futura (ADR), fora do escopo desta spec.
- Os tetos de custo (bytes) e de linhas sao parametros de configuracao desta feature — os valores concretos por ambiente ainda nao foram decididos (ver PRD, NFR-004, ja registrado como questao aberta) e nao bloqueiam esta implementacao, que os recebe como parametro injetavel.
- Esta feature depende da spec `001-catalogo-semantico` para produzir a decisao de autorizacao e a versao de metrica resolvida consumidas aqui.
