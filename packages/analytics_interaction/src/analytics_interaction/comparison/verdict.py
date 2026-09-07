"""The comparison verdict — T100 (FR-012, FR-065; SC-036).

**One evaluation, over the comparison as presented, before anything executes.**

`001`'s ``evaluate()`` accepts a ``comparison`` on the request. That field is the
whole point: the comparability gate looks at both ranges together and answers a
question neither side can answer alone — *are these two periods comparable for
these metrics?* Metric definitions change, sources start and stop covering days,
grains differ across a version boundary. A verdict on July and a verdict on June
each say the period is fine; only the comparison request asks whether July may be
held against June.

**Two single-side evaluations are not a verdict** (`FR-065`, `SC-036`). Combining
them is the failure this module exists to prevent, and it is prevented
structurally: this function calls ``evaluate`` exactly once, on a request that
carries ``comparison``, and there is no code path that assembles a verdict from
anything else. `T102` counts the calls.

**Before execution, always.** Nothing here touches the execution port, and the
port is not a parameter — the verdict cannot execute a side to decide whether the
comparison is permitted. Ordering is a property of the call graph rather than a
rule somebody follows: `T101` gates on this verdict, and only a permitted verdict
reaches `T098`/`T099`'s submission.

**Nothing is decided here.** The outcome, the reason code, the pt-BR message, the
limitations and the comparable window all come back from `001`. This module
builds one request and passes one decision through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    Comparison,
    DateRange,
)

from ..contracts._base import ContractViolation
from ..contracts.comparison import ComparisonIntent, ComparisonRoute
from ..contracts.reason_codes import InterpretationReasonCode
from ..identity.authorization_fingerprint import derive_authorization_fingerprint

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date

    from semantic_catalog.contracts.access_tag import PrincipalType
    from semantic_catalog.freshness.external import FreshnessSnapshot
    from semantic_catalog.loader.bundle import Bundle

    from ..authorization.context_preflight import AuthorizedContext
    from ..contracts.intake import PrincipalContext
    from ..contracts.intent import ResolvedIntent

__all__ = [
    "CatalogEvaluation",
    "comparison_verdict",
]


class CatalogEvaluation(Protocol):
    """`001`'s ``evaluate``, as this feature needs to name it.

    A Protocol rather than a direct import of ``semantic_catalog.validation``'s
    function, so a test can supply a counting stand-in and prove the call happens
    **once**. It is deliberately shaped as `001`'s own signature: a narrower one
    would let this feature decide which arguments the catalog gets to see, and
    dropping ``snapshot`` or ``on`` is exactly how a gate stops gating.
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


def comparison_verdict(
    intent: ResolvedIntent,
    comparison: ComparisonIntent,
    *,
    authorized: AuthorizedContext,
    auth_fingerprint: str,
    evaluate: CatalogEvaluation,
    bundle: Bundle,
    on: date,
    snapshot: FreshnessSnapshot | None = None,
) -> CatalogDecision:
    """Obtain the complete governed verdict for the comparison as presented.

    Returns `001`'s decision whatever it says. **Permission is not decided here**
    — a ``DENY`` comes back as a decision, not an exception, because a caller
    must be able to audit *why* a comparison was refused and an exception thrown
    from inside an evaluation is not auditable. `T101` reads the outcome.

    The fingerprint is checked first. An intent resolved under one authorization
    context and evaluated under another would ask the catalog about a principal
    who never asked the question, and `001`'s authorization gate would answer
    truthfully about the wrong person.
    """
    if auth_fingerprint != derive_authorization_fingerprint(authorized):
        raise ContractViolation(
            InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE,
            "the comparison was resolved under a different authorization context",
        )

    context = authorized.context
    return evaluate(
        _validation_request(intent, comparison, requester_access=context.granted_access_tags),
        bundle,
        principal_type=context.principal_type,
        authorization_scope=_resolved_scope(context),
        on=on,
        snapshot=snapshot,
    )


def _resolved_scope(context: PrincipalContext) -> str:
    """The scope, refusing rather than passing an empty one to the catalog.

    The preflight already rejects an unresolved scope, so this is unreachable
    through the ordered path. It is here because ``AuthorizedContext`` is
    constructible directly, and the failure it guards is silent: `001`'s
    authorization gate compares the scope it is given, and ``""`` or ``None``
    coerced to a string would be a scope that matches nothing — a *denial* that
    reads like a governed one but came from this feature's type slippage.
    """
    if not context.authorization_scope:
        raise ContractViolation(
            InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE,
            "the authorization scope was never resolved",
        )
    return context.authorization_scope


def _validation_request(
    intent: ResolvedIntent,
    comparison: ComparisonIntent,
    *,
    requester_access: frozenset[str],
) -> CatalogValidationRequest:
    """One request, carrying **both** sides.

    The baseline range is expressed as `001`'s ``Comparison``, not as a second
    request — that is the difference between asking the catalog about a
    comparison and asking it twice about two periods.

    A single-request comparison shares one date range and states no baseline;
    ``ComparisonIntent`` already refuses the inconsistent combinations, so this
    function has no case to handle for them.
    """
    if intent.period is None:
        raise ContractViolation(
            InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED,
            "a comparison verdict needs the resolved primary period",
        )

    return CatalogValidationRequest(
        metrics=intent.metrics,
        dimensions=intent.dimensions,
        sources=intent.sources,
        date_range=DateRange(start=intent.period.start, end=intent.period.end),
        comparison=_baseline(comparison),
        requester_access=tuple(sorted(requester_access)),
    )


def _baseline(comparison: ComparisonIntent) -> Comparison | None:
    """The second period, or none for the single-request route.

    ``None`` is not "no comparison" here — a single-request comparison is still a
    comparison; it is one `002` expresses inside one ``AnalyticsQuery``, so the
    catalog sees it as the one request it is. Only the two-execution route has a
    baseline range to state.
    """
    if comparison.route is ComparisonRoute.SINGLE_REQUEST or comparison.baseline_period is None:
        return None
    baseline = comparison.baseline_period
    return Comparison(
        kind=comparison.kind,
        baseline_range=DateRange(start=baseline.start, end=baseline.end),
    )
