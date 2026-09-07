"""The observation port — T038 (FR-074; SC-030, SC-031).

`001` reserves a role for the caller: supply the freshness snapshot. This
feature fills that role by **reading the governed tables itself**, never by
accepting observations from whoever asked the question (`FR-074`).

**One method, returning one whole bundle.** There is deliberately no
``read_freshness()``, ``read_coverage()`` or ``read_revisions()``. Three separate
reads could observe three different instants, and a decision marked `FINAL` on
freshness from one moment and revisions from another describes a state that never
existed. Atomicity is a property of the port's shape, so a caller cannot opt out
of it by calling one method and skipping another.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = [
    "CoverageObservation",
    "FreshnessObservation",
    "ObservationBundle",
    "ObservationReader",
    "RevisionObservation",
]


@dataclass(frozen=True, slots=True)
class FreshnessObservation:
    """When a source was last loaded, as the governed table records it."""

    source_id: str
    last_loaded_at: datetime
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CoverageObservation:
    """Whether a metric is available from a source, and over what window."""

    metric_id: str
    source_id: str
    available: bool
    covered_from: datetime | None = None
    covered_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class RevisionObservation:
    """The data revision a source was at when observed.

    ``revision_id`` is ``None`` when the source cannot supply a stable revision.
    That is what forces `reproducibility: limited` rather than being silently
    treated as "no change" (`FR-043`).
    """

    source_id: str
    revision_id: str | None


@dataclass(frozen=True, slots=True)
class ObservationBundle:
    """Freshness, coverage and revisions read as one atomic snapshot.

    ``read_at`` and ``request_correlation_id`` exist so a reused bundle is
    **detectable**: a bundle carrying another request's correlation id has
    escaped the request it was read for, and that is refused rather than
    tolerated (`FR-077`).
    """

    freshness: tuple[FreshnessObservation, ...]
    coverage: tuple[CoverageObservation, ...]
    revisions: tuple[RevisionObservation, ...]
    read_at: datetime
    request_correlation_id: str

    def source_ids(self) -> frozenset[str]:
        """Every source this bundle says anything about."""
        return frozenset(
            [o.source_id for o in self.freshness]
            + [o.source_id for o in self.coverage]
            + [o.source_id for o in self.revisions]
        )

    def is_atomic_for(self, required_sources: frozenset[str]) -> bool:
        """Whether the bundle covers every required source in all three parts.

        A partial bundle is not a smaller true answer — it is an unknown state
        wearing the shape of an answer.
        """
        if not required_sources:
            return True
        fresh = {o.source_id for o in self.freshness}
        rev = {o.source_id for o in self.revisions}
        cov = {o.source_id for o in self.coverage}
        return required_sources <= fresh and required_sources <= rev and required_sources <= cov


@runtime_checkable
class ObservationReader(Protocol):
    """Reads the governed observation tables. One call, one whole bundle."""

    def read(self, *, source_ids: frozenset[str], correlation_id: str) -> ObservationBundle:
        """Read every observation for ``source_ids`` as one snapshot.

        Raises rather than returning a partial bundle. The caller never sees a
        half-read state to make a judgement call about.
        """
        ...
