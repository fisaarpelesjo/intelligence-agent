# Cadencia do relatorio periodico: diaria

## Status

Accepted

## Context and Problem Statement

O pacote de relatorio periodico precisa de uma cadencia definida (diaria, semanal, outra) para ser especificado e implementado.

## Decision Drivers

- Simplicidade de especificacao e teste no primeiro recorte.
- Cadencia semanal pode ser adicionada depois como uma variacao, sem redesenhar o pacote (o agregador de KPIs e o mesmo, muda so a janela e o agendamento externo).

## Considered Options

- Diaria.
- Semanal.
- Adiar a especificacao deste pacote inteiramente.

## Decision Outcome

Cadencia diaria para a primeira versao do relatorio periodico. Cadencia semanal fica no "waiting room" do PRD como variacao futura.

## Positive Consequences

- Reduz o escopo do primeiro recorte deste pacote a uma unica janela de agregacao.

## Negative Consequences

- Se o uso real preferir cadencia semanal, havera trabalho de ajuste (baixo, dado o desenho do agregador).

## Evidence

PRD `docs/requirements/project-requirements.md`, secao "Decisoes que exigem ADR" (ADR-0003) e "Waiting room ou requisitos futuros".
