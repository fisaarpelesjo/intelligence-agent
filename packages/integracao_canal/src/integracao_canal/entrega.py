from __future__ import annotations

from .identidade import resolver_identidade
from .modelos import Channel, ChannelCapability, DeliveryOutcome, DeliveryPlan, IdentityRegistry


def planejar_entrega(capability: ChannelCapability, sentences: list[str]) -> DeliveryPlan | str:
    for sentence in sentences:
        if len(sentence) > capability.max_message_length:
            return "sentenca_excede_capacidade"

    blocks: list[tuple[str, ...]] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        added_len = len(sentence) if not current else current_len + 1 + len(sentence)
        if added_len > capability.max_message_length:
            blocks.append(tuple(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len = added_len
    if current:
        blocks.append(tuple(current))

    return DeliveryPlan(blocks=tuple(blocks))


def entregar(
    channel: Channel,
    registry: IdentityRegistry,
    channel_id: str,
    raw_sender_id: str,
    sentences: list[str],
) -> DeliveryOutcome:
    ref = resolver_identidade(registry, channel_id, raw_sender_id)

    plan_or_reason = planejar_entrega(channel.capability, sentences)
    if isinstance(plan_or_reason, str):
        return DeliveryOutcome(success=False, reason_code=plan_or_reason, blocks_sent=0)
    plan = plan_or_reason

    if len(plan.blocks) > 1 and not channel.capability.supports_multiple_messages:
        return DeliveryOutcome(
            success=False, reason_code="canal_nao_suporta_multiplas_mensagens", blocks_sent=0
        )

    blocks_sent = 0
    for block in plan.blocks:
        try:
            channel.send(ref, " ".join(block))
        except Exception:
            return DeliveryOutcome(
                success=False, reason_code="falha_no_envio", blocks_sent=blocks_sent
            )
        blocks_sent += 1

    return DeliveryOutcome(success=True, reason_code=None, blocks_sent=blocks_sent)
