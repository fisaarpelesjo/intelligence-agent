from datetime import date
from pathlib import Path

from catalogo_semantico import AuditEvent, Catalogo, carregar_catalogo, decidir
from catalogo_semantico.modelos import ReasonCode

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_metrica_desconhecida_e_sempre_negada(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo,
        metric_id="metrica_que_nao_existe",
        dimension_id=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        audit_sink=eventos,
    )

    assert decisao.allowed is False
    assert decisao.reason_code == ReasonCode.UNKNOWN_METRIC


def test_dimensao_nao_permitida_para_a_metrica_e_negada(catalogo: Catalogo) -> None:
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo,
        metric_id="signups",
        dimension_id="payment_method",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        audit_sink=eventos,
    )

    assert decisao.allowed is False
    assert decisao.reason_code == ReasonCode.DIMENSION_NOT_ALLOWED


def test_catalogo_vazio_nunca_permite_por_omissao() -> None:
    catalogo_vazio = carregar_catalogo(FIXTURE_DIR / "catalogo_vazio")
    eventos: list[AuditEvent] = []

    decisao = decidir(
        catalogo_vazio,
        metric_id="qualquer_metrica",
        dimension_id=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        audit_sink=eventos,
    )

    assert decisao.allowed is False
    assert decisao.reason_code == ReasonCode.UNKNOWN_METRIC
