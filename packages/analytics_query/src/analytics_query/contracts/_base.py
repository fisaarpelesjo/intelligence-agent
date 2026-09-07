"""Shared base for every governed contract in this feature.

Mirrors `001`'s posture deliberately: frozen, closed to extras, with strictness
applied per field rather than globally. A model-wide ``strict=True`` would reject
the string form of every enum and date, which is the only form authored YAML can
express; ``StrictInt`` and ``StrictBool`` are applied where silent coercion
actually causes harm.

``ContractViolation`` is how a contract refuses. Pydantic's own error says *what*
failed structurally; a governed refusal must also say *which reason code* the
caller is entitled to see, because that code selects the stored pt-BR wording and
is what the audit trail records.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from .reason_codes import AnalyticsReasonCode

__all__ = ["ContractViolation", "QueryModel", "build"]


class ContractViolation(ValueError):  # noqa: N818 - a governed refusal, not an error
    """A governed refusal raised while constructing or validating a contract.

    Carries the reason code rather than a message alone. The message is a
    developer-facing detail; the **code** is the governed fact — it selects the
    stored pt-BR wording (never generated here) and is what an audit event
    records.
    """

    def __init__(self, code: AnalyticsReasonCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


class QueryModel(BaseModel):
    """Base for every contract this feature authors.

    ``extra="forbid"`` is load-bearing, not stylistic: it is what makes "no query
    text", "no caller-supplied observation" and the `BD-1` rejection of
    ``comparison``/``order_by``/``limit`` structural properties rather than
    validation rules someone must remember to write.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        revalidate_instances="always",
        str_strip_whitespace=False,
    )


def build[M: BaseModel](model: type[M], /, **data: Any) -> M:
    """Construct a governed model, surfacing the **reason code** on failure.

    Pydantic wraps a validator's exception inside a ``ValidationError``, so a
    caller would otherwise have to parse a message to learn why a request was
    refused. A governed refusal must be programmatically legible: the code
    selects the stored pt-BR wording and is what the audit event records.

    An unknown field arrives as ``extra_forbidden`` rather than a
    ``ContractViolation`` — Pydantic rejects it before any validator runs. That
    is mapped to ``REQUEST_MALFORMED``, which is exactly the `BD-1` behaviour:
    ``comparison``, ``order_by`` and ``limit`` are refused as unknown fields.
    """
    try:
        return model(**data)
    except ValidationError as exc:
        for error in exc.errors():
            original = error.get("ctx", {}).get("error")
            if isinstance(original, ContractViolation):
                raise original from exc
        raise ContractViolation(
            AnalyticsReasonCode.REQUEST_MALFORMED,
            "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()),
        ) from exc
