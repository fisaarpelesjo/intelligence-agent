from datetime import date

from catalogo_semantico import AuditEvent, Catalogo, decidir


def test_metrica_e_dimensao_aprovadas_retorna_permitido_com_definicao(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo,
        metric_id="signups",
        dimension_id="country",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        audit_sink=eventos,
    )

    assert decisao.allowed is True
    assert decisao.reason_code is None
    assert decisao.resolved_metric_version is not None
    assert decisao.resolved_metric_version.label == "Novos cadastros (v1)"


def test_decisao_sem_dimensao_e_permitida_quando_metrica_e_periodo_validos(
    catalogo: Catalogo,
) -> None:
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo,
        metric_id="signups",
        dimension_id=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        audit_sink=eventos,
    )

    assert decisao.allowed is True
