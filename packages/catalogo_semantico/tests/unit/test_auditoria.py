from datetime import date

from catalogo_semantico import AuditEvent, Catalogo, decidir
from catalogo_semantico.modelos import ReasonCode


def test_decisao_permitida_emite_evento_de_auditoria(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decidir(
        catalogo,
        metric_id="signups",
        dimension_id="country",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        audit_sink=eventos,
    )

    assert len(eventos) == 1
    assert eventos[0].decision.allowed is True
    assert eventos[0].metric_id == "signups"


def test_decisao_negada_emite_evento_com_motivo(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decidir(
        catalogo,
        metric_id="metrica_desconhecida",
        dimension_id=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        audit_sink=eventos,
    )

    assert len(eventos) == 1
    assert eventos[0].decision.allowed is False
    assert eventos[0].decision.reason_code == ReasonCode.UNKNOWN_METRIC


def test_n_chamadas_emitem_exatamente_n_eventos(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    for _ in range(5):
        decidir(
            catalogo,
            metric_id="signups",
            dimension_id="country",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            audit_sink=eventos,
        )

    assert len(eventos) == 5
