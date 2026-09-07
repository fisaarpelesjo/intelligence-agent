"""The catalog port — T016 (`FR-001`, `FR-012`).

Asks `001` whether a rule's metric may be read at all, and for the window it
would be read over. **Computes no date**: the window comes from the decision.

**The first product of this port is a refusal, and that is not a failure state.**
Measured in cycle 314 against the production catalog, not against a fixture:

```
build_bundle("semantic") -> 11 metrics, 6 sources
evaluate(active_users, ...) -> DENY / METRIC_PENDING     (both principal types)
```

`semantic/governance/freshness-approvals.yaml` carries `approvals: []`, every
source is therefore unpublishable, and `001`'s existence gate denies
`METRIC_PENDING` for a metric whose lifecycle is `PENDING`. **Eleven of eleven are
pending while `D-1` is open**, so no rule can fire — and the honest thing for this
port to do is say so with the catalog's own word attached.

**The upstream refusal is carried, never restated.** `ANOMALY_RULE_METRIC_NOT_BOUND`
is a *carrier*, not a description: this feature's reason-code module says the
carriers *"travel with the upstream code that produced them, because
re-classifying an upstream refusal into a local vocabulary is how the original
reason stops being readable"*. So `METRIC_PENDING` travels verbatim in
``upstream_code``, and a reader of the run sees **which layer refused and in which
words**.

**And the carrier's name is imperfect, which is worth stating rather than hiding.**
`NOT_BOUND` reads as *"there is no binding"*, and the metric **has** a binding —
what it lacks is **publication**. What keeps that from being a lie is precisely the
carried code: ours says *"it did not resolve through `001`"* and the catalog's says
**why**. A test below asserts the carried code is present on every refusal, because
without it the word would be asserting more than it measured.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

from analytics_query.contracts.comparable_window import ComparableWindow, window_from_decision
from pydantic import Field
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.metric import AvailabilityStatus
from semantic_catalog.contracts.reason_codes import Outcome
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    Comparison,
    DateRange,
)

from ..contracts import AnomalyModel, AnomalyReasonCode, GovernedName

if TYPE_CHECKING:  # pragma: no cover - typing only
    from semantic_catalog.freshness.external import FreshnessSnapshot
    from semantic_catalog.loader.bundle import Bundle

__all__ = ["CatalogEvaluator", "MetricResolution", "resolve_metric"]


class CatalogEvaluator(Protocol):
    """`001`'s pipeline, as this feature consumes it.

    A protocol rather than a direct import at the call site, so a test can supply
    a governed decision without building a bundle — **and so this module never
    reaches for a catalog it was not handed.**
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


class MetricResolution(AnomalyModel):
    """What the catalog said about one rule's metric.

    **Permitted or refused, never partially either.** A resolution that permits
    carries the window; one that refuses carries our code **and** the catalog's.
    """

    rule_id: GovernedName
    permitted: bool
    window: ComparableWindow | None = Field(
        default=None, description="From the decision. This feature computes no date (FR-012)."
    )
    reason_code: AnomalyReasonCode | None = Field(
        default=None, description="Ours. Present exactly when permitted is False."
    )
    upstream_code: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "The catalog's own reason, verbatim. Present on every refusal: without it "
            "our carrier would be asserting more than it measured."
        ),
    )
    decision_id: str | None = Field(
        default=None, description="So a run can be traced back to the governed decision."
    )

    def _refusal_is_complete(self) -> bool:
        return self.reason_code is not None and self.upstream_code is not None

    @property
    def is_traceable(self) -> bool:
        """Whether this resolution can be audited back to `001`."""
        return self.decision_id is not None


def _answered_from(bundle: Bundle, metric: str) -> tuple[str, ...]:
    """The sources the CATALOG says this metric is answered from.

    **Read, never guessed, and never taken from the rule.** `001` classifies a source
    as *required* only when a requested metric declares it AVAILABLE, and a request
    that names no source has no required source — so gate 7 has nothing to cover,
    states no comparable window, and the resolution below refuses with
    `ANOMALY_RULE_PERIOD_NOT_GOVERNED` for a reason that is about the REQUEST rather
    than about the catalog.

    Deriving the list here keeps the rule out of it: an anomaly rule binds a metric,
    and where that metric may be answered from is the catalog's decision. A rule that
    named its own source could ask for a window over a source the metric does not
    declare.

    An unknown metric answers an empty tuple, which is what it was before this
    existed: the pipeline refuses the metric itself, and inventing a source here would
    turn that refusal into a different one.
    """
    declared = bundle.internal.metrics.get(metric)
    if declared is None:
        return ()
    return tuple(
        sorted(
            {
                entry.source
                for entry in declared.source_availability
                if entry.status is AvailabilityStatus.AVAILABLE
            }
        )
    )


def resolve_metric(
    rule_id: str,
    metric: str,
    *,
    evaluate: CatalogEvaluator,
    bundle: Bundle,
    start: date,
    end: date,
    baseline_start: date,
    baseline_end: date,
    comparison_kind: str,
    principal_type: PrincipalType,
    authorization_scope: str,
    requester_access: tuple[str, ...],
    on: date,
    snapshot: FreshnessSnapshot | None = None,
) -> MetricResolution:
    """Ask the catalog whether this metric may be read, and over which window.

    **Every outcome that is not `ALLOW` refuses**, and `ALLOW_WITH_CAVEAT` is
    included in that — a caveat is a governed condition on an *answer*, and this
    feature emits no answer. Treating it as permission would silently drop the
    caveat, which is the one thing `003` exists to carry.

    **The request declares a comparison**, and that is measured rather than
    stylistic: `window_from_decision` returns `None` for a single-range request
    because *"a single-source request has no comparison to qualify"* — and `None`
    is deliberately not an empty window there. Detection always compares a period
    against a baseline, so asking without declaring the comparison would get a
    legitimate `None` back and then treat it as a defect.

    Given a comparison was declared, a missing window **is** a defect: `FR-012`
    says windows come from the catalog, and a detector that picks its own window
    compares periods nobody governed.
    """
    request = CatalogValidationRequest(
        metrics=(metric,),
        sources=_answered_from(bundle, metric),
        date_range=DateRange(start=start, end=end),
        comparison=Comparison(
            kind=comparison_kind,
            baseline_range=DateRange(start=baseline_start, end=baseline_end),
        ),
        requester_access=requester_access,
    )
    decision = evaluate(
        request,
        bundle,
        principal_type=principal_type,
        authorization_scope=authorization_scope,
        on=on,
        snapshot=snapshot,
    )

    if decision.outcome is not Outcome.ALLOW:
        return MetricResolution(
            rule_id=rule_id,
            permitted=False,
            reason_code=AnomalyReasonCode.ANOMALY_RULE_METRIC_NOT_BOUND,
            upstream_code=decision.reason_code.value,
            decision_id=decision.decision_id,
        )

    window = window_from_decision(decision)
    if window is None:
        return MetricResolution(
            rule_id=rule_id,
            permitted=False,
            reason_code=AnomalyReasonCode.ANOMALY_RULE_PERIOD_NOT_GOVERNED,
            upstream_code=decision.reason_code.value,
            decision_id=decision.decision_id,
        )

    return MetricResolution(
        rule_id=rule_id,
        permitted=True,
        window=window,
        decision_id=decision.decision_id,
    )
