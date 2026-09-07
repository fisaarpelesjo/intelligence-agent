"""Required-source reduction — T066 (FR-022; research §R-9).

A request names sources. Only some of them **feed** the requested metrics, and
only those gate the outcome.

The failure this prevents is quiet over-refusal. Ask for store downloads while
naming ``android_app`` in the same request, and a naive gate refuses because
``android_app`` is three days stale — even though downloads are a store metric
and ``android_app`` contributes nothing to the answer. Nothing about the number
would have been wrong.

The mirror failure is over-permission, and the reduction does not cause it: a
source that *does* feed a requested metric is required, and its state gates the
whole evaluation.

Two consequences worth stating, because both have been got wrong elsewhere:

* **Refusal is per evaluation, never a quarantine.** A stale ``website`` denies
  the request that needs it and leaves a request that does not need it
  untouched. Healthy sources stay independently analysable.
* **Reduction is not degradation.** Dropping an unused source from the *gate* is
  not the same as dropping a required one from the *answer*. The second is
  auto-degradation and is forbidden (T070).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..contracts.metric import AvailabilityStatus, Metric

__all__ = ["SourceRequirement", "required_sources", "requirement_map"]


@dataclass(frozen=True, slots=True)
class SourceRequirement:
    """Whether a named source feeds the requested metrics."""

    source: str
    required: bool
    feeds: tuple[str, ...]

    @property
    def gates_the_outcome(self) -> bool:
        return self.required


def required_sources(
    metrics: Mapping[str, Metric],
    requested_metrics: tuple[str, ...],
    requested_sources: tuple[str, ...],
) -> tuple[SourceRequirement, ...]:
    """Classify every named source as required or not, in a stable order.

    A source is required when at least one requested metric declares it
    ``available``. A metric's ``unavailable`` declaration is a governance
    decision that the metric is not answered from there, so such a source feeds
    nothing and is not required.
    """
    requirements: list[SourceRequirement] = []
    for source_id in sorted(set(requested_sources)):
        feeds = tuple(
            metric_id
            for metric_id in sorted(set(requested_metrics))
            if (metric := metrics.get(metric_id)) is not None
            and any(
                entry.source == source_id and entry.status is AvailabilityStatus.AVAILABLE
                for entry in metric.source_availability
            )
        )
        requirements.append(SourceRequirement(source=source_id, required=bool(feeds), feeds=feeds))
    return tuple(requirements)


def requirement_map(
    metrics: Mapping[str, Metric],
    requested_metrics: tuple[str, ...],
    requested_sources: tuple[str, ...],
) -> Mapping[str, SourceRequirement]:
    """The same reduction, keyed by source id."""
    return {r.source: r for r in required_sources(metrics, requested_metrics, requested_sources)}
