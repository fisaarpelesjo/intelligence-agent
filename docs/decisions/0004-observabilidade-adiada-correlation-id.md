# Observabilidade: apenas correlation ID por enquanto, OpenTelemetry adiado

## Status

Accepted

## Context and Problem Statement

NFR-002 exige rastreabilidade ponta a ponta via correlation ID e traces compativeis com OpenTelemetry. Implementar a stack completa de observabilidade agora, ou adiar?

## Decision Drivers

- Nao ha ainda infraestrutura de producao real (collector, dashboard) para os traces serem uteis.
- Adicionar OpenTelemetry agora aumenta a complexidade de um projeto que ainda esta em fase de bibliotecas puras, sem deploy.
- Um identificador de correlacao (string, gerado por chamada) ja permite reconstruir a jornada de uma requisicao nos testes e logs locais, sem dependencia externa.

## Considered Options

- Implementar OpenTelemetry (SDK + exporter) desde ja.
- Usar apenas um correlation ID (string, ex. UUID) propagado explicitamente, sem tracing distribuido.
- Nao rastrear nada ainda.

## Decision Outcome

Cada decisao/execucao/mensagem carrega um `correlation_id` (string) gerado ou propagado pelo chamador. Integracao real com OpenTelemetry (collector, exporter, dashboard) fica adiada para quando houver infraestrutura de producao real a instrumentar.

## Positive Consequences

- Satisfaz a parte "rastreavel ponta a ponta" do NFR-002 sem dependencia externa.
- Migrar para OpenTelemetry depois e aditivo (o correlation_id vira um atributo do span), nao uma reescrita.

## Negative Consequences

- Sem exporter/collector real, não há visualização de trace automática ainda — seria feito lendo logs/eventos manualmente até a integração real.

## Evidence

PRD `docs/requirements/project-requirements.md`, secao "Decisoes que exigem ADR" (ADR-0004) e NFR-002.
