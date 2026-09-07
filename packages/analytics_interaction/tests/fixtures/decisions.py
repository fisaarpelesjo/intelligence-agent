"""Synthetic catalog decisions — Phase 9 test support.

`001` produces these from a real bundle through a real gate pipeline. A Phase 9
test needs a decision with a *chosen outcome* — permitted, caveated, denied — and
running a bundle through the gates to obtain one would make the routing and
verdict suites depend on `001`'s fixture catalog holding exactly the right
comparability rule.

So these are built directly against `001`'s contract. Directly, not loosely:
``CatalogDecision``'s own validators run, which means an outcome that disagrees
with its reason code cannot be built here either. A fixture that could express an
inconsistent decision would let a Phase 9 test pass against a shape `001` never
produces.

TEST-ONLY. Never evidence for any external record, and never a governed decision.
"""

from __future__ import annotations

from datetime import UTC, datetime

from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode, outcome_for
from semantic_catalog.validation.decision import (
    CatalogDecision,
    ComparableWindow,
    Subject,
    SubjectKind,
)

__all__ = ["ALLOWED", "CAVEATED", "DENIED", "decision"]


def decision(
    code: ReasonCode = ReasonCode.REQUEST_ALLOWED,
    *,
    comparable_window: ComparableWindow | None = None,
    outcome: Outcome | None = None,
) -> CatalogDecision:
    """A decision carrying ``code``, with the outcome `001` classifies it as.

    ``outcome`` is an override rather than a parameter with a sensible default,
    and it exists for exactly one test: proving that a decision whose outcome
    disagrees with its code is refused. Passing it anywhere else would be a test
    asserting against a decision the catalog cannot issue.
    """
    return CatalogDecision(
        decision_id="dec-1",
        policy_version="pol-1",
        catalog_release_id="r-1",
        evaluated_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
        outcome=outcome or outcome_for(code),
        reason_code=code,
        message_pt_br="decisão de teste",
        subject=Subject(kind=SubjectKind.REQUEST, id="req-1"),
        evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="r-1"),),
        comparable_window=comparable_window,
    )


#: The three verdicts Phase 9 gates on, named once so the suites agree on them.
ALLOWED = ReasonCode.REQUEST_ALLOWED
CAVEATED = ReasonCode.EQUIVALENT_PARTIAL_COMPARISON
DENIED = ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON
