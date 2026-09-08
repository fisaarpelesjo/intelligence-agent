# Regra de deteccao de anomalia: media movel de N dias + limiar percentual

## Status

Proposed

## Context and Problem Statement

O pacote de deteccao de anomalia precisa de uma regra concreta para decidir quando um valor observado constitui um "candidate finding" — ou seja, o que conta como baseline e o que conta como desvio relevante. Esta e uma decisao de produto (nao so de engenharia), ainda nao tomada explicitamente.

## Decision Drivers

- Precisa de uma regra simples de explicar e auditar (Constitution Principio II — deterministico, nunca uma caixa-preta estatistica complexa).
- Precisa ser calculavel a partir do que `execucao_query` ja oferece (uma query por dia), sem infraestrutura nova.
- Deve ser facilmente configuravel/trocavel por metrica, sem exigir redesenho do pacote.

## Considered Options

- Media movel dos N dias imediatamente anteriores ao dia observado, com limiar de desvio percentual configuravel.
- Media do mesmo dia da semana nas ultimas K semanas (controla sazonalidade semanal), com limiar percentual.
- Desvio-padrao / z-score sobre uma janela historica.
- Adiar a especificacao deste pacote inteiramente ate haver uma decisao de produto formal.

## Decision Outcome

Adotar media movel dos N dias imediatamente anteriores ao dia observado (`window_days`, configuravel, default sugerido 7) como baseline, e disparar um candidate finding quando o desvio percentual absoluto entre o valor observado e essa media ultrapassar um limiar configuravel (`threshold_pct`, sem default fixo no codigo — decidido por regra, por metrica). Esta e uma escolha de engenharia deliberadamente simples e revisavel, nao uma decisao estatistica definitiva — o status desta ADR fica `Proposed` (nao `Accepted`) ate o autor validar a regra com dado real.

## Positive Consequences

- Regra auditavel: qualquer pessoa consegue recalcular a media e o desvio a mao.
- `window_days` e `threshold_pct` sao parametros por regra, nao constantes globais — permite ajuste por metrica sem mudar codigo.

## Negative Consequences

- Nao controla sazonalidade (ex.: fim de semana vs dia util) — uma metrica com padrao semanal forte pode gerar falso positivo. Mitigacao futura: trocar por media do mesmo dia da semana (uma das alternativas consideradas), sem mudar a interface publica do pacote.
- Janela de N dias com qualquer dia indisponivel recusa o calculo inteiro (nao usa media parcial) — decisao conservadora para nao mascarar uma baseline incompleta como se fosse completa.

## Evidence

PRD `docs/requirements/project-requirements.md`, FR-005; spec `005-deteccao-anomalia`.
