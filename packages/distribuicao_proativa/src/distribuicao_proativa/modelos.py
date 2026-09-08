from __future__ import annotations

from dataclasses import dataclass

from integracao_canal import DeliveryOutcome


@dataclass(frozen=True)
class ChannelGateConfig:
    channel_id: str
    enabled: bool
    allowed_raw_sender_ids: frozenset[str]


@dataclass(frozen=True)
class DistributionOutcome:
    originated: bool
    reason_code: str | None
    delivery_outcome: DeliveryOutcome | None
