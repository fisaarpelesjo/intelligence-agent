# Conteudo do catalogo semantico: YAML sintetico versionado no repositorio

## Status

Accepted

## Context and Problem Statement

O pacote `catalogo_semantico` precisa de um conjunto real de definicoes de metrica/dimensao para funcionar e ser testado. De onde vem esse conteudo, e em que formato?

## Decision Drivers

- Este e um projeto pessoal com dominio de negocio sintetico/ilustrativo (nao ha empresa real por tras dos numeros).
- O formato deve ser legivel, versionavel em git, e facil de validar (integridade, sobreposicao de versao).
- Nao ha ainda nenhuma fonte de dado real (data warehouse) integrada.

## Considered Options

- Banco de dados dedicado para o catalogo.
- Arquivos YAML versionados no proprio pacote.
- Formato binario ou JSON gerado por ferramenta externa.

## Decision Outcome

Arquivos YAML em `packages/catalogo_semantico/catalog/` (`metrics.yaml`, `dimensions.yaml`, `owners.yaml`), carregados e validados em memoria por `carregar_catalogo()`. Conteudo inicial e sintetico (`signups`, `monthly_recurring_revenue`, `active_users`), representando um produto SaaS generico fictício.

## Positive Consequences

- Zero infraestrutura adicional; o catalogo e revisavel em qualquer PR como texto.
- Integridade (IDs duplicados, janelas de versao sobrepostas) e validada na carga, com testes cobrindo isso.

## Negative Consequences

- Nao reflete nenhum dado de negocio real; ao integrar um data warehouse real, o conteudo do catalogo precisara ser substituido ou expandido por definicoes reais, aprovadas por um dono de produto real.

## Evidence

Implementado em `packages/catalogo_semantico/` (spec `001-catalogo-semantico`); PRD, secao "Decisoes que exigem ADR" (ADR-0002).
