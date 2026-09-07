# Canal real de distribuicao: adiado, usar um port fake por enquanto

## Status

Accepted

## Context and Problem Statement

O pipeline (interacao conversacional e distribuicao proativa) precisa entregar mensagens a um usuario final atraves de algum canal externo (Telegram, WhatsApp, Slack, etc.). Qual canal integrar primeiro, e quando?

## Decision Drivers

- Nao travar a implementacao dos pacotes 003/004/007 esperando uma decisao de canal.
- O proprio principio de `channel_integration` ja diz "canal nunca e autoridade" — a logica de dominio nao deveria depender dos detalhes de um canal especifico.
- Custo de trocar de canal depois deve ser baixo se a interface for bem desenhada agora.

## Considered Options

- Integrar Telegram imediatamente (API HTTP simples, sem aprovacao de app).
- Integrar WhatsApp Business API (mais alcance, mais burocracia).
- Integrar Slack (bom para uso interno).
- Definir uma interface `Channel` abstrata e usar uma implementacao fake (console/em memoria) ate decidir o canal real.

## Decision Outcome

Definir uma interface `Channel` abstrata (analoga ao `DataSource` do pacote `execucao_query`) e usar uma implementacao fake para desenvolvimento e teste dos pacotes 003, 004 e 007. A escolha do canal real fica adiada para quando houver necessidade real de entrega — a interface e o unico compromisso assumido agora.

## Positive Consequences

- Pacotes 003/004/007 podem ser especificados, implementados e testados sem nenhuma credencial ou integracao externa.
- Trocar de canal real no futuro exige apenas uma nova implementacao de `Channel`, sem tocar a logica de dominio.

## Negative Consequences

- Nenhuma entrega real acontece ate esta decisao ser revisitada — aceitavel para o estagio atual do projeto (sem usuarios reais ainda).

## Evidence

PRD `docs/requirements/project-requirements.md`, secao "Decisoes que exigem ADR" (ADR-0001); mesmo padrao ja usado em `packages/execucao_query` (`DataSource` port + `FakeDataSource`).
