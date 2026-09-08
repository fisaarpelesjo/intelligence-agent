# Data Model: Distribuicao proativa

## ChannelGateConfig

| Campo | Tipo |
|---|---|
| `channel_id` | texto |
| `enabled` | booleano |
| `allowed_raw_sender_ids` | conjunto de texto |

## DistributionOutcome

| Campo | Tipo | Notas |
|---|---|---|
| `originated` | booleano | |
| `reason_code` | texto ou nulo | Preenchido quando `originated=False`; tambem repassado se `integracao_canal.entregar` recusar |
| `delivery_outcome` | `DeliveryOutcome` (de `integracao_canal`) ou nulo | Preenchido somente quando `entregar()` chegou a ser chamado |

## Campos rotulados da mensagem (derivados de `PrioritizedInsight`)

| Rotulo | Origem |
|---|---|
| `identificador` | `insight.candidate.identifier` |
| `rank` | `insight.rank` |
| `impact_score` | `insight.impact_score` |
| `reach_score` | `insight.reach_score` |

Cada linha enviada segue o formato `"<rotulo>: <valor>"`.
