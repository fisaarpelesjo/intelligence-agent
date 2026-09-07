"""Who may receive an originated finding — derived from the declared key, never written.

## OD-105 (2026-09-03, ciclo 535) consertou a chave e o plural

Até hoje este módulo lia `TELEGRAM_ALLOWED_CHAT_ID` — a allowlist de QUEM PODE FALAR com o
bot — e devolvia a string inteira como UM destinatário. É byte a byte o defeito de
2026-08-30 que a `008` registrou e consertou (`OD-28`): uma chave não responde duas
perguntas, e a resposta singular devolveu três ids como um. O clique C1 do dono decidiu:
**a MESMA lista declarada do relatório diário**, pela chave que responde a pergunta certa
(*para onde um envio VAI*), no plural que a primeira entrega real já exigiu (`S-24`).

**A lista é DECLARADA, nunca herdada.** Um chat fora da declaração não recebe nada; o
teto do `d_16` (TRÊS declarados, OD-97) segue valendo — um quarto declarado reabre o
limiar zero e é decisão nova, não configuração.

**A mensagem de recusa nomeia a CHAVE e nunca um valor.**
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from ..contracts.reason_codes import DistributionReasonCode

__all__ = ["RECIPIENT_KEY", "NoAcceptedRecipient", "recipients_from"]

#: A chave que responde "para onde um envio VAI" — a mesma do relatório diário (OD-28),
#: escolhida pelo clique C1 do OD-105. O nome é o contrato; o que ela guarda é do dono.
RECIPIENT_KEY = "TELEGRAM_REPORT_CHAT_ID"


class NoAcceptedRecipient(LookupError):  # noqa: N818 - a governed refusal, not an error
    """The declared key yielded no recipient.

    **The message names the KEY and never a value.** A refusal that quoted what it
    found would put a chat id in a log the first time the variable held something
    unexpected, which is the one place a secret leaks without anybody deciding to.
    """

    def __init__(self) -> None:
        self.code = DistributionReasonCode.DISTRIBUTION_RECIPIENT_NOT_ACCEPTED
        super().__init__(
            f"{self.code.value}: {RECIPIENT_KEY} declares no recipient, so there is nobody this "
            "feature is authorized to originate a message to"
        )


def recipients_from(environment: Mapping[str, str]) -> tuple[str, ...]:
    """**Every** declared recipient, in order and without duplicates — or a named refusal.

    O molde é o `recipients_from` da `008` (o consertado de 30/08): vírgula, ponto e
    vírgula ou espaço separam; duplicatas caem; a ordem é a da declaração. Vazio é
    RECUSA nomeada, não uma lista vazia que passaria por "cada destinatário autorizado"
    vacuamente — enviar para ninguém não é enviar.
    """
    found = environment.get(RECIPIENT_KEY, "").strip()
    if not found:
        raise NoAcceptedRecipient
    ordered: list[str] = []
    for part in re.split(r"[,;\s]+", found):
        piece = part.strip()
        if piece and piece not in ordered:
            ordered.append(piece)
    if not ordered:
        raise NoAcceptedRecipient
    return tuple(ordered)
