from __future__ import annotations

from .modelos import ChannelCapability, RegistryRef


class FakeChannel:
    """Canal de teste: colecionar o que foi enviado, sem nenhuma integracao real."""

    def __init__(self, capability: ChannelCapability, fail_after: int | None = None) -> None:
        self.capability = capability
        self.sent: list[tuple[RegistryRef, str]] = []
        self._fail_after = fail_after

    def send(self, registry_ref: RegistryRef, text: str) -> None:
        if self._fail_after is not None and len(self.sent) >= self._fail_after:
            raise RuntimeError("falha de envio simulada")
        self.sent.append((registry_ref, text))
