# Data Model: Memoria de conversa

## ConversationTurn

| Campo | Tipo |
|---|---|
| `registry_ref` | `RegistryRef` (de `integracao_canal`) |
| `metric_id` | texto |
| `period_expression` | texto |
| `recorded_at` | data/hora |

## ConversationMemory (comportamento de `InMemoryConversationMemory`)

| Metodo | Assinatura | Notas |
|---|---|---|
| `registrar_turno` | `(turn: ConversationTurn) -> None` | Acrescenta a lista interna da identidade |
| `turnos_recentes` | `(registry_ref: RegistryRef, reference_now: datetime, max_age: timedelta) -> list[ConversationTurn]` | Filtra por `reference_now - turn.recorded_at <= max_age`; `max_age <= timedelta(0)` sempre retorna `[]` |

## InboundOutcome

| Campo | Tipo | Valor |
|---|---|---|
| `accepted` | booleano | sempre `False` nesta versao |
| `reason_code` | texto | sempre `"inbound_desabilitado"` |
