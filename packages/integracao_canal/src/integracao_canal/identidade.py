from __future__ import annotations

from .modelos import IdentityRegistry, RegistryRef


class FakeIdentityRegistry:
    """Registro de identidade em memoria: atribui um RegistryRef opaco e estavel
    por par (channel_id, raw_sender_id), nunca reutilizando o identificador bruto.
    """

    def __init__(self) -> None:
        self._refs: dict[tuple[str, str], RegistryRef] = {}
        self._next_id = 1

    def resolve(self, channel_id: str, raw_sender_id: str) -> RegistryRef:
        key = (channel_id, raw_sender_id)
        if key not in self._refs:
            self._refs[key] = f"registry-ref-{self._next_id}"
            self._next_id += 1
        return self._refs[key]


def resolver_identidade(
    registry: IdentityRegistry, channel_id: str, raw_sender_id: str
) -> RegistryRef:
    return registry.resolve(channel_id, raw_sender_id)
