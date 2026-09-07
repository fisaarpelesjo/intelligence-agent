"""Answerable-subset disclosure — T070 (FR-022; research §R-9).

When a required source is refused, the request **as asked** is denied. Full
stop. The healthy sources may be *named* so the reader knows what a narrower
request would reach — and that is all naming them does.

**Auto-degradation is forbidden.** Answering a three-source request from the two
healthy ones and returning that as the result would present a different
comparison than the one asked for, under the label of the one asked for. Nobody
reading it could tell. The disclosure exists precisely so the catalog can be
helpful without doing that: it tells the reader where to go and makes them ask.

Two properties enforce it:

* the decision carrying a subset is **still ``DENY``** — the model refuses any
  other outcome (T050);
* the subset lists **source identifiers only**, never a figure, a window or a
  partial result. There is nothing in it to mistake for an answer.

Disclosure is governed, not automatic: ``refusal.disclose_answerable_subset`` in
the catalog policy decides whether the hint is offered at all.
"""

from __future__ import annotations

from ..contracts.policy import CatalogPolicy
from ..contracts.reason_codes import Outcome, ReasonCode
from ..freshness.external import CompletenessStatus, FreshnessSnapshot
from ..freshness.required import SourceRequirement
from ..loader.load import LoadedCatalog

__all__ = ["DISCLOSABLE_REASONS", "PROTECTS_SOURCE_METADATA", "answerable_subset"]

#: Refusals that must disclose nothing about which sources a metric draws on or
#: when they last loaded. An authorisation denial listing contributing sources,
#: their states and their update times would hand the requester exactly the shape
#: of a metric they are not permitted to see — the disclosure Gate 3 runs early
#: to prevent. Existence and policy refusals are included for the same reason:
#: there is nothing governed to describe, so describing anything is a leak.
PROTECTS_SOURCE_METADATA = frozenset(
    {
        ReasonCode.ACCESS_DENIED,
        ReasonCode.ACCESS_TAG_UNKNOWN,
        ReasonCode.ACCESS_TAG_DEPRECATED,
        ReasonCode.ACCESS_TAG_SCOPE_MISMATCH,
        ReasonCode.METRIC_NOT_GOVERNED,
        ReasonCode.DIMENSION_NOT_GOVERNED,
        ReasonCode.SOURCE_NOT_GOVERNED,
        ReasonCode.POLICY_UNRESOLVABLE,
    }
)

#: Refusals a subset can usefully qualify: the request failed because a specific
#: required source was unusable, so naming the usable ones is actionable. A
#: refusal about the metric, the policy or the requester is not narrowed by
#: dropping a source, and offering a subset there would misdirect the reader.
DISCLOSABLE_REASONS = frozenset(
    {
        ReasonCode.SOURCE_BEYOND_TOLERANCE,
        ReasonCode.SOURCE_STATE_FAILED,
        ReasonCode.SOURCE_STATE_PARTIAL,
        ReasonCode.SOURCE_STATE_UNKNOWN,
        ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD,
    }
)


def answerable_subset(
    catalog: LoadedCatalog,
    policy: CatalogPolicy,
    requirements: tuple[SourceRequirement, ...],
    snapshot: FreshnessSnapshot | None,
    *,
    outcome: Outcome,
    reason_code: ReasonCode,
    now_source_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Required sources that would have passed. Empty unless it helps.

    Returns nothing at all when the outcome is not a denial: a subset on an
    allow would be a second, quieter result travelling beside the first.
    """
    if outcome is not Outcome.DENY:
        return ()
    if reason_code not in DISCLOSABLE_REASONS:
        return ()
    if not policy.refusal.disclose_answerable_subset:
        return ()
    if snapshot is None:
        return ()

    healthy: list[str] = []
    for requirement in requirements:
        if not requirement.required:
            continue
        source = catalog.sources.get(requirement.source)
        record = snapshot.record_for(requirement.source)
        if source is None or record is None:
            continue
        if record.status is not CompletenessStatus.COMPLETE and record.status is not (
            CompletenessStatus.DELAYED
        ):
            continue
        if record.within_tolerance(source, now=snapshot.observed_at) is not True:
            continue
        healthy.append(requirement.source)

    # A subset that is the whole set discloses nothing and reads as a
    # contradiction beside the denial.
    required = {r.source for r in requirements if r.required}
    if not healthy or set(healthy) == required:
        return ()
    _ = now_source_ids
    return tuple(sorted(healthy))
