from __future__ import annotations

from datetime import datetime, timedelta

from integracao_canal import RegistryRef

from .modelos import ConversationTurn


class InMemoryConversationMemory:
    """Memoria de turno de conversa em processo, indexada por RegistryRef.

    Nao persiste entre processos — armazenamento real e uma decisao de
    infraestrutura futura, fora de escopo desta versao.
    """

    def __init__(self) -> None:
        self._turns: dict[RegistryRef, list[ConversationTurn]] = {}

    def registrar_turno(self, turn: ConversationTurn) -> None:
        self._turns.setdefault(turn.registry_ref, []).append(turn)

    def turnos_recentes(
        self,
        registry_ref: RegistryRef,
        reference_now: datetime,
        max_age: timedelta,
    ) -> list[ConversationTurn]:
        if max_age <= timedelta(0):
            return []
        return [
            turn
            for turn in self._turns.get(registry_ref, [])
            if reference_now - turn.recorded_at <= max_age
        ]
