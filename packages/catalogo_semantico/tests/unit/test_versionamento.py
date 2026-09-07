from datetime import date

from catalogo_semantico import AuditEvent, Catalogo, decidir
from catalogo_semantico.modelos import ReasonCode


def test_periodo_na_versao_antiga_resolve_definicao_antiga(catalogo: Catalogo) -> None:
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
    assert decisao.resolved_metric_version is not None
    assert decisao.resolved_metric_version.label == "Novos cadastros (v1)"


def test_periodo_na_versao_nova_resolve_definicao_nova(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo,
        metric_id="signups",
        dimension_id="plan_type",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        audit_sink=eventos,
    )

    assert decisao.allowed is True
    assert decisao.resolved_metric_version is not None
    assert decisao.resolved_metric_version.label == "Novos cadastros (v2)"


def test_periodo_cruzando_fronteira_de_versao_e_negado(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo,
        metric_id="signups",
        dimension_id=None,
        period_start=date(2026, 6, 15),
        period_end=date(2026, 7, 15),
        audit_sink=eventos,
    )

    assert decisao.allowed is False
    assert decisao.reason_code == ReasonCode.PERIOD_SPANS_VERSION_BOUNDARY


def test_periodo_fora_de_qualquer_versao_e_negado(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo,
        metric_id="signups",
        dimension_id=None,
        period_start=date(2025, 12, 1),
        period_end=date(2025, 12, 31),
        audit_sink=eventos,
    )

    assert decisao.allowed is False
    assert decisao.reason_code == ReasonCode.NO_METRIC_VERSION_FOR_PERIOD


def test_metrica_descontinuada_ainda_resolve_para_periodo_historico(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo,
        metric_id="legacy_metric",
        dimension_id="country",
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        audit_sink=eventos,
    )

    assert decisao.allowed is True
    assert decisao.resolved_metric_version is not None
    assert decisao.resolved_metric_version.label == "Metrica descontinuada"
