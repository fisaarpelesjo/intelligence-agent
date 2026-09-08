from __future__ import annotations

from .modelos import InboundOutcome


def processar_mensagem_inbound(payload: object) -> InboundOutcome:
    """Recusa sempre. Nao aceita nenhuma referencia a memoria de conversa —
    e estruturalmente impossivel que uma mensagem inbound afete a memoria
    nesta versao (PRD FR-009).
    """
    return InboundOutcome(accepted=False, reason_code="inbound_desabilitado")
