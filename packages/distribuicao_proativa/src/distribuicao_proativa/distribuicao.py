from __future__ import annotations

from integracao_canal import Channel, IdentityRegistry, entregar
from priorizacao_insights import PrioritizedInsight

from .modelos import ChannelGateConfig, DistributionOutcome


def _campos_rotulados(insight: PrioritizedInsight) -> list[str]:
    return [
        f"identificador: {insight.candidate.identifier}",
        f"rank: {insight.rank}",
        f"impact_score: {insight.impact_score}",
        f"reach_score: {insight.reach_score}",
    ]


def distribuir(
    insight: PrioritizedInsight | None,
    gate_config: ChannelGateConfig,
    raw_sender_id: str,
    channel: Channel,
    registry: IdentityRegistry,
) -> DistributionOutcome:
    if insight is None:
        return DistributionOutcome(
            originated=False, reason_code="finding_nao_priorizavel", delivery_outcome=None
        )
    if not gate_config.enabled:
        return DistributionOutcome(
            originated=False, reason_code="canal_desabilitado", delivery_outcome=None
        )
    if raw_sender_id not in gate_config.allowed_raw_sender_ids:
        return DistributionOutcome(
            originated=False, reason_code="destinatario_nao_autorizado", delivery_outcome=None
        )

    sentences = _campos_rotulados(insight)
    delivery = entregar(channel, registry, gate_config.channel_id, raw_sender_id, sentences)

    return DistributionOutcome(
        originated=delivery.success, reason_code=delivery.reason_code, delivery_outcome=delivery
    )
