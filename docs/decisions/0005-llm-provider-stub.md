# LLM provider: stub/fake para o MVP, provider real adiado

## Status

Accepted

## Context and Problem Statement

CON-003 ja exige que qualquer LLM provider seja acessado via uma interface abstrata `LLMProvider`. Falta decidir qual provider concreto usar no MVP para narrar respostas ja calculadas (o LLM nunca calcula, so narra — Principio II).

## Decision Drivers

- O LLM, nesta arquitetura, so formata texto a partir de um resultado ja calculado — nao precisa de um modelo sofisticado para o MVP funcionar e ser testado.
- Depender de uma API key real desde o inicio adiciona custo e um ponto de falha externo aos testes.
- A interface abstrata ja isola essa escolha do resto do dominio (CON-003).

## Considered Options

- Anthropic Claude.
- OpenAI.
- Um `LLMProvider` stub/fake que formata o resultado num template de texto fixo, sem chamar nenhuma API real.

## Decision Outcome

Implementar um `LLMProvider` stub para o MVP: narra o resultado calculado usando um template de texto determinístico (sem chamada de rede). A escolha de um provider real (Anthropic, OpenAI, ou outro) fica adiada para quando a qualidade da narrativa em linguagem natural precisar ser avaliada de verdade — nesse ponto, basta implementar `LLMProvider` de novo, sem tocar no restante do pipeline.

## Positive Consequences

- Pacote de interacao conversacional pode ser especificado, implementado e testado sem nenhuma credencial ou custo de API.
- Trocar para um provider real depois e uma implementacao adicional de `LLMProvider`, nao uma mudanca de contrato.

## Negative Consequences

- A narrativa do MVP e mais mecanica/template do que uma narrativa gerada por LLM real — aceitavel para validar o pipeline de governanca antes de investir em qualidade de linguagem natural.

## Evidence

PRD `docs/requirements/project-requirements.md`, CON-003; mesmo padrao de port+fake ja usado em `execucao_query` (`DataSource`/`FakeDataSource`) e nesta decisao para `Channel` (ADR-0001).
