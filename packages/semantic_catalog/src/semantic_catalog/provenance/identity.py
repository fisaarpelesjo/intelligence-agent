"""Final decision identity — T073 (FR-066, FR-067; decision-contract §2).

The gate pipeline produces a ``PRE_EVIDENCE`` result: the governance question is
answered, the data question has not been asked. This module asks the data
question and, when it can be answered, promotes the result to ``FINAL``.

``decision_id`` folds **six** inputs, and the last one is why this module exists:

1. the normalised request   4. the policy version
2. the catalog release id   5. the required freshness snapshots
3. the metric version set   6. the required **data revisions**

An identical request against an identical catalog, policy and revision returns an
identical id (SC-021). A restatement produces a new revision, therefore a new id
(FR-067, SC-031) — which is the point: the same question answered from different
data is a different answer, and two answers that cannot be told apart are worse
than two that disagree.

**Nothing here mutates a prior decision.** ``finalise`` returns a *new* decision;
the model is frozen, so it could not do otherwise even by accident.
``supersedes_decision_id`` is a one-directional, additive link — the earlier
decision is never rewritten to point forward at its successor.

**Promotion fails closed.** A permissive outcome is promoted only when every
required source supplied a stable revision. Missing or unstable leaves the
decision ``PRE_EVIDENCE`` with ``limited`` reproducibility and denies autonomous
publication (FR-068). A ``DENY`` may be final with no revisions at all, because
nothing was read.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts.audit_event import EvidenceKind, EvidenceRef
from ..contracts.reason_codes import Outcome
from ..validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    Finality,
    Reproducibility,
    derive_decision_id,
)
from ..validation.disclosure import PROTECTS_SOURCE_METADATA
from .revision import RevisionResolution

__all__ = ["DecisionLedger", "FinalisedDecision", "finalise"]


@dataclass(frozen=True, slots=True)
class FinalisedDecision:
    """A decision after the data question, with why it landed where it did."""

    decision: CatalogDecision
    resolution: RevisionResolution
    superseded: str | None

    @property
    def is_final(self) -> bool:
        return self.decision.finality is Finality.FINAL

    @property
    def permits_autonomous_publication(self) -> bool:
        """FR-068. A limited decision may be read, never auto-published."""
        return self.is_final and self.resolution.permits_autonomous_publication


def finalise(
    decision: CatalogDecision,
    request: CatalogValidationRequest,
    resolution: RevisionResolution,
    *,
    metric_version_ids: tuple[str, ...],
    freshness_snapshot_ids: tuple[str, ...] = (),
    supersedes_decision_id: str | None = None,
) -> FinalisedDecision:
    """Re-derive identity with the revision evidence folded in.

    The returned decision is a new object. The input is untouched, which is what
    makes a superseding decision safe to create beside the one it supersedes.
    """
    reproducible = resolution.is_reproducible
    permissive = decision.outcome is not Outcome.DENY

    # A refusal that protects source metadata carries no revision either: a
    # revision id names the source it belongs to, which is the disclosure the
    # refusal exists to withhold.
    protected = decision.reason_code in PROTECTS_SOURCE_METADATA
    revision_ids = resolution.revision_ids if reproducible and not protected else ()

    if not permissive:
        # Nothing was read, so no revision contributed to the refusal. A denial
        # is final on its governance evidence alone.
        finality = Finality.FINAL
        reproducibility = Reproducibility.FULL if revision_ids else Reproducibility.LIMITED
    elif reproducible:
        finality = Finality.FINAL
        reproducibility = Reproducibility.FULL
    else:
        finality = Finality.PRE_EVIDENCE
        reproducibility = Reproducibility.LIMITED

    decision_id = derive_decision_id(
        request,
        catalog_release_id=decision.catalog_release_id,
        metric_version_ids=metric_version_ids,
        policy_version=decision.policy_version,
        freshness_snapshot_ids=freshness_snapshot_ids,
        data_revision_ids=revision_ids,
    )

    refs = tuple(decision.evidence_refs) + tuple(
        EvidenceRef(kind=EvidenceKind.DATA_REVISION, id=revision_id) for revision_id in revision_ids
    )

    promoted = decision.model_copy(
        update={
            "decision_id": decision_id,
            "data_revisions": revision_ids,
            "reproducibility": reproducibility,
            "finality": finality,
            "evidence_refs": refs,
            "supersedes_decision_id": supersedes_decision_id,
        }
    )
    # Re-validate: model_copy bypasses validators, and the finality rules are the
    # ones that must not be bypassable.
    promoted = CatalogDecision.model_validate(promoted.model_dump(mode="python"))

    return FinalisedDecision(
        decision=promoted,
        resolution=resolution,
        superseded=supersedes_decision_id,
    )


@dataclass(slots=True)
class DecisionLedger:
    """Decisions in the order they were made. Append-only by construction.

    Not a store — an in-memory record used to prove the property that matters:
    creating a superseding decision leaves its predecessor byte-identical. The
    operational archive belongs to the observability feature (D-13).
    """

    _entries: list[CatalogDecision]

    def __init__(self) -> None:
        self._entries = []

    def record(self, decision: CatalogDecision) -> CatalogDecision:
        """Append and return it. Never replaces an existing entry."""
        self._entries.append(decision)
        return decision

    def supersede(self, earlier: CatalogDecision, later: CatalogDecision) -> CatalogDecision:
        """Record ``later`` as superseding ``earlier``, leaving ``earlier`` alone.

        The link is one-directional and additive: ``later`` names its
        predecessor, and the predecessor is never rewritten to name its
        successor (FR-067).
        """
        if earlier not in self._entries:
            raise ValueError("cannot supersede a decision that was never recorded")
        linked = CatalogDecision.model_validate(
            {**later.model_dump(mode="python"), "supersedes_decision_id": earlier.decision_id}
        )
        return self.record(linked)

    @property
    def entries(self) -> tuple[CatalogDecision, ...]:
        return tuple(self._entries)

    def get(self, decision_id: str) -> CatalogDecision | None:
        return next((d for d in self._entries if d.decision_id == decision_id), None)
