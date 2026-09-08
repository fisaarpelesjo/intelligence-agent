from priorizacao_insights import InsightCandidate, priorizar


def test_ordena_por_impact_score_descendente() -> None:
    a = InsightCandidate(identifier="a", magnitude=100, confidence=0.9, reach=10)
    b = InsightCandidate(identifier="b", magnitude=10, confidence=0.9, reach=10)

    resultado = priorizar([b, a])

    assert [p.candidate.identifier for p in resultado.prioritized] == ["a", "b"]
    assert resultado.prioritized[0].rank == 1
    assert resultado.prioritized[1].rank == 2


def test_desempata_por_reach_score_quando_impact_score_empata() -> None:
    a = InsightCandidate(identifier="a", magnitude=10, confidence=1.0, reach=100)
    b = InsightCandidate(identifier="b", magnitude=10, confidence=1.0, reach=10)

    resultado = priorizar([b, a])

    assert [p.candidate.identifier for p in resultado.prioritized] == ["a", "b"]


def test_lista_vazia_retorna_outcome_vazio() -> None:
    resultado = priorizar([])

    assert resultado.prioritized == ()
    assert resultado.not_prioritisable == ()


def test_nenhum_score_unico_e_exposto() -> None:
    import dataclasses

    from priorizacao_insights import PrioritizedInsight

    campos = {f.name for f in dataclasses.fields(PrioritizedInsight)}
    assert "score" not in campos
    assert {"impact_score", "reach_score"}.issubset(campos)
