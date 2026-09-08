# Feature Specification: Deteccao de anomalia

**Feature Branch**: `005-deteccao-anomalia`

**Created**: 2026-09-08

**Status**: Draft

**Input**: PRD (FR-005); ADR-0006 (regra de baseline: media movel + limiar percentual, `Proposed`); consome `catalogo_semantico` (spec 001) e `execucao_query` (spec 002)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Detectar um candidate finding quando o desvio ultrapassa o limiar (Priority: P1)

Dada uma regra de deteccao (metrica, janela de dias da baseline, limiar percentual), o sistema calcula a media movel dos `window_days` dias anteriores ao dia observado, compara com o valor observado, e produz um candidate finding quando o desvio percentual absoluto ultrapassa o limiar — contendo o valor observado, a baseline, o desvio e a direcao (aumento/queda), sem afirmar causa.

**Why this priority**: E a capacidade central do pacote; sem ela nao ha deteccao.

**Independent Test**: Chamar `detectar()` com uma `FakeDataSource` configurada para retornar um valor observado muito acima da media dos dias anteriores, e verificar que o finding e produzido com os campos corretos.

**Acceptance Scenarios**:

1. **Given** uma regra com `window_days=7` e `threshold_pct=20`, um valor observado 50% acima da media dos 7 dias anteriores, **When** avaliada, **Then** o resultado e `triggered=True`, com `finding.direction="increase"` e `finding.deviation_pct` proximo de 50.
2. **Given** a mesma regra, um valor observado 40% abaixo da media, **When** avaliada, **Then** `triggered=True` com `finding.direction="decrease"`.

---

### User Story 2 - Nao detectar quando o desvio esta dentro do limiar (Priority: P1)

Quando o valor observado esta dentro do limiar configurado em relacao a baseline, o sistema nao produz um finding.

**Why this priority**: Sem isso, toda variacao normal viraria alerta — o oposto do proposito do limiar.

**Independent Test**: Chamar `detectar()` com um valor observado proximo da media (dentro do limiar) e verificar `triggered=False`, `finding=None`.

**Acceptance Scenarios**:

1. **Given** a mesma regra (`threshold_pct=20`), um valor observado 5% acima da media, **When** avaliada, **Then** `triggered=False` e `finding` e `None`.
2. **Given** um dos dias da janela de baseline indisponivel no catalogo/execucao, **When** avaliada, **Then** o resultado e `triggered=False` com o motivo nomeado "baseline_incompleta" — a baseline nunca e calculada com dado parcial.
3. **Given** a baseline calculada e exatamente zero, **When** o desvio percentual e calculado, **Then** o resultado e `triggered=False` com o motivo nomeado "baseline_zero", nunca um desvio percentual infinito.

---

### User Story 3 - O pacote nunca se auto-origina (Priority: P1)

O codigo-fonte deste pacote nao importa nenhum modulo de scheduling, timer ou threading — a decisao de quando rodar a deteccao e sempre externa ao pacote.

**Why this priority**: Constitution e PRD FR-005 exigem que a deteccao seja determinada externamente e auditavel; o pacote em si nunca decide seu proprio agendamento.

**Independent Test**: Percorrer o codigo-fonte do pacote com `ast` e verificar que nenhum modulo `threading`, `sched` ou `time` (alem de `datetime`) e importado.

**Acceptance Scenarios**:

1. **Given** o codigo-fonte de `packages/deteccao_anomalia/src`, **When** analisado por AST, **Then** nenhuma importacao de `threading`, `sched` ou `time` e encontrada.

---

### Edge Cases

- O que acontece quando o valor observado (dia avaliado) esta indisponivel? O resultado e `triggered=False` com o motivo nomeado "observado_indisponivel", sem tentar calcular a baseline.
- O que acontece com `window_days=0`? E um erro de configuracao da regra — a funcao recusa com um motivo nomeado ("janela_invalida") em vez de calcular uma media de zero pontos.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE calcular a baseline como a media aritmetica dos valores executados dos `window_days` dias imediatamente anteriores ao dia observado.
- **FR-002**: O sistema NAO DEVE calcular uma baseline parcial — se qualquer um dos `window_days` dias estiver indisponivel (autorizacao ou execucao recusada), o resultado e "baseline_incompleta", sem calcular media com os dias restantes.
- **FR-003**: O sistema DEVE produzir um candidate finding (`triggered=True`) quando o desvio percentual absoluto entre o valor observado e a baseline ultrapassar `threshold_pct`; caso contrario, `triggered=False`.
- **FR-004**: O sistema DEVE recusar o calculo do desvio com o motivo nomeado "baseline_zero" quando a baseline calculada for exatamente zero, nunca retornando um desvio infinito.
- **FR-005**: O candidate finding DEVE conter o valor observado, o valor da baseline, o desvio percentual, a direcao (`increase`/`decrease`) e os parametros da regra aplicada (`window_days`, `threshold_pct`) — nunca uma afirmacao de causa.
- **FR-006**: O codigo-fonte do pacote NAO DEVE importar `threading`, `sched` nem `time` em nenhum modulo.

### Key Entities *(include if feature involves data)*

- **AnomalyRule**: `metric_id`, `dimension_id`/`dimension_value` opcionais, `window_days`, `threshold_pct`.
- **CandidateFinding**: `metric_id`, `observed_date`, `observed_value`, `baseline_value`, `deviation_pct`, `direction`, `window_days`, `threshold_pct`.
- **DetectionOutcome**: `triggered` (booleano), `finding` (`CandidateFinding` ou nulo), `reason_code` (texto ou nulo, presente quando `triggered=False` por indisponibilidade/erro de configuracao — nao quando simplesmente dentro do limiar).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos desvios que ultrapassam o limiar configurado produzem um finding com a direcao correta.
- **SC-002**: 100% dos desvios dentro do limiar retornam `triggered=False` sem finding.
- **SC-003**: 0% dos calculos usam uma baseline parcial — qualquer dia indisponivel na janela recusa o calculo inteiro.
- **SC-004**: 0% dos calculos com baseline zero retornam um desvio percentual infinito ou indefinido.
- **SC-005**: 0 importacoes de `threading`, `sched` ou `time` em todo o codigo-fonte do pacote.

## Assumptions

- A regra de baseline (media movel + limiar percentual) e a decisao registrada em ADR-0006, com status `Proposed` — pode ser revisada quando houver dado real para validar.
- `window_days` e `threshold_pct` sao configuracao por regra, injetada pelo chamador — nao ha valor default fixo no codigo.
- O agendamento de quando rodar a deteccao (diario, a cada hora, etc.) e responsabilidade de um chamador externo (ex.: um cron job ou o proprio `relatorio_periodico`), fora do escopo desta spec.
- Nao ha priorizacao nem distribuicao do finding nesta spec — isso pertence a pacotes futuros (`insights_prioritisation`, `proactive_distribution`), fora de escopo aqui.
