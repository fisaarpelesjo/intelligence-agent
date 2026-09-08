# Contratos: identidade e entrega

## `resolver_identidade(registry: IdentityRegistry, channel_id: str, raw_sender_id: str) -> RegistryRef`

Delega inteiramente a `registry.resolve(channel_id, raw_sender_id)`. Nao contem logica propria de derivacao — a estrategia de derivacao pertence a implementacao do registro (a fake usa um contador incremental por par unico, mas isso e um detalhe de implementacao, nao parte do contrato).

## `planejar_entrega(capability: ChannelCapability, sentences: list[str]) -> DeliveryPlan | str`

Retorna um `DeliveryPlan` ou uma string com o motivo de recusa (`sentenca_excede_capacidade`).

1. Para cada sentenca, se `len(sentenca) > capability.max_message_length` -> retornar `"sentenca_excede_capacidade"` imediatamente.
2. Agrupar sentencas em blocos: comecar um novo bloco quando adicionar a proxima sentenca (mais um separador) excederia `max_message_length`.
3. Retornar `DeliveryPlan(blocks=[...])`.

## `entregar(channel: Channel, registry: IdentityRegistry, channel_id: str, raw_sender_id: str, sentences: list[str]) -> DeliveryOutcome`

1. `ref = resolver_identidade(registry, channel_id, raw_sender_id)`.
2. `plan = planejar_entrega(channel.capability, sentences)`. Se for uma string de recusa -> `DeliveryOutcome(success=False, reason_code=plan, blocks_sent=0)`.
3. Se `len(plan.blocks) > 1` e `not channel.capability.supports_multiple_messages` -> `DeliveryOutcome(success=False, reason_code="canal_nao_suporta_multiplas_mensagens", blocks_sent=0)`.
4. Para cada bloco, na ordem: chamar `channel.send(ref, " ".join(bloco))`. Se levantar excecao -> parar e retornar `DeliveryOutcome(success=False, reason_code="falha_no_envio", blocks_sent=<blocos ja enviados>)`.
5. Se todos os blocos forem enviados -> `DeliveryOutcome(success=True, reason_code=None, blocks_sent=len(plan.blocks))`.
