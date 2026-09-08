# Data Model: Integracao de canal

## RegistryRef

Alias de texto (`str`) — identificador opaco, derivado, nunca o identificador bruto do canal.

## IdentityRegistry (Protocol)

| Metodo | Assinatura |
|---|---|
| `resolve` | `(channel_id: str, raw_sender_id: str) -> RegistryRef` |

Idempotente: o mesmo par `(channel_id, raw_sender_id)` sempre retorna o mesmo `RegistryRef`.

## ChannelCapability

| Campo | Tipo |
|---|---|
| `channel_id` | texto |
| `max_message_length` | inteiro |
| `supports_multiple_messages` | booleano |

## DeliveryPlan

| Campo | Tipo | Notas |
|---|---|---|
| `blocks` | lista de lista de texto | Cada bloco e uma lista de sentencas inteiras; a concatenacao de todas as sentencas de todos os blocos, na ordem, reproduz a entrada exata |

## Channel (Protocol)

| Membro | Tipo |
|---|---|
| `capability` | `ChannelCapability` |
| `send` | `(registry_ref: RegistryRef, text: str) -> None` (pode levantar excecao) |

## DeliveryOutcome

| Campo | Tipo | Notas |
|---|---|---|
| `success` | booleano | |
| `reason_code` | texto ou nulo | `sentenca_excede_capacidade`, `canal_nao_suporta_multiplas_mensagens`, `falha_no_envio` |
| `blocks_sent` | inteiro | Numero de blocos efetivamente enviados antes de uma falha, ou o total quando `success=True` |
