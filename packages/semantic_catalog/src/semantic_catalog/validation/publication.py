"""Publication eligibility under D-1 — T112 (FR-076, FR-077).

**Scope boundary.** This is not lifecycle derivation (T040). Lifecycle answers
"is the contract complete?"; this answers "has the business signed off the
decision-bearing inventory the contract depends on?". A metric can be complete,
owned, tagged and still unpublishable because the source it reads has no
approved delay tolerance.

The rule this module exists to enforce, stated once (research §Open business
inputs, authoritative): **sources stay unpublishable while D-1 approval is
absent.** Everything else here follows from it.

An unpublishable source is barred from freshness, coverage, comparability,
availability and every ALLOW/DENY evaluation, and its candidate
``delay_tolerance`` must never appear in a user-facing refusal — a refusal that
quoted an unapproved figure would present it to the reader as governed policy.
It also establishes no semantic-fingerprint baseline: fingerprint evaluation for
a source begins at its first resolving approval, so signing D-1 off registers as
the initial baseline rather than as a semantic change to an already-published
source.

Fails closed everywhere: an absent registry makes every source unpublishable,
because the safe reading of "no approval file" is "nothing is approved".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from ..contracts.freshness_approval import FreshnessApprovalRegistry, FreshnessDenial
from ..contracts.metric import AvailabilityStatus, Metric
from ..contracts.source import Source
from ..loader.load import LoadedCatalog

__all__ = [
    "MetricEligibility",
    "SourceEligibility",
    "metric_eligibilities",
    "metric_eligibility",
    "publishable_source_ids",
    "source_eligibility",
]


@dataclass(frozen=True, slots=True)
class SourceEligibility:
    """Why a source may or may not be published, and used in decisions."""

    source_id: str
    publishable: bool
    denial: FreshnessDenial | None

    @property
    def may_participate_in_decisions(self) -> bool:
        """Freshness, coverage, comparability, availability, ALLOW/DENY."""
        return self.publishable

    @property
    def may_disclose_delay_tolerance(self) -> bool:
        """Whether the tolerance may be named in a user-facing message."""
        return self.publishable

    @property
    def contributes_to_fingerprint(self) -> bool:
        """Fingerprint evaluation starts at the first resolving approval."""
        return self.publishable


@dataclass(frozen=True, slots=True)
class MetricEligibility:
    """A metric is publishable only if every source it declares is."""

    metric_id: str
    publishable: bool
    unapproved_sources: tuple[str, ...]


def source_eligibility(
    source: Source,
    registry: FreshnessApprovalRegistry | None,
    *,
    source_content_commit: str | None,
    on: date,
    permitted_roles: frozenset[str] | None = None,
) -> SourceEligibility:
    """Eligibility for one source. A missing registry denies.

    ``source_content_commit`` is the commit that last modified this source's own
    file — ADR 0033. ``None`` denies: not knowing whether the approved content
    still stands is not the same as it standing.
    """
    if registry is None:
        return SourceEligibility(source.id, False, FreshnessDenial.NO_APPROVAL)
    denial = registry.evaluate(
        source,
        source_content_commit=source_content_commit,
        on=on,
        permitted_roles=permitted_roles,
    )
    return SourceEligibility(source.id, denial is None, denial)


def publishable_source_ids(
    catalog: LoadedCatalog,
    *,
    source_commits: Mapping[str, str] | None,
    on: date,
    permitted_roles: frozenset[str] | None = None,
) -> frozenset[str]:
    """Sources that may be published and used in decisions. Empty is valid.

    **A commit PER SOURCE, which is what ADR 0033 required and what one shared
    commit could not express.** Each source is checked against the commit that
    last touched its own file, so one source's edit does not invalidate another's
    approval — and does not fail to invalidate its own.

    A source absent from the mapping is denied, and so is every source when the
    mapping is ``None``: the caller did not say what the content commit is, and
    an unstated one is unknown rather than unchanged.
    """
    commits = source_commits or {}
    return frozenset(
        source_id
        for source_id, model in catalog.sources.items()
        if source_eligibility(
            model,
            catalog.freshness_approvals,
            source_content_commit=commits.get(source_id),
            on=on,
            permitted_roles=permitted_roles,
        ).publishable
    )


def metric_eligibility(
    metric: Metric,
    publishable_sources: frozenset[str],
) -> MetricEligibility:
    """A metric reading any unapproved source is itself unpublishable.

    Only sources declared ``available`` are considered. A source the metric
    explicitly declares ``unavailable`` — website retention, for instance — is a
    governance decision, not a data dependency, so requiring D-1 approval for it
    would make the metric permanently unpublishable for a source it never reads.

    Declaring **no** available source is not a way around this: a metric with
    nothing to answer from is unpublishable too.
    """
    declared = tuple(
        entry.source
        for entry in metric.source_availability
        if entry.status is AvailabilityStatus.AVAILABLE
    )
    unapproved = tuple(sorted({s for s in declared if s not in publishable_sources}))
    return MetricEligibility(
        metric_id=metric.name,
        publishable=bool(declared) and not unapproved,
        unapproved_sources=unapproved,
    )


def metric_eligibilities(
    catalog: LoadedCatalog,
    *,
    source_commits: Mapping[str, str] | None,
    on: date,
    permitted_roles: frozenset[str] | None = None,
) -> Mapping[str, MetricEligibility]:
    """Eligibility for every loaded metric, keyed by metric name."""
    approved = publishable_source_ids(
        catalog,
        source_commits=source_commits,
        on=on,
        permitted_roles=permitted_roles,
    )
    return {name: metric_eligibility(model, approved) for name, model in catalog.metrics.items()}
