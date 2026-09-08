from priorizacao_insights import InsightCandidate, priorizar


def test_confianca_none_nao_e_priorizado() -> None:
    desconhecido = InsightCandidate(identifier="x", magnitude=100, confidence=None, reach=10)
    conhecido = InsightCandidate(identifier="y", magnitude=10, confidence=0.5, reach=5)

    resultado = priorizar([desconhecido, conhecido])

    assert len(resultado.prioritized) == 1
    assert resultado.prioritized[0].candidate.identifier == "y"
    assert len(resultado.not_prioritisable) == 1
    assert resultado.not_prioritisable[0].candidate.identifier == "x"
    assert resultado.not_prioritisable[0].reason_code == "confidence_unknown"
