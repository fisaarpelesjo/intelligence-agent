"""Data-revision resolution and finalisation — T093 (FR-043; SC-005).

Calls `001`'s ``resolve_revisions()`` and then ``finalise()``. **No finality
logic is written here** — this module has no rule about when a decision becomes
`FINAL`, no threshold, and no opinion about what counts as a stable revision.

That restraint is the requirement. `001` owns the seam: it decides that a
decision is `PRE_EVIDENCE` until a data revision arrives, and that
``reproducibility: full`` requires at least one stable revision. If this feature
re-derived either, two components would answer the same question and they would
drift — and the drift would be invisible, because both would look authoritative.

What this feature contributes is the **evidence**: the revisions it observed
while reading the governed tables for this request. Supplying evidence and
deciding what it means are different jobs, and only the first belongs here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from semantic_catalog.provenance.identity import finalise
from semantic_catalog.provenance.revision import resolve_revisions

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date

    from semantic_catalog.provenance.identity import FinalisedDecision
    from semantic_catalog.provenance.revision import RevisionSnapshot
    from semantic_catalog.validation.decision import CatalogDecision
    from semantic_catalog.validation.pipeline import CatalogValidationRequest

__all__ = ["finalise_decision"]


def finalise_decision(
    decision: CatalogDecision,
    request: CatalogValidationRequest,
    *,
    required_sources: tuple[str, ...],
    snapshot: RevisionSnapshot | None,
    metric_version_ids: tuple[str, ...],
    freshness_snapshot_ids: tuple[str, ...] = (),
    period_start: date,
    period_end: date,
) -> FinalisedDecision:
    """Advance a `PRE_EVIDENCE` decision using the revisions this request read.

    ``snapshot`` may be ``None`` — a source that cannot supply a stable revision
    is a real state, and `001` renders it as ``reproducibility: limited`` with
    ``REPRODUCIBILITY_LIMITED``. It is deliberately **not** defaulted to an
    empty snapshot here: an empty snapshot would assert "no revisions exist",
    which is a claim, where ``None`` correctly says "none were established".
    """
    resolution = resolve_revisions(
        required_sources,
        snapshot,
        period_start=period_start,
        period_end=period_end,
    )
    return finalise(
        decision,
        request,
        resolution,
        metric_version_ids=metric_version_ids,
        freshness_snapshot_ids=freshness_snapshot_ids,
    )
