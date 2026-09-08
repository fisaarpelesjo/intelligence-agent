from distribuicao_proativa import distribuir
from distribuicao_proativa.distribuicao import _campos_rotulados


def test_campos_rotulados_seguem_formato_rotulo_valor(insight_priorizavel) -> None:
    sentencas = _campos_rotulados(insight_priorizavel)

    assert len(sentencas) == 4
    for sentenca in sentencas:
        rotulo, _, valor = sentenca.partition(": ")
        assert rotulo in {"identificador", "rank", "impact_score", "reach_score"}
        assert valor != ""


def test_toda_sentenca_enviada_contem_os_rotulos_esperados(
    insight_priorizavel, gate_habilitado, channel, registry
) -> None:
    resultado = distribuir(insight_priorizavel, gate_habilitado, "12345", channel, registry)

    assert resultado.originated is True
    assert len(channel.sent) == 1
    _, texto_enviado = channel.sent[0]
    for rotulo in ("identificador", "rank", "impact_score", "reach_score"):
        assert f"{rotulo}: " in texto_enviado
