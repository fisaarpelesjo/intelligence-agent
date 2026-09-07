"""Governed data revisions — T072 (FR-066, FR-067, FR-068).

A data revision is the transformation feature's statement of *which state of the
data* an answer stood on. It is supplied (EXT-A / D-12), never derived here: the
catalog cannot know that a source republished last month, and inventing an
identifier would fabricate the very provenance this exists to record.

Three rules, each guarding a different failure:

**A restatement creates a new revision** (FR-067). The figures moved under an
unchanged definition, so the old answer was not wrong when it was given — it was
answered from data that no longer exists. Reusing the revision id would make two
different answers indistinguishable.

**A missing or unstable revision means ``limited`` reproducibility** (FR-068).
The classification travels with the answer, and autonomous publication is denied
for anything relying on it. Not because the number is wrong, but because nobody
can reproduce it, and an unreproducible number published without review is a
claim no one can check later.

**Nothing here mutates a prior revision.** Revisions accumulate; the newest is
resolved, the older ones stay readable. An audit that cannot see the revision an
old decision used cannot explain that decision.

``is_stable`` is the load-bearing flag. A source that reports *a* revision but
cannot guarantee the identifier is durable is worse than one reporting none: the
first looks reproducible.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, StrictBool, model_validator

from ..contracts._base import CatalogModel, Identifier, PtBrText
from ..contracts.reason_codes import ReasonCode

__all__ = [
    "DataRevision",
    "RevisionResolution",
    "RevisionSnapshot",
    "load_revisions",
    "resolve_revisions",
]


class DataRevision(CatalogModel):
    """One governed statement of a source's data state (data-model §4.6)."""

    data_revision_id: str = Field(min_length=1)
    source: Identifier
    revised_at: datetime
    reason: PtBrText | None = None

    is_stable: StrictBool = Field(
        default=True,
        description="False when the producer cannot guarantee a durable identifier (FR-068).",
    )
    restates_from: date | None = None
    restates_to: date | None = None
    supersedes_revision_id: str | None = None

    @model_validator(mode="after")
    def _restatement_is_a_complete_statement(self) -> DataRevision:
        """A restatement names its window and says why, or it is not one.

        A revision that claims to restate but cannot say *what* leaves a reader
        unable to tell which of their previous answers moved.
        """
        window = (self.restates_from, self.restates_to)
        if any(window) and not all(window):
            raise ValueError(
                f"revision {self.data_revision_id!r} declares half a restatement window; "
                "a restatement names both ends or neither"
            )
        if self.is_restatement and not self.reason:
            raise ValueError(
                f"revision {self.data_revision_id!r} restates "
                f"{self.restates_from}..{self.restates_to} with no stated reason (FR-067)"
            )
        if (
            self.restates_from is not None
            and self.restates_to is not None
            and self.restates_to < self.restates_from
        ):
            raise ValueError(
                f"revision {self.data_revision_id!r} restates a window ending before it starts"
            )
        return self

    @property
    def is_restatement(self) -> bool:
        return self.restates_from is not None and self.restates_to is not None

    def touches(self, start: date, end: date) -> bool:
        """Whether this restatement overlaps a requested period."""
        if not self.is_restatement:
            return False
        assert self.restates_from is not None and self.restates_to is not None
        return self.restates_from <= end and self.restates_to >= start


class RevisionSnapshot(CatalogModel):
    """The revisions a caller observed, one per source at most.

    Supplied by the caller for the same reason the freshness snapshot is: this
    library reads no warehouse, holds no credential, and must be reproducible
    from a fixture.
    """

    observed_at: datetime
    revisions: tuple[DataRevision, ...] = ()
    is_fixture: StrictBool = Field(
        default=False,
        description="True for a unit fixture. Never asserts EXT-A production readiness.",
    )

    @model_validator(mode="after")
    def _one_revision_per_source(self) -> RevisionSnapshot:
        seen = [revision.source for revision in self.revisions]
        if len(set(seen)) != len(seen):
            raise ValueError(
                "two revisions for the same source in one snapshot; which one an answer "
                "stood on must never depend on ordering"
            )
        return self

    def for_source(self, source_id: str) -> DataRevision | None:
        """``None`` means the producer said nothing — not that nothing changed."""
        return next((r for r in self.revisions if r.source == source_id), None)


@dataclass(frozen=True, slots=True)
class RevisionResolution:
    """What the required sources could prove about their data state."""

    revision_ids: tuple[str, ...]
    missing_sources: tuple[str, ...]
    unstable_sources: tuple[str, ...]
    restatements: tuple[DataRevision, ...]

    @property
    def is_reproducible(self) -> bool:
        """Every required source supplied a stable revision."""
        return not self.missing_sources and not self.unstable_sources

    @property
    def limitation_code(self) -> ReasonCode | None:
        """``REPRODUCIBILITY_LIMITED`` when anything is missing or unstable."""
        return None if self.is_reproducible else ReasonCode.REPRODUCIBILITY_LIMITED

    @property
    def restatement_code(self) -> ReasonCode | None:
        return ReasonCode.PERIOD_RESTATED if self.restatements else None

    @property
    def permits_autonomous_publication(self) -> bool:
        """FR-068. Denied while reproducibility is limited."""
        return self.is_reproducible

    def describe(self) -> str:
        if self.is_reproducible:
            return f"revisões estáveis: {', '.join(self.revision_ids)}"
        gaps = ", ".join(sorted({*self.missing_sources, *self.unstable_sources}))
        return f"sem revisão estável para: {gaps}"


def resolve_revisions(
    required_sources: tuple[str, ...],
    snapshot: RevisionSnapshot | None,
    *,
    period_start: date,
    period_end: date,
) -> RevisionResolution:
    """Resolve the revision state of every required source.

    An absent snapshot is not an empty one: with no snapshot at all, every
    required source is missing, which is the fail-closed reading. A caller that
    supplied nothing has proven nothing.
    """
    revision_ids: list[str] = []
    missing: list[str] = []
    unstable: list[str] = []
    restatements: list[DataRevision] = []

    for source_id in sorted(set(required_sources)):
        revision = snapshot.for_source(source_id) if snapshot is not None else None
        if revision is None:
            missing.append(source_id)
            continue
        if not revision.is_stable:
            # Recorded as unstable rather than silently accepted: a revision id
            # that may change is not evidence, and reads as though it were.
            unstable.append(source_id)
            continue
        revision_ids.append(revision.data_revision_id)
        if revision.touches(period_start, period_end):
            restatements.append(revision)

    return RevisionResolution(
        revision_ids=tuple(sorted(revision_ids)),
        missing_sources=tuple(missing),
        unstable_sources=tuple(unstable),
        restatements=tuple(restatements),
    )


def load_revisions(path: Path) -> RevisionSnapshot:
    """Load a revision snapshot from a YAML fixture.

    ``is_fixture`` is forced true whatever the file says, so a fixture cannot
    present itself as a production observation.
    """
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping")
    payload: Mapping[str, Any] = {**raw, "is_fixture": True}
    return RevisionSnapshot.model_validate(payload)
