from distribuicao_proativa import distribuir


def test_origina_mensagem_quando_as_3_condicoes_passam(
    insight_priorizavel, gate_habilitado, channel, registry
) -> None:
    resultado = distribuir(insight_priorizavel, gate_habilitado, "12345", channel, registry)

    assert resultado.originated is True
    assert resultado.delivery_outcome is not None
    assert resultado.delivery_outcome.success is True
    assert len(channel.sent) == 1
