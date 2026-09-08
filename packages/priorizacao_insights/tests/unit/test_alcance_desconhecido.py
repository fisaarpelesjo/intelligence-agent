from priorizacao_insights import InsightCandidate, priorizar


def test_alcance_none_com_confianca_presente_nao_e_priorizado() -> None:
    candidato = InsightCandidate(identifier="x", magnitude=100, confidence=0.9, reach=None)

    resultado = priorizar([candidato])

    assert resultado.prioritized == ()
    assert resultado.not_prioritisable[0].reason_code == "reach_unknown"


def test_confianca_e_alcance_ambos_none_reporta_confidence_unknown() -> None:
    candidato = InsightCandidate(identifier="x", magnitude=100, confidence=None, reach=None)

    resultado = priorizar([candidato])

    assert resultado.not_prioritisable[0].reason_code == "confidence_unknown"
