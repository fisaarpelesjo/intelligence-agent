"""Shared gate types — Phase 6 (decision-contract §4).

Every gate has the same shape: look at the request and the catalog, and either
pass or produce a :class:`GateVerdict` naming a stable reason code **and the
specific subject responsible**. There is no "denied" without an offender, which
is what SC-004 means by no generic refusals.

Gates never construct a :class:`~semantic_catalog.validation.decision.CatalogDecision`.
They return a verdict; the pipeline turns the first denial into a decision. That
split is why a gate cannot accidentally emit a decision missing its policy
version or its evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from ...contracts.access_tag import PrincipalType
from ...contracts.policy import CatalogPolicy
from ...contracts.reason_codes import Outcome, ReasonCode, outcome_for
from ...freshness.external import FreshnessSnapshot
from ...freshness.required import SourceRequirement, required_sources
from ...loader.bundle import Bundle
from ..decision import CatalogValidationRequest, Subject, SubjectKind

__all__ = ["GateContext", "GateVerdict", "caveat", "deny"]


@dataclass(frozen=True, slots=True)
class GateVerdict:
    """A gate finding. Passing cleanly is ``None``, never a verdict.

    A verdict is either a **denial**, which stops the pipeline, or a **caveat**,
    which does not. The outcome class is read from the governed code rather than
    passed in, so a gate cannot classify its own finding — a caveat that decided
    it was a denial, or vice versa, would let one gate override the enum.
    """

    reason_code: ReasonCode
    subject: Subject
    detail: str

    @property
    def outcome(self) -> Outcome:
        return outcome_for(self.reason_code)

    @property
    def is_denial(self) -> bool:
        return self.outcome is Outcome.DENY


def deny(reason_code: ReasonCode, kind: SubjectKind, identifier: str, detail: str) -> GateVerdict:
    """Construct a denial that names its offender. The only way to deny."""
    verdict = GateVerdict(
        reason_code=reason_code,
        subject=Subject(kind=kind, id=identifier),
        detail=detail,
    )
    if not verdict.is_denial:
        raise ValueError(
            f"{reason_code.value} is classified {verdict.outcome.value}; use caveat() instead"
        )
    return verdict


def caveat(reason_code: ReasonCode, kind: SubjectKind, identifier: str, detail: str) -> GateVerdict:
    """Construct a non-blocking caveat. Evaluation continues past it."""
    verdict = GateVerdict(
        reason_code=reason_code,
        subject=Subject(kind=kind, id=identifier),
        detail=detail,
    )
    if verdict.outcome is not Outcome.ALLOW_WITH_CAVEAT:
        raise ValueError(
            f"{reason_code.value} is classified {verdict.outcome.value}; use deny() instead"
        )
    return verdict


@dataclass(frozen=True, slots=True)
class GateContext:
    """Everything a gate may read. Deliberately narrow.

    A gate sees the built bundle rather than a raw catalog, so lifecycle and
    projection decisions already made cannot be re-litigated inside a gate, and
    a gate cannot reach past the public projection into a draft definition.
    """

    request: CatalogValidationRequest
    bundle: Bundle
    policy: CatalogPolicy
    principal_type: PrincipalType
    authorization_scope: str
    on: date

    #: Observed external state, supplied by the caller. ``None`` means the
    #: caller offered no evidence, which the freshness and coverage gates treat
    #: as an unknown state and refuse — never as healthy.
    snapshot: FreshnessSnapshot | None = None

    #: Shared cutoff for an equivalent-partial comparison. Never inferred: a
    #: guessed cutoff manufactures the equivalence the rule exists to check.
    partial_cutoff: time | None = None

    @property
    def requirements(self) -> tuple[SourceRequirement, ...]:
        """Named sources classified as required or not (T066)."""
        return required_sources(
            self.bundle.internal.metrics,
            self.request.metrics,
            self.request.sources,
        )

    @property
    def required_source_ids(self) -> tuple[str, ...]:
        """Only these gate the outcome. A named-but-unused source does not."""
        return tuple(r.source for r in self.requirements if r.required)
