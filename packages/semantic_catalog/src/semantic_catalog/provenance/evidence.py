"""Evidence references and the provenance statement — T074 (FR-039).

Constitution Principle III: **every answer carries its provenance**, or the
system abstains. Five things, and a decision missing any of them is not
something a reader can check:

* contributing **sources**
* **data-as-of** — the instant the evidence was observed
* each source's **last successful update**
* **coverage** actually observed for the requested period
* known **limitations** — offsets, outages, restatements, caveats

The statement is assembled from evidence the decision already stood on, never
re-fetched. Re-reading here would let a provenance statement describe a different
observation than the decision it explains, and nobody would see the difference.

**Identifiers only.** The statement names metrics, sources, revisions and
windows. It carries no metric value, no fact row, no personal data and no prompt
text (FR-041) — there is nothing in it to leak, because none of that is ever put
in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..contracts.audit_event import EvidenceKind, EvidenceRef
from ..freshness.external import FreshnessSnapshot
from ..validation.decision import CatalogDecision
from .revision import RevisionResolution

__all__ = [
    "ProvenanceStatement",
    "SourceProvenance",
    "evidence_refs_for",
    "provenance_for",
]


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """What one contributing source can prove about the answer."""

    source: str
    last_successful_update: datetime | None
    status: str
    coverage_start: date | None
    coverage_end: date | None
    data_revision_id: str | None

    @property
    def is_complete_evidence(self) -> bool:
        """Everything a reader needs to reproduce this source's contribution."""
        return (
            self.last_successful_update is not None
            and self.coverage_start is not None
            and self.coverage_end is not None
            and self.data_revision_id is not None
        )


@dataclass(frozen=True, slots=True)
class ProvenanceStatement:
    """The five things Principle III requires on every answer."""

    sources: tuple[SourceProvenance, ...]
    data_as_of: datetime | None
    limitations: tuple[str, ...]
    catalog_release_id: str
    policy_version: str
    data_revisions: tuple[str, ...]

    @property
    def is_sufficient(self) -> bool:
        """Whether a provenance statement can actually be constructed (SC-008).

        A decision with no contributing source is sufficient only if it refused
        before reaching one — there is genuinely nothing to describe.
        """
        return bool(self.catalog_release_id and self.policy_version)

    def describe(self) -> str:
        """One line per source. Identifiers and timestamps, nothing else."""
        if not self.sources:
            return f"release {self.catalog_release_id}, política {self.policy_version}"
        lines = [
            f"{s.source}: estado {s.status}"
            + (
                f", atualizado {s.last_successful_update.isoformat()}"
                if s.last_successful_update
                else ""
            )
            + (f", cobertura {s.coverage_start}..{s.coverage_end}" if s.coverage_start else "")
            + (f", revisão {s.data_revision_id}" if s.data_revision_id else "")
            for s in self.sources
        ]
        return " | ".join(lines)


def evidence_refs_for(
    metric_version_ids: tuple[str, ...],
    catalog_release_id: str,
    snapshot: FreshnessSnapshot | None,
    resolution: RevisionResolution | None,
    required_sources: tuple[str, ...] = (),
) -> tuple[EvidenceRef, ...]:
    """Every reference a decision stood on, deduplicated and ordered.

    Ordered because two identical decisions must serialise identically; a set
    would make the evidence list depend on hash ordering.
    """
    refs: list[EvidenceRef] = [
        EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id=catalog_release_id)
    ]
    refs += [
        EvidenceRef(kind=EvidenceKind.METRIC_VERSION, id=version_id)
        for version_id in sorted(metric_version_ids)
    ]
    if snapshot is not None and snapshot.snapshot_id:
        for source_id in sorted(set(required_sources)):
            refs.append(
                EvidenceRef(
                    kind=EvidenceKind.FRESHNESS_SNAPSHOT,
                    id=f"{source_id}@{snapshot.snapshot_id}",
                )
            )
    # Coverage windows for the **requested** metrics only. A snapshot carries
    # rows for every metric on a source, and citing all of them would tell a
    # requester which other metrics that source feeds — including ones they are
    # not authorised to see. The decision stood on its own metrics' coverage.
    cited_metrics = {version_id.split("@", 1)[0] for version_id in metric_version_ids}
    if snapshot is not None:
        for source_id in sorted(set(required_sources)):
            for coverage in snapshot.coverage:
                if coverage.metric in cited_metrics and coverage.source == source_id:
                    refs.append(
                        EvidenceRef(
                            kind=EvidenceKind.COVERAGE_WINDOW,
                            id=(
                                f"{coverage.metric}:{coverage.source}:"
                                f"{coverage.min_date}:{coverage.max_date}"
                            ),
                        )
                    )
    if resolution is not None:
        refs += [
            EvidenceRef(kind=EvidenceKind.DATA_REVISION, id=revision_id)
            for revision_id in resolution.revision_ids
        ]

    seen: set[tuple[str, str]] = set()
    unique: list[EvidenceRef] = []
    for ref in refs:
        key = (ref.kind.value, ref.id)
        if key not in seen:
            seen.add(key)
            unique.append(ref)
    return tuple(unique)


def provenance_for(
    decision: CatalogDecision,
    required_sources: tuple[str, ...],
    snapshot: FreshnessSnapshot | None,
    resolution: RevisionResolution | None,
    metric_ids: tuple[str, ...] = (),
) -> ProvenanceStatement:
    """Assemble the provenance statement for a decision."""
    sources: list[SourceProvenance] = []
    for source_id in sorted(set(required_sources)):
        record = snapshot.record_for(source_id) if snapshot is not None else None
        coverage = None
        if snapshot is not None:
            for metric_id in sorted(set(metric_ids)):
                coverage = snapshot.coverage_for(metric_id, source_id)
                if coverage is not None:
                    break
        revision_id = None
        if resolution is not None:
            revision_id = next(
                (r for r in resolution.revision_ids if r.startswith(f"{source_id}@")),
                resolution.revision_ids[0] if len(resolution.revision_ids) == 1 else None,
            )
        sources.append(
            SourceProvenance(
                source=source_id,
                last_successful_update=record.last_successful_update if record else None,
                status=record.status.value if record else "unknown",
                coverage_start=coverage.min_date if coverage else None,
                coverage_end=coverage.max_date if coverage else None,
                data_revision_id=revision_id,
            )
        )

    return ProvenanceStatement(
        sources=tuple(sources),
        data_as_of=snapshot.observed_at if snapshot is not None else None,
        limitations=tuple(limitation.message_pt_br for limitation in decision.limitations),
        catalog_release_id=decision.catalog_release_id,
        policy_version=decision.policy_version,
        data_revisions=tuple(decision.data_revisions),
    )
