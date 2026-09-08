from datetime import UTC, datetime, timedelta

from memoria_conversa import ConversationTurn, InMemoryConversationMemory

AGORA = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
DOIS_DIAS_ATRAS = AGORA - timedelta(days=2)


def _memoria_com_turno_antigo() -> InMemoryConversationMemory:
    memoria = InMemoryConversationMemory()
    memoria.registrar_turno(
        ConversationTurn(
            registry_ref="ref-1",
            metric_id="signups",
            period_expression="mes_passado",
            recorded_at=DOIS_DIAS_ATRAS,
        )
    )
    return memoria


def test_turno_fora_da_janela_de_retencao_nao_e_retornado() -> None:
    memoria = _memoria_com_turno_antigo()

    resultado = memoria.turnos_recentes("ref-1", reference_now=AGORA, max_age=timedelta(days=1))

    assert resultado == []


def test_turno_dentro_de_janela_maior_e_retornado() -> None:
    memoria = _memoria_com_turno_antigo()

    resultado = memoria.turnos_recentes("ref-1", reference_now=AGORA, max_age=timedelta(days=3))

    assert len(resultado) == 1


def test_janela_zero_ou_negativa_sempre_retorna_vazio() -> None:
    memoria = InMemoryConversationMemory()
    memoria.registrar_turno(
        ConversationTurn(
            registry_ref="ref-1", metric_id="signups", period_expression="hoje", recorded_at=AGORA
        )
    )

    assert memoria.turnos_recentes("ref-1", AGORA, timedelta(0)) == []
    assert memoria.turnos_recentes("ref-1", AGORA, timedelta(days=-1)) == []
