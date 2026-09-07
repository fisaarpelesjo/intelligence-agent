import socket
from datetime import date

import pytest
from catalogo_semantico import AuditEvent, Catalogo, decidir


def test_decidir_nao_abre_nenhum_socket_de_rede(
    catalogo: Catalogo, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _falhar_se_chamado(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("decidir() nao deve abrir conexao de rede (SC-004)")

    monkeypatch.setattr(socket.socket, "connect", _falhar_se_chamado)

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
