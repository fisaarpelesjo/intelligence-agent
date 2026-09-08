from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

RegistryRef = str


@dataclass(frozen=True)
class ChannelCapability:
    channel_id: str
    max_message_length: int
    supports_multiple_messages: bool


@dataclass(frozen=True)
class DeliveryPlan:
    blocks: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DeliveryOutcome:
    success: bool
    reason_code: str | None
    blocks_sent: int


class IdentityRegistry(Protocol):
    def resolve(self, channel_id: str, raw_sender_id: str) -> RegistryRef: ...


class Channel(Protocol):
    capability: ChannelCapability

    def send(self, registry_ref: RegistryRef, text: str) -> None: ...
