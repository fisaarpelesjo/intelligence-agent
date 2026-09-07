"""Pending safe-metadata projection — T041 (FR-018, FR-060; R-8).

A pending metric is **kept, not removed**. What goes is its unsafe content, and
the way it goes is the whole point of this module: the public shape is
**constructed from an allowlist**, never produced by filtering the metric. There
is no code path here that starts with the full contract and removes things, so
there is no conditional to miss, no verbose flag to trip and no prompt injection
that can surface a field that was never written.

Read-time filtering fails open on the first missed branch. Build-time
construction fails closed by construction.

:class:`PendingStub` is exhaustive — six fields, and the type system enforces
that nothing else can be added to a projection without editing this file:

``name`` always · ``status`` always · ``missing_fields`` always (names only)
``public_name`` only when authored **and** approved
``owner`` only when defined
``expected_available_from`` only when an approved date exists

**Absent for a pending metric**: every version block, ``calculation_basis``,
``numerator``, ``denominator``, ``aggregation``, ``additivity``, ``grain``,
``unit``, ``time_dimension``, ``source_view``, ``exclusions``,
``allowed_dimensions``, draft description and limitations, **all
``source_availability`` entries**, every ``retention.*`` field, and any derived
figure. An availability claim about an unapproved definition is still a claim, so
none is made.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from ..contracts.metric import Metric
from .lifecycle import LifecycleState
from .visibility import VisibilityResolution

__all__ = [
    "EXPOSABLE_PENDING_FIELDS",
    "MetricView",
    "PendingCandidates",
    "PendingStub",
    "pending_candidates",
    "project_metric",
    "project_pending",
    "project_published",
]

#: The only field names a pending projection may ever carry beyond the three
#: unconditional ones. Kept here so a reader can see the closed set at a glance;
#: the authoritative list is the policy's ``pending_visibility.exposable_fields``.
EXPOSABLE_PENDING_FIELDS: tuple[str, ...] = ("public_name", "expected_available_from")


@dataclass(frozen=True, slots=True)
class PendingCandidates:
    """Authored values for the two approval-gated fields, before gating.

    Separated from the projection so the approval gate has something to gate.
    A candidate is not an exposure: both fields still require a resolving
    approval, and both are omitted without one.
    """

    public_name: str | None = None
    expected_available_from: date | None = None


@dataclass(frozen=True, slots=True)
class PendingStub:
    """The exhaustive public shape of a pending metric.

    Six fields. Anything not here is not merely hidden — it is never written.
    """

    name: str
    status: Literal["pending"]
    missing_fields: tuple[str, ...]
    public_name: str | None = None
    owner: str | None = None
    expected_available_from: date | None = None

    def to_public_dict(self) -> dict[str, Any]:
        """Serialisable form, omitting every field that resolved to nothing.

        Omission is literal: an unapproved ``public_name`` produces no key at
        all, not a key with ``null``. A ``null`` still tells a reader the field
        exists and is empty, which is a claim nobody approved.
        """
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "missing_fields": list(self.missing_fields),
        }
        if self.public_name is not None:
            payload["public_name"] = self.public_name
        if self.owner is not None:
            payload["owner"] = self.owner
        if self.expected_available_from is not None:
            payload["expected_available_from"] = self.expected_available_from.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class MetricView:
    """A published metric's public shape — the full governed contract.

    Published means the contract is complete, owned and its sources approved, so
    there is nothing to withhold. The withholding logic lives entirely on the
    pending side, which is why this type carries the model rather than a copy.
    """

    name: str
    status: Literal["published", "deprecated"]
    metric: Metric

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.metric.model_dump(mode="json")
        payload["status"] = self.status
        return payload


def pending_candidates(metric: Metric) -> PendingCandidates:
    """Authored candidate values for the two gated fields.

    ``public_name`` is the pt-BR label of the newest authored version — the
    current authored intent for how the metric is named to a person.

    ``expected_available_from`` has **no authored home** in any approved
    contract: no metric, source or approval field carries a committed
    availability date. It therefore resolves to ``None`` for every metric in the
    catalog today, which matches the specified behaviour — "omitted when nobody
    has committed to one" (research §R-8). The parameter exists so the approval
    path is exercised rather than assumed; it is never defaulted or inferred.
    """
    newest = max(metric.versions, key=lambda v: (v.effective_from, v.version))
    return PendingCandidates(public_name=newest.content.label, expected_available_from=None)


def project_pending(
    metric: Metric,
    state: LifecycleState,
    *,
    visibility: VisibilityResolution,
    candidates: PendingCandidates | None = None,
    owner_known: bool = True,
) -> PendingStub:
    """Build the pending stub. Every conditional field defaults to omitted."""
    values = candidates if candidates is not None else pending_candidates(metric)

    public_name = values.public_name if visibility.exposes("public_name") else None
    expected = (
        values.expected_available_from if visibility.exposes("expected_available_from") else None
    )

    return PendingStub(
        name=metric.name,
        status="pending",
        missing_fields=state.missing_fields,
        public_name=public_name,
        owner=metric.owner if owner_known else None,
        expected_available_from=expected,
    )


def project_published(metric: Metric, state: LifecycleState) -> MetricView:
    """Build the published (or deprecated) view."""
    status: Literal["published", "deprecated"] = (
        "deprecated" if state.lifecycle.value == "deprecated" else "published"
    )
    return MetricView(name=metric.name, status=status, metric=metric)


def project_metric(
    metric: Metric,
    state: LifecycleState,
    *,
    visibility: VisibilityResolution,
    candidates: PendingCandidates | None = None,
    owner_known: bool = True,
) -> MetricView | PendingStub:
    """Project one metric according to its derived lifecycle."""
    if state.is_pending:
        return project_pending(
            metric,
            state,
            visibility=visibility,
            candidates=candidates,
            owner_known=owner_known,
        )
    return project_published(metric, state)
