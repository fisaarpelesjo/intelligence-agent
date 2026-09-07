"""Fixture observation reader — T043 (FR-075; SC-032).

**Lives under `tests/` and is reachable from nowhere else.** A contract test
scans `src/` for any reference to this module, and there is no flag, environment
variable or deployment mode that selects it. That is the whole design: fixture
observations prove internal behaviour without ever being reachable on the request
path, so they can never be mistaken for evidence about production (`FR-075`).

It produces the same ``ObservationBundle`` the governed reader produces, so tests
exercise the real contract rather than a parallel one — including the failure
shapes, which is why partial and non-atomic bundles are constructible here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from analytics_query.observations.reader import (
    CoverageObservation,
    FreshnessObservation,
    ObservationBundle,
    RevisionObservation,
)

__all__ = ["FixtureObservationReader"]


class FixtureObservationReader:
    """A programmable ``ObservationReader`` for tests.

    ``omit_sources`` and ``drop_part`` exist so the *failure* paths are testable:
    a reader that could only produce well-formed bundles could not prove that a
    partial one refuses.
    """

    __slots__ = (
        "_coverage",
        "_drop_part",
        "_fail_with",
        "_omit",
        "_read_at",
        "_revisions",
        "_stamp",
    )

    def __init__(
        self,
        *,
        last_loaded_at: datetime | None = None,
        revision_id: str | None = "rev-1",
        available: bool = True,
        omit_sources: frozenset[str] = frozenset(),
        drop_part: str | None = None,
        fail_with: Exception | None = None,
        stamp_correlation_id: str | None = None,
    ) -> None:
        self._read_at = last_loaded_at or datetime(2026, 8, 12, tzinfo=UTC)
        self._revisions = revision_id
        self._coverage = available
        self._omit = omit_sources
        self._drop_part = drop_part
        self._fail_with = fail_with
        #: When set, the bundle is stamped with *this* correlation id instead of
        #: the caller's — the shape of a snapshot that escaped its request.
        self._stamp = stamp_correlation_id

    def read(self, *, source_ids: frozenset[str], correlation_id: str) -> ObservationBundle:
        if self._fail_with is not None:
            raise self._fail_with

        included = sorted(source_ids - self._omit)
        freshness = tuple(
            FreshnessObservation(
                source_id=s, last_loaded_at=self._read_at, observed_at=self._read_at
            )
            for s in included
        )
        revisions = tuple(
            RevisionObservation(source_id=s, revision_id=self._revisions) for s in included
        )
        coverage = tuple(
            CoverageObservation(metric_id="installs", source_id=s, available=self._coverage)
            for s in included
        )

        if self._drop_part == "freshness":
            freshness = ()
        elif self._drop_part == "revisions":
            revisions = ()
        elif self._drop_part == "coverage":
            coverage = ()

        return ObservationBundle(
            freshness=freshness,
            coverage=coverage,
            revisions=revisions,
            read_at=self._read_at,
            request_correlation_id=self._stamp or correlation_id,
        )
