"""Allowed-combination matrix — T057 (FR-013; library contract §1.3).

Consumers must be able to **discover** the answerable surface instead of finding
it by trial and error. A consumer that probes the gates to learn what is allowed
generates a stream of denials that look like an incident, and learns the shape of
metrics it may not be authorised to see along the way.

So the matrix is computed the same way a request is: by running the pipeline. It
is not a second, parallel implementation of the rules, because a second
implementation is a second set of rules that will disagree with the first at the
worst possible moment.

**Access-filtered.** The matrix a requester receives contains only combinations
that requester could actually ask for. An unauthorised metric is absent, not
listed-and-refused — listing it would disclose that it exists.

Today every metric is pending (D-1, D-8 open), so the matrix is legitimately
**empty**. An empty answerable surface is the correct report of a catalog whose
business inputs are unapproved, not a failure of this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ..contracts.access_tag import PrincipalType
from ..contracts.metric import AvailabilityStatus
from ..contracts.reason_codes import Outcome
from ..freshness.external import FreshnessSnapshot
from ..loader.bundle import Bundle
from .decision import CatalogValidationRequest, DateRange
from .pipeline import evaluate

__all__ = ["CombinationMatrix", "CombinationRow", "allowed_combinations"]


@dataclass(frozen=True, slots=True)
class CombinationRow:
    """One answerable combination, with the contract the analysis must honour.

    The aggregation, grain, unit and time dimension travel with the row because
    US2 scenario 4 requires an approval to state them — an "allowed" that does
    not say how to compute the number leaves the caller to guess.
    """

    metric_id: str
    source_id: str
    dimension_id: str | None
    aggregation: str
    grain: str
    unit: str
    time_dimension: str
    additivity: str


@dataclass(frozen=True, slots=True)
class CombinationMatrix:
    """The full answerable surface for one requester."""

    rows: tuple[CombinationRow, ...]
    evaluated_on: date

    @property
    def metric_ids(self) -> tuple[str, ...]:
        return tuple(sorted({row.metric_id for row in self.rows}))

    def is_empty(self) -> bool:
        return not self.rows


def allowed_combinations(
    bundle: Bundle,
    *,
    access: Sequence[str],
    principal_type: PrincipalType,
    authorization_scope: str,
    on: date,
    snapshot: FreshnessSnapshot | None = None,
    probe_range: DateRange | None = None,
) -> CombinationMatrix:
    """Enumerate what this requester may ask, by asking the pipeline.

    Candidate triples come from the authored contracts — a metric's available
    sources and its ``allowed_dimensions`` — and each is then put through the
    real gates. The enumeration proposes; the pipeline disposes.

    ``snapshot`` is the caller's observed external state. Without one the
    freshness and coverage gates refuse everything, so the matrix is empty —
    which is the correct report of a catalog nobody has supplied evidence for.
    """
    window = probe_range or DateRange(start=on, end=on)
    rows: list[CombinationRow] = []

    for metric_id, metric in sorted(bundle.internal.metrics.items()):
        sources = sorted(
            entry.source
            for entry in metric.source_availability
            if entry.status is AvailabilityStatus.AVAILABLE
        )
        for version in metric.versions:
            dimensions: list[str | None] = [None, *sorted(version.allowed_dimensions)]
            for source_id in sources:
                for dimension_id in dimensions:
                    request = CatalogValidationRequest(
                        metrics=(metric_id,),
                        dimensions=() if dimension_id is None else (dimension_id,),
                        sources=(source_id,),
                        date_range=window,
                        requester_access=tuple(access),
                    )
                    decision = evaluate(
                        request,
                        bundle,
                        principal_type=principal_type,
                        authorization_scope=authorization_scope,
                        on=on,
                        snapshot=snapshot,
                    )
                    # A caveated combination is still answerable — it is the
                    # caveat that travels with the answer, not a refusal. Only a
                    # denial is excluded from the surface.
                    if decision.outcome is Outcome.DENY:
                        continue
                    rows.append(
                        CombinationRow(
                            metric_id=metric_id,
                            source_id=source_id,
                            dimension_id=dimension_id,
                            aggregation=version.aggregation.value,
                            grain=version.grain,
                            unit=version.unit.value,
                            time_dimension=version.time_dimension,
                            additivity=version.additivity.value,
                        )
                    )

    return CombinationMatrix(rows=tuple(rows), evaluated_on=on)
