from datetime import UTC, datetime, timedelta

from memoria_conversa import ConversationTurn, InMemoryConversationMemory

AGORA = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def test_turno_registrado_e_recuperado_pela_mesma_identidade() -> None:
    memoria = InMemoryConversationMemory()
    turno = ConversationTurn(
        registry_ref="ref-1",
        metric_id="signups",
        period_expression="mes_passado",
        recorded_at=AGORA,
    )

    memoria.registrar_turno(turno)
    resultado = memoria.turnos_recentes("ref-1", reference_now=AGORA, max_age=timedelta(days=1))

    assert turno in resultado


def test_turnos_sao_isolados_por_identidade() -> None:
    memoria = InMemoryConversationMemory()
    memoria.registrar_turno(
        ConversationTurn(
            registry_ref="ref-1", metric_id="signups", period_expression="hoje", recorded_at=AGORA
        )
    )
    memoria.registrar_turno(
        ConversationTurn(
            registry_ref="ref-2",
            metric_id="active_users",
            period_expression="hoje",
            recorded_at=AGORA,
        )
    )

    resultado = memoria.turnos_recentes("ref-1", reference_now=AGORA, max_age=timedelta(days=1))

    assert len(resultado) == 1
    assert resultado[0].registry_ref == "ref-1"


def test_identidade_sem_turno_retorna_lista_vazia() -> None:
    memoria = InMemoryConversationMemory()

    resultado = memoria.turnos_recentes(
        "ref-desconhecida", reference_now=AGORA, max_age=timedelta(days=1)
    )

    assert resultado == []
