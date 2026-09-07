"""Shared base for every governed contract in this feature — T004 (FR-002).

Mirrors `001`'s, `002`'s and `003`'s posture deliberately: frozen, closed to
extras, with strictness applied per field rather than globally.

**``extra="forbid"`` is the mechanism, not a style choice.** It is what makes "no
query text", "no caller-asserted tenant", "no transport-asserted authenticity",
"no caller-supplied governed limit" and "no fixture selector" structural
properties rather than validation rules someone has to remember to write. Each is
refused because the field does not exist, not because a validator rejected it
(`FR-002`, `FR-004`, `FR-107`, `contracts/canonical-contracts.md` §3).

``ChannelViolation`` is how a contract refuses. Pydantic's own error says *what*
failed structurally; a governed refusal must also say *which reason code* the
sender is entitled to see, because that code selects the stored pt-BR wording and
is what the audit trail records.

**The refusal code is a parameter of :func:`build`, not a constant.** A malformed
provider payload and an envelope carrying an undeclared field are different
governed conditions with different codes, and mapping both onto one would tell the
audit trail the wrong thing about which boundary refused.
"""

from __future__ import annotations

from typing import Any, NewType

from pydantic import BaseModel, ConfigDict, ValidationError

from .reason_codes import ChannelReasonCode

__all__ = [
    "ChannelModel",
    "ChannelViolation",
    "ConversationRef",
    "CorrelationId",
    "MessageKey",
    "PrincipalRef",
    "TenantId",
    "build",
]

#: Identity and correlation are distinct types rather than bare strings, so a
#: tenant cannot be passed where a principal reference belongs. All four are
#: **pseudonymous or opaque**: none carries a phone number, member id, chat id,
#: handle, display name or email (`FR-077`).
TenantId = NewType("TenantId", str)
PrincipalRef = NewType("PrincipalRef", str)
ConversationRef = NewType("ConversationRef", str)
CorrelationId = NewType("CorrelationId", str)
MessageKey = NewType("MessageKey", str)


class ChannelViolation(ValueError):  # noqa: N818 - a governed refusal, not an error
    """A governed refusal raised while constructing or validating a contract.

    Carries the reason code rather than a message alone. The message is a
    developer-facing detail; the **code** is the governed fact — it selects the
    stored pt-BR wording (never generated here) and is what an audit event
    records.

    ``detail`` is deliberately **not** sender-facing. It may name which envelope
    field was absent or which signature mode failed; that distinction belongs in
    the audit event's ``detail_class`` and never in a response
    (ADR 0018, ADR 0019).
    """

    def __init__(self, code: ChannelReasonCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


class ChannelModel(BaseModel):
    """Base for every contract this feature authors."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        revalidate_instances="always",
        str_strip_whitespace=False,
    )


def build[M: BaseModel](model: type[M], code: ChannelReasonCode, /, **data: Any) -> M:
    """Construct a governed model, surfacing the **reason code** on failure.

    Pydantic wraps a validator's exception inside a ``ValidationError``, so a
    caller would otherwise have to parse a message to learn why a contract
    refused. A governed refusal must be programmatically legible.

    An unknown field arrives as ``extra_forbidden`` rather than a
    ``ChannelViolation`` — Pydantic rejects it before any validator runs — and is
    mapped to ``code``. That is exactly the intended behaviour: ``verified``,
    ``principal``, ``access_tags``, ``max_rows``, ``detected_language``,
    ``fixture`` and ``mode`` are refused as fields that do not exist, not by a
    rule that names them.
    """
    try:
        return model(**data)
    except ValidationError as exc:
        for error in exc.errors():
            original = error.get("ctx", {}).get("error")
            if isinstance(original, ChannelViolation):
                raise original from exc
        raise ChannelViolation(
            code,
            "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()),
        ) from exc
