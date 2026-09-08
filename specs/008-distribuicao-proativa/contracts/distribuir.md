# Contrato: funcao de distribuicao

## `distribuir(insight, gate_config, raw_sender_id, channel, registry) -> DistributionOutcome`

**Entradas**:
- `insight`: `PrioritizedInsight | None` (de `priorizacao_insights`). `None` significa "nao priorizavel".
- `gate_config`: `ChannelGateConfig`.
- `raw_sender_id`: texto (identificador bruto do destinatario no canal).
- `channel`, `registry`: portas de `integracao_canal`.

**Ordem das checagens** (curto-circuito):

1. Se `insight is None` -> `DistributionOutcome(originated=False, reason_code="finding_nao_priorizavel", delivery_outcome=None)`.
2. Se `not gate_config.enabled` -> `reason_code="canal_desabilitado"`.
3. Se `raw_sender_id not in gate_config.allowed_raw_sender_ids` -> `reason_code="destinatario_nao_autorizado"`.
4. Montar as sentencas rotuladas (per `data-model.md`).
5. Chamar `integracao_canal.entregar(channel, registry, gate_config.channel_id, raw_sender_id, sentences)`.
6. Retornar `DistributionOutcome(originated=delivery.success, reason_code=delivery.reason_code, delivery_outcome=delivery)`.

`entregar()` e chamado no maximo uma vez, e somente se os passos 1-3 passarem.
