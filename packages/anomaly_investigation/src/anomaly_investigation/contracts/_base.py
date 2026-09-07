"""Shared base for every governed contract in this feature.

Mirrors `002`'s and `004`'s posture deliberately: frozen, closed to extras, with
strictness applied per field rather than globally.

``AnomalyContractViolation`` is how a contract refuses. Pydantic's own error says
*what* failed structurally; a governed refusal must also say **which reason code**,
because the code is what a run records in its withholdings and what an operator
reads.

**One upstream element this feature needed is private, and it was not taken.**
`001`'s ``Identifier`` lives in ``semantic_catalog.contracts._base``. Standing
constraint 2 of ``tasks.md`` says: if a required upstream element is private, stop
and record it — no alias, wrapper, re-export, subclass, ``getattr``, monkeypatch or
copy. So ``GovernedName`` below is this feature's own bounded string, and it makes
**no claim** to be `001`'s identifier grammar: a name that must resolve in the
catalog is resolved **by** the catalog through the ports, never validated here
against a copied pattern.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .reason_codes import AnomalyReasonCode

__all__ = [
    "AnomalyContractViolation",
    "AnomalyModel",
    "GovernedName",
    "build",
]


class AnomalyContractViolation(ValueError):  # noqa: N818 - a governed refusal, not an error
    """A governed refusal raised while constructing or validating a contract.

    Carries the reason code rather than a message alone. The message is a
    developer-facing detail; the **code** is the governed fact.
    """

    def __init__(self, code: AnomalyReasonCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


#: A non-empty name this feature carries but does not interpret — a metric, a
#: dimension, a period. **Length-bounded and nothing more.** Validating its
#: *grammar* here would be re-implementing a catalog gate, which `FR-008` forbids
#: and which would drift the moment `001`'s grammar changed.
GovernedName = Annotated[str, Field(min_length=1, max_length=200)]


class AnomalyModel(BaseModel):
    """Base for every contract this feature authors.

    ``extra="forbid"`` is load-bearing rather than stylistic: it is what makes
    "no score", "no severity" and "no narrative" **structural properties** of a
    candidate rather than review rules someone must remember to apply. `FR-013`
    is enforced by the shape before any test runs.

    ``frozen=True`` matters for a second reason here: a candidate is evidence.
    Evidence that can be edited after the fact is not evidence.
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
    caller would otherwise have to parse a message to learn why a construction
    was refused.

    A missing required field or an unknown one arrives as a Pydantic error rather
    than a ``AnomalyContractViolation`` — it is rejected before any validator
    runs. Both are mapped to ``ANOMALY_FIGURE_UNAVAILABLE`` only when they concern
    evidence; anything else re-raises the original, because inventing a code for a
    structural mistake would put a governed word on a programming error.
    """
    try:
        return model(**data)
    except ValidationError as exc:
        for error in exc.errors():
            original = error.get("ctx", {}).get("error")
            if isinstance(original, AnomalyContractViolation):
                raise original from exc
        raise
