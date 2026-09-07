"""L3 cross-artifact reconciliation — T092 (FR-009).

L1 asks whether a file is well-formed. L2 asks whether the things it points at
exist. **L3 asks whether what the catalog claims about the world is true.**

The asymmetry is the design (research §R-4):

``declared-but-absent`` → **error**
    The catalog says ``installs`` is available on ``google_play`` from January and
    the warehouse has no such coverage. That is a governance lie: a consumer
    reading the catalog would ask a question the data cannot answer, and the
    refusal would arrive later, from a different layer, phrased as a coverage
    problem rather than as a wrong declaration.

``absent-but-declared`` → **warning**
    Coverage exists that nothing governs. Ungoverned data is the normal state of
    a warehouse, not a defect; failing on it would make every new upstream table
    break the catalog build, and stewards would learn to bypass the gate.

The comparison is made against a **caller-supplied** observation, exactly as the
freshness gate is. This module opens no warehouse connection and dereferences no
``source_view``: ``semantic.metric_availability`` is owned by the transformation
feature (D-12 / EXT-A). Until that readiness is declared, the observation comes
from a fixture — and a fixture-backed run says so in the report itself, as a
warning, so nobody reads a green L3 as a statement about production.

A third rule belongs here because it also crosses artifacts: a dimension listed
in ``allowed_dimensions`` must be applicable to at least one source where the
metric is actually available. A dimension that applies nowhere the metric lives
is a combination the matrix would advertise and every request would be refused.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from ..contracts.metric import AvailabilityStatus
from ..freshness.external import ObservedCoverage
from ..loader.load import LoadedCatalog
from .result import Severity, Subject, ValidationFinding, ValidationLayer, ValidationReport

__all__ = [
    "ObservedCoverageSet",
    "load_observed_coverage",
    "validate_reconciliation",
]


@dataclass(frozen=True, slots=True)
class ObservedCoverageSet:
    """What ``semantic.metric_availability`` reports, as the caller read it.

    ``is_fixture`` is not decoration. A fixture proves a rule works; it proves
    nothing about EXT-A readiness, and the flag exists so no downstream reader
    can mistake the two.
    """

    rows: tuple[ObservedCoverage, ...] = ()
    is_fixture: bool = False

    @property
    def pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset((row.metric, row.source) for row in self.rows)

    def row_for(self, metric_id: str, source_id: str) -> ObservedCoverage | None:
        return next(
            (r for r in self.rows if r.metric == metric_id and r.source == source_id),
            None,
        )


def load_observed_coverage(path: Path) -> ObservedCoverageSet:
    """Load an observed-coverage fixture.

    ``is_fixture`` is forced true regardless of what the file claims, so a
    fixture cannot present itself as a production observation by setting a flag.
    """
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping")
    payload = cast("dict[str, object]", raw)
    entries = payload.get("coverage", [])
    if not isinstance(entries, list):
        raise ValueError(f"{path}: 'coverage' must be a list of rows")
    rows = tuple(ObservedCoverage.model_validate(item) for item in cast("list[object]", entries))
    return ObservedCoverageSet(rows=rows, is_fixture=True)


def _finding(
    rule: str,
    kind: str,
    identifier: str,
    message: str,
    *,
    field_path: str | None = None,
    severity: Severity = Severity.ERROR,
) -> ValidationFinding:
    return ValidationFinding(
        layer=ValidationLayer.L3_RECONCILIATION,
        rule=rule,
        severity=severity,
        subject=Subject(kind=kind, identifier=identifier, field_path=field_path),
        message=message,
    )


def _declared_pairs(catalog: LoadedCatalog) -> dict[tuple[str, str], Any]:
    declared: dict[tuple[str, str], Any] = {}
    for metric_id, metric in catalog.metrics.items():
        for entry in metric.source_availability:
            if entry.status is AvailabilityStatus.AVAILABLE:
                declared[(metric_id, entry.source)] = entry
    return declared


def _declared_without_coverage(
    declared: Mapping[tuple[str, str], Any], observed: ObservedCoverageSet
) -> Iterable[ValidationFinding]:
    for (metric_id, source_id), entry in sorted(declared.items()):
        row = observed.row_for(metric_id, source_id)
        if row is None:
            yield _finding(
                "declared_without_coverage",
                "metric",
                metric_id,
                f"metric {metric_id!r} declares availability on source {source_id!r} from "
                f"{entry.available_from}, and the observed coverage set has no row for that "
                "pair; a declaration the data does not support sends a consumer to ask a "
                "question nothing can answer (FR-009)",
                field_path="source_availability",
            )
            continue
        # OD-106 (2026-09-03): num sliding, available_from e proveniencia (a leitura da
        # assinatura), nao claim de dias — o predates e dispensado; o par-vivo acima nao.
        if getattr(entry, "sliding", False):
            continue
        if entry.available_from is not None and entry.available_from < row.min_date:
            yield _finding(
                "declared_availability_predates_coverage",
                "metric",
                metric_id,
                f"metric {metric_id!r} declares availability on {source_id!r} from "
                f"{entry.available_from}, but observed coverage starts {row.min_date}; the "
                "catalog claims days the source does not have (FR-009)",
                field_path="source_availability.available_from",
            )


def _coverage_without_declaration(
    declared: Mapping[tuple[str, str], Any], observed: ObservedCoverageSet
) -> Iterable[ValidationFinding]:
    for pair in sorted(observed.pairs - set(declared)):
        metric_id, source_id = pair
        yield _finding(
            "coverage_without_declaration",
            "metric",
            metric_id,
            f"observed coverage exists for {metric_id!r} on source {source_id!r} with no "
            "declaration governing it; ungoverned data is the normal state and is reported, "
            "not refused",
            severity=Severity.WARNING,
        )


def _dimension_applicability(catalog: LoadedCatalog) -> Iterable[ValidationFinding]:
    for metric_id, metric in sorted(catalog.metrics.items()):
        available = {
            entry.source
            for entry in metric.source_availability
            if entry.status is AvailabilityStatus.AVAILABLE
        }
        if not available:
            continue
        for version in metric.versions:
            for dimension_id in version.allowed_dimensions:
                dimension = catalog.dimensions.get(dimension_id)
                if dimension is None or not dimension.source_applicability:
                    continue  # unresolved is L2's finding; unrestricted applies everywhere
                applicable = {entry.source for entry in dimension.source_applicability}
                if available & applicable:
                    continue
                yield _finding(
                    "dimension_not_applicable_to_any_declared_source",
                    "metric",
                    metric_id,
                    f"metric {metric_id!r} version {version.version} allows dimension "
                    f"{dimension_id!r}, which applies to {sorted(applicable)} and to none of the "
                    f"sources the metric is available on ({sorted(available)}); the combination "
                    "would be advertised and always refused (FR-008, FR-010)",
                    field_path=f"versions[{version.version}].allowed_dimensions",
                )


def validate_reconciliation(
    catalog: LoadedCatalog, observed: ObservedCoverageSet
) -> ValidationReport:
    """Reconcile declared availability against observed coverage.

    An empty report means every declaration is backed by data. Warnings do not
    make the report invalid — only the declared-but-absent direction does.
    """
    declared = _declared_pairs(catalog)
    findings: list[ValidationFinding] = []
    findings.extend(_declared_without_coverage(declared, observed))
    findings.extend(_coverage_without_declaration(declared, observed))
    findings.extend(_dimension_applicability(catalog))

    if observed.is_fixture:
        findings.append(
            _finding(
                "observed_coverage_is_a_fixture",
                "catalog",
                "metric_availability",
                "reconciliation ran against a fixture observation of metric_availability, not "
                "against the warehouse; the result says nothing about production readiness "
                "(D-12 / EXT-A)",
                severity=Severity.WARNING,
            )
        )
    return ValidationReport.from_findings(findings)
