"""The catalog bridge — T068 (FR-003, FR-004, FR-015, FR-016, FR-018, FR-019, FR-020; SC-016).

The single point at which governance enters this feature. Two jobs, and
deliberately no third:

1. **Translate** an ``AnalyticsQuery`` into `001`'s ``CatalogValidationRequest``.
2. **Call** ``evaluate()`` and pass its verdict through unchanged.

Delegation is total, and that is what discharges the inherited blockers:
retention answerability stays `001`'s decision while `D-8`/`D-9` evidence is
absent (`FR-062`), and this feature neither anticipates nor works around it.

No gate is re-implemented here. Existence, lifecycle, authorisation,
combination, grain, comparability, coverage, freshness, period, retention and
as-of resolution are all `001`'s, and this module contains none of that logic
(`FR-015`). It also does not *re-order* them: the gates run in `001`'s order
because `001` runs them.

Translation is mechanical and lossless in the directions that matter. What it
must never do is widen: a dimension the caller did not ask for, or a source the
caller did not name, would change the question the catalog is asked. Required
sources are derived **by `001`**, from the metrics — this feature does not reduce
the source set itself (`FR-019`), because a reduction computed here could quietly
drop the source that would have refused the request (`FR-020`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from semantic_catalog.contracts.reason_codes import Outcome
from semantic_catalog.validation.decision import DateRange as CatalogDateRange
from semantic_catalog.validation.pipeline import CatalogValidationRequest

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date

    from semantic_catalog.contracts.audit_event import PrincipalType
    from semantic_catalog.loader.bundle import Bundle
    from semantic_catalog.validation.decision import CatalogDecision
    from semantic_catalog.validation.pipeline import FreshnessSnapshot

    from ..contracts.request import AnalyticsQuery

__all__ = [
    "PERMISSIVE_OUTCOMES",
    "CatalogEvaluator",
    "evaluate_fully",
    "is_permissive",
    "to_catalog_request",
]

#: The only outcomes under which execution is reachable. Anything else — including
#: an outcome `001` adds later — refuses, because the default is "not permitted"
#: rather than "not recognised, so probably fine" (`FR-016`, `FR-048`).
PERMISSIVE_OUTCOMES: frozenset[Outcome] = frozenset({Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT})


class CatalogEvaluator(Protocol):
    """`001`'s ``evaluate``, at its real signature.

    Declared as a protocol so tests can substitute a decision without a loaded
    bundle — not so production can substitute a *verdict*. There is one
    implementation on the request path, and it is `001`'s.
    """

    def __call__(
        self,
        request: CatalogValidationRequest,
        bundle: Bundle,
        *,
        principal_type: PrincipalType,
        authorization_scope: str,
        on: date,
        snapshot: FreshnessSnapshot | None = None,
    ) -> CatalogDecision: ...


def to_catalog_request(
    request: AnalyticsQuery, *, requester_access: tuple[str, ...]
) -> CatalogValidationRequest:
    """Translate the governed request into the catalog's own request type.

    ``filters`` are deliberately **not** translated. `001` governs which
    metric-dimension-source combinations may be asked; it does not govern which
    *values* are selected, and passing filter values upstream would hand the
    catalog data it has no use for and no contract to protect.

    ``comparison`` and ``aggregate`` are left unset: neither is part of this
    feature's request surface (`BD-1`), so inventing one here would ask the
    catalog a question the caller never asked.
    """
    return CatalogValidationRequest(
        metrics=request.metrics,
        dimensions=request.dimensions,
        sources=request.sources,
        date_range=CatalogDateRange(start=request.date_range.start, end=request.date_range.end),
        requester_access=requester_access,
    )


def evaluate_fully(
    request: AnalyticsQuery,
    *,
    evaluate: CatalogEvaluator,
    bundle: Bundle,
    snapshot: FreshnessSnapshot,
    principal_type: PrincipalType,
    authorization_scope: str,
    requester_access: tuple[str, ...],
    on: date,
) -> CatalogDecision:
    """Run the full evaluation with the self-read snapshot supplied.

    ``snapshot`` is required here, unlike in the preflight where it is
    deliberately ``None``. This is the call that may cost: gates 7 and 8 need
    observations, and by this point the principal has been authorized and the
    observations have been read from the governed tables (`FR-073`).

    The returned decision is passed back **verbatim**. It is not restated,
    summarised, downgraded or re-coded — a refusal keeps `001`'s own reason code
    (`FR-017`, and the passthrough test asserts it).
    """
    return evaluate(
        to_catalog_request(request, requester_access=requester_access),
        bundle,
        principal_type=principal_type,
        authorization_scope=authorization_scope,
        on=on,
        snapshot=snapshot,
    )


def is_permissive(decision: CatalogDecision) -> bool:
    """Whether execution is reachable at all.

    Reads the public ``outcome`` only. Deciding from anything else — a gate
    name, an internal flag, the shape of the payload — would be this feature
    forming its own opinion about a governance verdict.
    """
    return decision.outcome in PERMISSIVE_OUTCOMES
