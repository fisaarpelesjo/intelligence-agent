# Feature Specification: Relatorio periodico

**Feature Branch**: `004-relatorio-periodico`

**Created**: 2026-09-08

**Status**: Draft

**Input**: PRD (FR-008); ADR-0003 (cadencia diaria); consome `catalogo_semantico` (spec 001) e `execucao_query` (spec 002)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Gerar o relatorio diario de KPIs (Priority: P1)

Dada uma lista configurada de KPIs (metricas), o sistema gera o relatorio do dia anterior (ultimo dia completo, ADR-0003): para cada KPI, autoriza e executa; inclui o valor no relatorio quando bem-sucedido, ou marca o KPI como indisponivel com motivo nomeado quando a autorizacao ou execucao recusar — sem falhar o relatorio inteiro por causa de um unico KPI indisponivel.

**Why this priority**: E o produto central deste pacote; sem ele nao ha relatorio.

**Independent Test**: Chamar `gerar_relatorio_diario()` com uma lista de KPIs (alguns validos, um invalido), um catalogo de teste e uma `FakeDataSource`, e verificar que o relatorio contem todos os KPIs, uns com valor e outro marcado indisponivel.

**Acceptance Scenarios**:

1. **Given** uma lista de 3 KPIs validos e aprovados, **When** o relatorio e gerado para uma data de referencia, **Then** o relatorio contem os 3 resultados, cada um com valor, unidade e fonte, referentes ao dia anterior a data de referencia.
2. **Given** uma lista com 2 KPIs validos e 1 KPI cuja metrica e desconhecida no catalogo, **When** o relatorio e gerado, **Then** o relatorio contem 3 entradas — 2 com valor e 1 marcada indisponivel com o motivo nomeado — e a geracao nao lanca excecao nem aborta.

---

### User Story 2 - Avaliar alerta por regra de limiar, independente do relatorio (Priority: P1)

Dada uma lista configurada de regras de alerta (metrica, limiar, direcao), o sistema avalia cada regra contra o valor executado do dia anterior e determina se dispara — como uma chamada e um tipo de retorno completamente separados do relatorio.

**Why this priority**: Regras de alerta atendem um publico e uma cadencia de leitura diferentes do relatorio (PRD, secao Requisitos funcionais); nunca devem se fundir.

**Independent Test**: Chamar `avaliar_alertas()` isoladamente (sem chamar `gerar_relatorio_diario()`) com uma regra cujo valor executado ultrapassa o limiar, e verificar que o alerta dispara.

**Acceptance Scenarios**:

1. **Given** uma regra de alerta com direcao "acima" e limiar 100, e o valor executado e 150, **When** avaliada, **Then** o alerta dispara (`triggered=True`).
2. **Given** a mesma regra, **When** o valor executado e 50, **Then** o alerta nao dispara (`triggered=False`).
3. **Given** uma regra cuja metrica e desconhecida no catalogo, **When** avaliada, **Then** o alerta nao dispara e carrega um motivo nomeado de indisponibilidade — nunca lanca excecao.

---

### User Story 3 - Relatorio e alerta nunca se fundem (Priority: P2)

`gerar_relatorio_diario()` e `avaliar_alertas()` sao duas funcoes com dois tipos de retorno distintos (`DailyReport` e `AlertBundle`); nao existe nenhuma funcao ou tipo que combine os dois.

**Why this priority**: Garante estruturalmente a separacao exigida pelo PRD, verificavel por inspecao do codigo-fonte, nao apenas por convencao.

**Independent Test**: Inspecionar o modulo publico do pacote e confirmar que `DailyReport` e `AlertBundle` nao compartilham nenhum campo, e que nenhuma funcao publica retorna os dois combinados.

**Acceptance Scenarios**:

1. **Given** o modulo publico do pacote, **When** inspecionado, **Then** `DailyReport` e `AlertBundle` sao dataclasses distintas, sem campo em comum, e nenhuma funcao publica retorna uma tupla ou objeto que combine ambas.

---

### Edge Cases

- O que acontece se a lista de KPIs ou de regras de alerta estiver vazia? O relatorio/bundle e retornado vazio, sem erro.
- O que acontece se a mesma metrica aparecer tanto num KPI do relatorio quanto numa regra de alerta? Cada chamada (`gerar_relatorio_diario`, `avaliar_alertas`) executa a query de forma independente — nao ha cache compartilhado nesta versao.
- O que acontece se `execucao_query` recusar por teto de custo excedido? O KPI/alerta correspondente e marcado indisponivel com esse motivo, igual a qualquer outra recusa.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE gerar o relatorio para o ultimo dia completo (dia anterior a data de referencia injetada), nunca para o dia corrente (ainda parcial).
- **FR-002**: O sistema DEVE incluir, para cada KPI configurado, um resultado com valor/unidade/fonte quando autorizado e executado com sucesso, ou uma marca de indisponibilidade com motivo nomeado quando a autorizacao ou execucao recusar — sem abortar o relatorio inteiro.
- **FR-003**: O sistema DEVE avaliar cada regra de alerta de forma independente do relatorio, comparando o valor executado do dia anterior contra o limiar configurado na direcao configurada (acima/abaixo).
- **FR-004**: O sistema NAO DEVE lancar excecao quando uma regra de alerta referenciar uma metrica indisponivel — deve marcar a regra como nao avaliavel com motivo nomeado.
- **FR-005**: O sistema NAO DEVE ter nenhum tipo ou funcao publica que combine `DailyReport` e `AlertBundle` numa unica saida.

### Key Entities *(include if feature involves data)*

- **KpiDefinition**: `metric_id`, `dimension_id`/`dimension_value` opcionais.
- **KpiResult**: `metric_id`, disponivel (booleano), valor/unidade/fonte quando disponivel, motivo nomeado quando nao.
- **DailyReport**: `report_date`, lista de `KpiResult`.
- **AlertRule**: `metric_id`, `threshold`, `direction` (`above`/`below`).
- **AlertResult**: `metric_id`, `evaluated` (booleano — falso quando a metrica estava indisponivel), `triggered` (booleano), `value` quando avaliado, motivo nomeado quando nao avaliado.
- **AlertBundle**: `report_date`, lista de `AlertResult`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos KPIs configurados aparecem no relatorio (disponiveis ou marcados indisponiveis) — nunca um KPI silenciosamente ausente.
- **SC-002**: 0% das chamadas a `gerar_relatorio_diario()` ou `avaliar_alertas()` lancam excecao nao tratada devido a uma metrica indisponivel.
- **SC-003**: 100% das regras de alerta cujo valor executado ultrapassa o limiar na direcao configurada disparam; 0% das que nao ultrapassam disparam.
- **SC-004**: `DailyReport` e `AlertBundle` nunca compartilham um campo — verificavel por inspecao dos `dataclasses.fields()` de cada tipo.

## Assumptions

- O escopo desta spec e a geracao do relatorio/alerta em memoria; a entrega por canal (Telegram, etc.) esta fora de escopo — adiada por ADR-0001, igual as demais specs.
- A cadencia e diaria (ADR-0003); cadencia semanal fica no waiting room do PRD.
- A lista de KPIs e de regras de alerta e configuracao injetada pelo chamador (lista de `KpiDefinition`/`AlertRule`) — nao ha descoberta automatica de metricas nesta versao.
