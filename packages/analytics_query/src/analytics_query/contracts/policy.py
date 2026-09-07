"""The governed query policy — T024 (FR-070, FR-072; SC-027).

Five limits, **jointly required**. A policy carrying cost limits but no privacy
floor does not resolve — it is not partially usable. That is what makes `D-14`
and `D-16` a single failure mode in code rather than in prose, and it removes any
configuration in which the system runs with spending controls but no minimum
aggregation.

The threshold is never derived, defaulted or inferred (`FR-072`). Its absence is
a refusal, not a fallback: inventing a privacy floor would be this feature making
a legal judgement on the data owner's behalf.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, StrictInt, model_validator

from ._base import ContractViolation, QueryModel
from .reason_codes import AnalyticsReasonCode

__all__ = ["PolicyApproval", "QueryPolicy"]


class PolicyApproval(QueryModel):
    """Who approved a policy. A role, never an individual.

    Naming a person would orphan the approval path the moment they leave, which
    is the same rule `001` applies to every approver.
    """

    approver_role: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    approved_on: date


class QueryPolicy(QueryModel):
    """Versioned governed limits. All five are required.

    ``StrictInt`` throughout: a limit silently coerced from a float or a string
    is a limit nobody chose, and these bound money and privacy.
    """

    version: str = Field(min_length=1)
    effective_from: date
    effective_to: date | None = None

    maximum_bytes_billed: StrictInt = Field(gt=0)  # D-14
    maximum_rows: StrictInt = Field(gt=0)  # D-14
    execution_timeout_seconds: StrictInt = Field(gt=0)  # D-14
    maximum_range_days: StrictInt = Field(gt=0)  # D-14
    # D-16: ge=0 desde 2026-09-02 (S-33/OD-97) — o dono aprovou limiar ZERO explicito
    # ("o dado e interno: so os tres declarados veem numeros, agregados sem nome de
    # cliente"); zero e VALOR APROVADO, nao ausencia, e um tipo que o proibe torna a
    # instancia conjunta do d_14 inconstrutivel. Negativo segue recusado: a fronteira morde.
    minimum_aggregation_threshold: StrictInt = Field(ge=0)

    approval: PolicyApproval

    @model_validator(mode="after")
    def _effective_window_is_ordered(self) -> QueryPolicy:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ContractViolation(
                AnalyticsReasonCode.QUERY_POLICY_UNRESOLVABLE,
                "the policy's effective window ends before it begins",
            )
        return self

    def is_effective_on(self, moment: date) -> bool:
        """Whether this policy governs ``moment``. Bounds are inclusive."""
        if moment < self.effective_from:
            return False
        return self.effective_to is None or moment <= self.effective_to
