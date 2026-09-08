import dataclasses

from distribuicao_proativa import distribuir


def test_insight_ausente_e_recusado(gate_habilitado, channel, registry) -> None:
    resultado = distribuir(None, gate_habilitado, "12345", channel, registry)

    assert resultado.originated is False
    assert resultado.reason_code == "finding_nao_priorizavel"
    assert channel.sent == []


def test_canal_desabilitado_e_recusado(
    insight_priorizavel, gate_habilitado, channel, registry
) -> None:
    gate_desabilitado = dataclasses.replace(gate_habilitado, enabled=False)

    resultado = distribuir(insight_priorizavel, gate_desabilitado, "12345", channel, registry)

    assert resultado.originated is False
    assert resultado.reason_code == "canal_desabilitado"
    assert channel.sent == []


def test_destinatario_fora_da_allow_list_e_recusado(
    insight_priorizavel, gate_habilitado, channel, registry
) -> None:
    resultado = distribuir(insight_priorizavel, gate_habilitado, "outro-id", channel, registry)

    assert resultado.originated is False
    assert resultado.reason_code == "destinatario_nao_autorizado"
    assert channel.sent == []
