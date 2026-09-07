"""Governed observation reader — T041 (FR-073, FR-077; SC-030).

This feature reads `semantic.source_freshness` and `semantic.metric_availability`
**itself**, under its own read-only credential, and supplies the snapshot to
`001`. The upstream contract reserves that role for the caller; filling it here
is what keeps caller-supplied evidence out of the request path entirely
(`FR-073`, `FR-074`).

The two governed table names are module constants, not parameters. A settable
table name would be a runtime switch over governed content — the reader could be
pointed at a fixture table in production, which is precisely the reachability
`FR-075` forbids.

**Read per request.** Every call produces a fresh bundle stamped with the
requesting correlation id, so a snapshot cannot silently serve a later request
that a fresh read would have refused (`FR-077`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, cast

from .reader import (
    CoverageObservation,
    FreshnessObservation,
    ObservationBundle,
    RevisionObservation,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable, Sequence

__all__ = [
    "AVAILABILITY_TABLE",
    "FRESHNESS_TABLE",
    "BigQueryObservationReader",
    "GovernedObservationStatement",
    "ObservationQueryRunner",
]

#: The only two tables this reader may touch. Constants, never parameters.
FRESHNESS_TABLE = "semantic.source_freshness"
AVAILABILITY_TABLE = "semantic.metric_availability"


class GovernedObservationStatement(StrEnum):
    """The two statements this reader may run. A closed set, not a parameter.

    Naming the statement rather than passing its text means **no SQL string
    crosses the runner boundary at all**. A caller cannot substitute a statement
    it was not offered, and the SQL-surface scan finds no function in this
    package accepting query text.
    """

    SOURCE_FRESHNESS = "source_freshness"
    METRIC_AVAILABILITY = "metric_availability"


#: The governed text for each statement. Module-private and fixed: the enum is
#: the interface, this mapping is the implementation.
_STATEMENT_TEXT: dict[GovernedObservationStatement, str] = {
    GovernedObservationStatement.SOURCE_FRESHNESS: (
        "SELECT source_id, last_loaded_at, data_revision_id "
        f"FROM `{FRESHNESS_TABLE}` WHERE source_id IN UNNEST(@source_ids)"
    ),
    GovernedObservationStatement.METRIC_AVAILABILITY: (
        "SELECT metric_id, source_id, available, covered_from, covered_to "
        f"FROM `{AVAILABILITY_TABLE}` WHERE source_id IN UNNEST(@source_ids)"
    ),
}


class ObservationQueryRunner(Protocol):
    """The narrow slice of warehouse access this reader needs.

    Declared here rather than importing the adapter so the reader depends on a
    row-returning call and nothing else — it cannot execute a governed analytics
    query even by accident.
    """

    def rows(
        self, statement: GovernedObservationStatement, parameters: dict[str, Any]
    ) -> Sequence[dict[str, Any]]:
        """Run one of the two governed statements and return its rows."""
        ...


class BigQueryObservationReader:
    """Reads both governed tables as one snapshot.

    The runner is injected. This module names no project, holds no credential and
    constructs no client — the deployment supplies one, so there is nothing here
    to leak (`FR-027`).
    """

    __slots__ = ("_runner",)

    def __init__(self, runner: ObservationQueryRunner) -> None:
        self._runner = runner

    def read(self, *, source_ids: frozenset[str], correlation_id: str) -> ObservationBundle:
        """Read freshness, coverage and revisions for ``source_ids``.

        Raises rather than returning a partial bundle. Deciding what a half-read
        state means is exactly the judgement call this design refuses to make.
        """
        ordered = sorted(source_ids)
        read_at = datetime.now(UTC)

        freshness_rows = self._runner.rows(
            GovernedObservationStatement.SOURCE_FRESHNESS, {"source_ids": ordered}
        )
        coverage_rows = self._runner.rows(
            GovernedObservationStatement.METRIC_AVAILABILITY, {"source_ids": ordered}
        )

        freshness: list[FreshnessObservation] = []
        revisions: list[RevisionObservation] = []
        for row in _dicts(freshness_rows):
            source_id = _require_str(row, "source_id")
            freshness.append(
                FreshnessObservation(
                    source_id=source_id,
                    last_loaded_at=_require_datetime(row, "last_loaded_at"),
                    observed_at=read_at,
                )
            )
            revision = row.get("data_revision_id")
            revisions.append(
                RevisionObservation(
                    source_id=source_id,
                    revision_id=revision if isinstance(revision, str) and revision else None,
                )
            )

        coverage = [
            CoverageObservation(
                metric_id=_require_str(row, "metric_id"),
                source_id=_require_str(row, "source_id"),
                available=bool(row.get("available")),
                covered_from=_optional_datetime(row, "covered_from"),
                covered_to=_optional_datetime(row, "covered_to"),
            )
            for row in _dicts(coverage_rows)
        ]

        return ObservationBundle(
            freshness=tuple(freshness),
            coverage=tuple(coverage),
            revisions=tuple(revisions),
            read_at=read_at,
            request_correlation_id=correlation_id,
        )


def _dicts(rows: object) -> Iterable[dict[str, Any]]:
    if not isinstance(rows, (list, tuple)):
        raise ValueError("observation read did not return a row sequence")
    return [
        cast("dict[str, Any]", r) for r in cast("Sequence[object]", rows) if isinstance(r, dict)
    ]


def _require_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"observation row is missing a non-empty {key}")
    return value


def _require_datetime(row: dict[str, Any], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise ValueError(f"observation row is missing a datetime {key}")
    return value


def _optional_datetime(row: dict[str, Any], key: str) -> datetime | None:
    value = row.get(key)
    return value if isinstance(value, datetime) else None
