# Contratos: memoria e inbound

## `InMemoryConversationMemory.registrar_turno(turn: ConversationTurn) -> None`

Acrescenta `turn` a lista interna indexada por `turn.registry_ref`. Nao valida nem deduplica.

## `InMemoryConversationMemory.turnos_recentes(registry_ref, reference_now, max_age) -> list[ConversationTurn]`

1. Se `max_age <= timedelta(0)` -> retornar `[]`.
2. Buscar a lista de turnos para `registry_ref` (vazia se nao existir).
3. Retornar somente os turnos cujo `reference_now - recorded_at <= max_age`, na ordem em que foram registrados.

## `processar_mensagem_inbound(payload: object) -> InboundOutcome`

Sempre retorna `InboundOutcome(accepted=False, reason_code="inbound_desabilitado")`, para qualquer `payload`. A assinatura desta funcao nao inclui nenhum parametro do tipo `ConversationMemory` — verificado por teste com `inspect.signature`.
