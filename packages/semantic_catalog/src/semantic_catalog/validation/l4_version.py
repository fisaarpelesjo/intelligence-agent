"""L4 version gate and closed-version immutability — T087 (FR-033, FR-069).

Three rules, and the first one is the whole point of the semantic fingerprint:

**A Semantic edit requires a new version block.** If an existing block's
fingerprint moved and no new block was appended, the build fails naming the
fields that moved. Not "a field changed" — *which* fields, so the steward can
see whether they meant to redefine the metric or fat-fingered a unit.

**A closed version is immutable in its Semantic fields.** A block whose
``effective_to`` is set answers periods that are already closed, and figures
already published for them must not change (FR-034, SC-021). Appending a new
block does **not** excuse editing an old one: the new block governs new dates, so
touching the old one can only be rewriting history. Descriptive edits to a closed
version are permitted and produce no finding — a description is allowed to
improve, and the fingerprint does not cover it.

**Nothing is deleted, and numbers strictly increase.** A version present in the
baseline and absent now is an error, as is a metric that disappeared: FR-065
requires deprecated versions to stay resolvable for audit forever. A new block
numbered at or below the highest baseline number is an error too — duplicate and
decreasing numbers make ``metric_version_id`` ambiguous across releases, which
FR-069 forbids.

One rule needs no baseline and runs on any catalog: **no gaps between version
blocks**. The ``Metric`` contract refuses overlaps, but a hole between
``effective_to`` and the next ``effective_from`` passes it, and a day inside that
hole has no governed definition — a period covering it cannot be answered and
must not be answered by the nearest neighbour.

The baseline is supplied by the caller — the merge base, the previous release,
whatever the build compares against. This module opens no repository and shells
out to no Git: what to compare against is the caller's decision, and hiding it
here would make the gate untestable without a working tree.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from typing import Any

from ..contracts.metric import Metric
from ..loader.load import LoadedCatalog
from ..resolution.fingerprint import digest, fingerprint_inputs
from .result import Severity, Subject, ValidationFinding, ValidationLayer, ValidationReport

__all__ = [
    "FingerprintBaseline",
    "VersionRecord",
    "moved_fields",
    "validate_version_gate",
]

_ONE_DAY = timedelta(days=1)


def _finding(
    rule: str,
    identifier: str,
    message: str,
    *,
    field_path: str | None = None,
    severity: Severity = Severity.ERROR,
) -> ValidationFinding:
    return ValidationFinding(
        layer=ValidationLayer.L4_POLICY,
        rule=rule,
        severity=severity,
        subject=Subject(kind="metric", identifier=identifier, field_path=field_path),
        message=message,
    )


@dataclass(frozen=True, slots=True)
class VersionRecord:
    """One version block as the baseline saw it.

    The **inputs** are kept, not only the digest. A digest can say that something
    moved; only the inputs can say what, and "your fingerprint changed" is not a
    message a steward can act on.
    """

    metric_id: str
    version: int
    inputs: Mapping[str, Any]
    effective_from: date
    effective_to: date | None

    @property
    def fingerprint(self) -> str:
        return digest(self.inputs)

    @property
    def is_closed(self) -> bool:
        """A closed block has an end date; it answers periods already settled."""
        return self.effective_to is not None


@dataclass(frozen=True, slots=True)
class FingerprintBaseline:
    """What the catalog looked like before this change."""

    records: Mapping[tuple[str, int], VersionRecord]

    @classmethod
    def from_metrics(cls, metrics: Mapping[str, Metric]) -> FingerprintBaseline:
        records: dict[tuple[str, int], VersionRecord] = {}
        for metric_id, metric in metrics.items():
            metric_inputs = fingerprint_inputs(metric)
            for version in metric.versions:
                records[(metric_id, version.version)] = VersionRecord(
                    metric_id=metric_id,
                    version=version.version,
                    inputs={**metric_inputs, **fingerprint_inputs(version)},
                    effective_from=version.effective_from,
                    effective_to=version.effective_to,
                )
        return cls(records=records)

    @classmethod
    def from_catalog(cls, catalog: LoadedCatalog) -> FingerprintBaseline:
        return cls.from_metrics(catalog.metrics)

    def versions_of(self, metric_id: str) -> tuple[int, ...]:
        return tuple(sorted(v for (m, v) in self.records if m == metric_id))

    @property
    def metric_ids(self) -> frozenset[str]:
        return frozenset(m for (m, _) in self.records)


def moved_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[str, ...]:
    """Field paths whose fingerprinted value differs, sorted.

    Added and removed paths count as moved: a field that appeared or vanished
    changed the definition just as much as one that was edited.
    """
    paths = set(before) | set(after)
    return tuple(sorted(path for path in paths if before.get(path) != after.get(path)))


def _current_records(metrics: Mapping[str, Metric]) -> Mapping[tuple[str, int], VersionRecord]:
    return FingerprintBaseline.from_metrics(metrics).records


def _gap_findings(metrics: Mapping[str, Metric]) -> list[ValidationFinding]:
    """Days between version blocks that no definition covers (FR-034)."""
    findings: list[ValidationFinding] = []
    for metric_id, metric in sorted(metrics.items()):
        ordered = sorted(metric.versions, key=lambda v: v.effective_from)
        for earlier, later in pairwise(ordered):
            if earlier.effective_to is None:
                continue  # the contract already refuses an open block mid-history
            expected = earlier.effective_to + _ONE_DAY
            if later.effective_from > expected:
                findings.append(
                    _finding(
                        "version_range_gap",
                        metric_id,
                        f"metric {metric_id!r} has no definition between {expected} and "
                        f"{later.effective_from - _ONE_DAY}: version {earlier.version} closes "
                        f"{earlier.effective_to} and version {later.version} opens "
                        f"{later.effective_from}. A period covering those days cannot be "
                        "answered, and must not be answered by a neighbouring version",
                        field_path=f"versions[{later.version}].effective_from",
                    )
                )
    return findings


def validate_version_gate(
    catalog: LoadedCatalog | Mapping[str, Metric],
    baseline: FingerprintBaseline | None = None,
) -> ValidationReport:
    """Run the version gate. An empty report means every rule passed.

    Without a ``baseline`` only the rules that need no history run, so this is
    safe to call on a first release or on the production catalog directly.
    """
    metrics = catalog.metrics if isinstance(catalog, LoadedCatalog) else catalog
    findings: list[ValidationFinding] = _gap_findings(metrics)

    if baseline is None:
        return ValidationReport.from_findings(findings)

    current = _current_records(metrics)

    for metric_id in sorted(baseline.metric_ids):
        if metric_id not in metrics:
            findings.append(
                _finding(
                    "metric_removed",
                    metric_id,
                    f"metric {metric_id!r} was in the baseline and is absent now; deprecated "
                    "metrics and their versions stay resolvable for audit and are never "
                    "deleted (FR-065)",
                )
            )

    for key in sorted(baseline.records):
        metric_id, version_number = key
        if metric_id not in metrics:
            continue  # already reported as a removed metric
        before = baseline.records[key]
        after = current.get(key)

        if after is None:
            findings.append(
                _finding(
                    "version_removed",
                    metric_id,
                    f"metric {metric_id!r} version {version_number} was in the baseline and is "
                    "absent now; no version block is ever deleted (FR-065)",
                    field_path=f"versions[{version_number}]",
                )
            )
            continue

        if before.fingerprint == after.fingerprint:
            continue

        moved = moved_fields(before.inputs, after.inputs)
        appended = sorted(
            set(baseline.versions_of(metric_id)) ^ {v for (m, v) in current if m == metric_id}
        )

        if before.is_closed:
            findings.append(
                _finding(
                    "closed_version_semantic_edit",
                    metric_id,
                    f"metric {metric_id!r} version {version_number} is closed "
                    f"({before.effective_from}..{before.effective_to}) and its semantic fields "
                    f"changed: {list(moved)}. Periods already answered under it must not change; "
                    "closed versions accept Descriptive edits only (SC-021, FR-034)",
                    field_path=f"versions[{version_number}]",
                )
            )
            continue

        if not appended:
            findings.append(
                _finding(
                    "semantic_edit_without_new_version",
                    metric_id,
                    f"metric {metric_id!r} version {version_number} changed semantic fields "
                    f"{list(moved)} without a new version block; a change to what the number "
                    "means requires a new version with its own effective_from (FR-033)",
                    field_path=f"versions[{version_number}]",
                )
            )

    findings.extend(_new_version_number_findings(metrics, baseline, current))
    return ValidationReport.from_findings(findings)


def _new_version_number_findings(
    metrics: Mapping[str, Metric],
    baseline: FingerprintBaseline,
    current: Mapping[tuple[str, int], VersionRecord],
) -> list[ValidationFinding]:
    """New blocks must number above every baseline block (FR-069)."""
    findings: list[ValidationFinding] = []
    for metric_id in sorted(metrics):
        known = baseline.versions_of(metric_id)
        if not known:
            continue
        highest = max(known)
        for _, version_number in sorted(k for k in current if k[0] == metric_id):
            if version_number in known or version_number > highest:
                continue
            findings.append(
                _finding(
                    "version_number_not_increasing",
                    metric_id,
                    f"metric {metric_id!r} adds version {version_number}, which does not exceed "
                    f"the highest baseline version {highest}; version numbers strictly increase "
                    "so that a metric_version_id means one thing forever (FR-069)",
                    field_path=f"versions[{version_number}].version",
                )
            )
    return findings
