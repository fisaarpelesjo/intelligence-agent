from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from integracao_canal import RegistryRef


@dataclass(frozen=True)
class ConversationTurn:
    registry_ref: RegistryRef
    metric_id: str
    period_expression: str
    recorded_at: datetime


@dataclass(frozen=True)
class InboundOutcome:
    accepted: bool
    reason_code: str
