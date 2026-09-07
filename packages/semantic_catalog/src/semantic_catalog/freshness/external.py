"""External read-only contracts — T062 (FR-020; data-model §3.1, §3.2).

``semantic.source_freshness`` and ``semantic.metric_availability`` are owned by
the transformation feature (D-12 / EXT-A). This module models what they return
and nothing else.

**The library opens no warehouse connection.** The caller reads those tables and
passes a :class:`FreshnessSnapshot` in. Three things follow, and all three are
the reason:

* no credential is ever held here, so none can leak from a governance artifact;
* every gate is testable from a fixture, with no network and no warehouse;
* this feature creates **no BigQuery object, no DDL, no DML, no scheduled job** —
  it reads two tables it does not own and dereferences nothing else (NG-1, NG-2).

``lag`` and ``within_tolerance`` are **derived at read time**, never stored.
Tolerance is authored in Git; lag is observed in the warehouse. The comparison
between the two *is* the freshness gate, and materialising it would freeze one
half of a comparison that must be made fresh each time.

A fixture is a fixture. Loading one proves a gate branch works; it proves
nothing about EXT-A readiness, and :attr:`FreshnessSnapshot.is_fixture` exists so
no downstream reader can mistake the two.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, StrictBool, StrictInt, model_validator

from ..contracts._base import CatalogModel, Identifier
from ..contracts.source import Source

__all__ = [
    "CompletenessStatus",
    "FreshnessRecord",
    "FreshnessSnapshot",
    "ObservedCoverage",
    "load_snapshot",
]


class CompletenessStatus(StrEnum):
    """The five states ``semantic.source_freshness`` reports (FR-021)."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    DELAYED = "delayed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class FreshnessRecord(CatalogModel):
    """One row of ``semantic.source_freshness``. Read-only; never written here."""

    source: Identifier
    status: CompletenessStatus
    observed_at: datetime

    ingestion_started_at: datetime | None = None
    ingestion_finished_at: datetime | None = None
    source_max_event_at: datetime | None = None
    expected_max_event_at: datetime | None = None
    completeness_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    row_count: StrictInt | None = Field(default=None, ge=0)
    previous_row_count: StrictInt | None = Field(default=None, ge=0)
    last_error: str | None = None
    last_successful_update: datetime | None = None

    @model_validator(mode="after")
    def _failed_states_explain_themselves(self) -> FreshnessRecord:
        if self.status is CompletenessStatus.FAILED and not self.last_error:
            raise ValueError(
                f"source {self.source!r} reports 'failed' with no last_error; "
                "a failure nobody can act on is not a report"
            )
        return self

    def lag(self, *, now: datetime) -> timedelta | None:
        """Observed lag, derived at read time. ``None`` when unobservable."""
        reference = self.last_successful_update or self.source_max_event_at
        if reference is None:
            return None
        return now - reference

    def within_tolerance(self, source: Source, *, now: datetime) -> bool | None:
        """``None`` when the lag cannot be observed — which is not 'fine'.

        Callers must treat ``None`` as unknown and refuse, never as a pass. The
        three-valued return exists so that distinction cannot be lost in a
        boolean.
        """
        observed = self.lag(now=now)
        if observed is None:
            return None
        return observed <= source.delay_tolerance


class ObservedCoverage(CatalogModel):
    """One row of ``semantic.metric_availability``. Read-only."""

    metric: Identifier
    source: Identifier
    min_date: date
    max_date: date
    observed_at: datetime
    dimension_set: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def _ordered(self) -> ObservedCoverage:
        if self.max_date < self.min_date:
            raise ValueError(
                f"coverage for {self.metric}/{self.source} ends {self.max_date} "
                f"before it starts {self.min_date}"
            )
        return self

    def covers(self, start: date, end: date) -> bool:
        return self.min_date <= start and self.max_date >= end


class FreshnessSnapshot(CatalogModel):
    """One observation of both external tables, supplied by the caller.

    Immutable and self-describing: a decision cites the snapshot it stood on, so
    the snapshot cannot be something the library re-fetched half way through.
    """

    observed_at: datetime
    records: tuple[FreshnessRecord, ...] = ()
    coverage: tuple[ObservedCoverage, ...] = ()
    is_fixture: StrictBool = Field(
        default=False,
        description="True for a unit fixture. Never asserts EXT-A production readiness.",
    )
    snapshot_id: str | None = None

    @model_validator(mode="after")
    def _one_record_per_source(self) -> FreshnessSnapshot:
        seen = [r.source for r in self.records]
        if len(set(seen)) != len(seen):
            raise ValueError("two freshness records for the same source in one snapshot")
        return self

    def record_for(self, source_id: str) -> FreshnessRecord | None:
        """``None`` means the snapshot says nothing — an unknown state, not a pass."""
        return next((r for r in self.records if r.source == source_id), None)

    def coverage_for(self, metric_id: str, source_id: str) -> ObservedCoverage | None:
        return next(
            (c for c in self.coverage if c.metric == metric_id and c.source == source_id),
            None,
        )

    @property
    def sources(self) -> frozenset[str]:
        return frozenset(r.source for r in self.records)


def load_snapshot(path: Path) -> FreshnessSnapshot:
    """Load a snapshot from a YAML fixture.

    Fixtures load with ``is_fixture`` forced true regardless of what the file
    claims, so a fixture cannot present itself as a production observation by
    setting a flag.
    """
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping")
    payload: Mapping[str, Any] = {**raw, "is_fixture": True}
    return FreshnessSnapshot.model_validate(payload)
