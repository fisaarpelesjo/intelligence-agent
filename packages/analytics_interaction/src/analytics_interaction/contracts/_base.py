"""Shared base for every governed contract in this feature — T020 (FR-002).

Mirrors `001`'s and `002`'s posture deliberately: frozen, closed to extras, with
strictness applied per field rather than globally. A model-wide ``strict=True``
would reject the string form of every enum and date, which is the only form
authored YAML can express; ``StrictInt`` is applied where silent coercion
actually causes harm.

**``extra="forbid"`` is the mechanism, not a style choice.** It is what makes "no
query text", "no caller-asserted access tag", "no caller-supplied governed limit"
and "no fixture selector" structural properties rather than validation rules
someone has to remember to write. Each is refused because the field does not
exist, not because a validator rejected it (`FR-002`,
`contracts/intake-contract.md` §3).

``ContractViolation`` is how a contract refuses. Pydantic's own error says *what*
failed structurally; a governed refusal must also say *which reason code* the
caller is entitled to see, because that code selects the stored pt-BR wording and
is what the audit trail records.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .reason_codes import InterpretationReasonCode

__all__ = ["ContractViolation", "InteractionModel", "LocalizedRef", "build"]


class ContractViolation(ValueError):  # noqa: N818 - a governed refusal, not an error
    """A governed refusal raised while constructing or validating a contract.

    Carries the reason code rather than a message alone. The message is a
    developer-facing detail; the **code** is the governed fact — it selects the
    stored pt-BR wording (never generated here) and is what an audit event
    records.
    """

    def __init__(self, code: InterpretationReasonCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


class InteractionModel(BaseModel):
    """Base for every contract this feature authors."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        revalidate_instances="always",
        str_strip_whitespace=False,
    )


class LocalizedRef(InteractionModel):
    """A pointer into governed content, never a built string.

    Every user-facing message in this feature is one of these: a
    ``(code, language, content_version)`` triple resolved against
    `interpretation_governance/messages/` at assembly time. No string is
    generated, concatenated from user input, paraphrased or translated
    (`FR-039`), which is what makes byte-identity across repeats (`SC-028`) a
    property of the design rather than a discipline somebody maintains.

    Lives in the shared base because two separately-owned contracts need it —
    `AnswerClaim.message` and `CandidateRef.distinguishing` — and putting it in
    either one would make the other import it from a module about something
    else.

    ``arguments`` carries interpolation values, and the registry allowlists which
    field names may appear. A metric value, a filter value, a credential or a
    span of the question can never be interpolated
    (`contracts/governed-content.md` §7).
    """

    code: str = Field(min_length=1)
    language: str = Field(min_length=1)
    content_version: str = Field(min_length=1)
    arguments: tuple[tuple[str, str], ...] = ()


def build[M: BaseModel](model: type[M], /, **data: Any) -> M:
    """Construct a governed model, surfacing the **reason code** on failure.

    Pydantic wraps a validator's exception inside a ``ValidationError``, so a
    caller would otherwise have to parse a message to learn why a contract
    refused. A governed refusal must be programmatically legible: the code
    selects the stored pt-BR wording and is what the audit event records.

    An unknown field arrives as ``extra_forbidden`` rather than a
    ``ContractViolation`` — Pydantic rejects it before any validator runs. That
    is mapped to ``INTAKE_MALFORMED``, which is exactly the intended behaviour:
    ``sql``, ``access_tags``, ``max_rows``, ``fixture`` and ``channel`` are
    refused as unknown fields, not by a rule that names them.
    """
    try:
        return model(**data)
    except ValidationError as exc:
        for error in exc.errors():
            original = error.get("ctx", {}).get("error")
            if isinstance(original, ContractViolation):
                raise original from exc
        raise ContractViolation(
            InterpretationReasonCode.INTAKE_MALFORMED,
            "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()),
        ) from exc
