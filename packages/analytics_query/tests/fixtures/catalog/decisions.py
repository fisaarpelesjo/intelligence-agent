"""Constructed ``CatalogDecision`` values for pipeline tests.

Test package only. These stand in for `001`'s verdict so the *pipeline's* own
behaviour — ordering, non-disclosure, passthrough — can be asserted without a
loaded bundle.

They are **not** a second gate implementation and must never become one: nothing
here decides anything, it only fixes what the upstream decision *was* so the
code under test has something to react to. The no-gate-duplication scan covers
`src/` precisely so this file cannot quietly grow into governance logic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.validation.decision import (
    CatalogDecision,
    Limitation,
    Subject,
    SubjectKind,
)

__all__ = ["ALLOWED", "DENIED_ACCESS", "decision"]


def decision(
    *,
    outcome: Outcome = Outcome.ALLOW,
    reason_code: ReasonCode = ReasonCode.REQUEST_ALLOWED,
    limitations: tuple[Limitation, ...] = (),
    answerable_subset: tuple[str, ...] = (),
    subject_id: str = "installs",
) -> CatalogDecision:
    """One decision, with only the fields a pipeline test needs to vary."""
    return CatalogDecision(
        decision_id="d-1",
        policy_version="p@1",
        catalog_release_id="r-1",
        evaluated_at=datetime(2026, 8, 12, tzinfo=UTC),
        outcome=outcome,
        reason_code=reason_code,
        message_pt_br="mensagem",
        subject=Subject(kind=SubjectKind.METRIC, id=subject_id),
        evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="r-1"),),
        limitations=limitations,
        answerable_subset=answerable_subset,
    )


#: Gates 1-6 passed and there was nothing for 7-8 to evaluate.
ALLOWED = decision()

#: Gate 3 denied. The one refusal that must cost nothing at all.
DENIED_ACCESS = decision(outcome=Outcome.DENY, reason_code=ReasonCode.ACCESS_DENIED)
