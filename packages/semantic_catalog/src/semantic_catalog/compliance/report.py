"""Compliance report — T097 (FR-032; SC-001).

One question, asked of every governed entry: **is this entry compliant, and if
not, exactly what is missing?**

The report composes the existing layers rather than re-deciding anything. L1
says whether a file is well-formed, L2 whether its references resolve, L3
whether its availability claims match observed coverage, L4 whether it satisfies
the governed policy and the version gate. This module attributes those findings
to entries and counts them. It contains no rule of its own, deliberately: a
second implementation of "compliant" would eventually disagree with the first,
and the disagreement would surface as a report that passes while CI fails.

**SC-001 is about published entries.** A pending metric with unset required
fields is not non-compliant — it is pending, which is the system working. What
SC-001 forbids is a *published* entry that is incomplete, unowned or claiming
availability nothing observed. :attr:`ComplianceReport.published_non_compliant`
is the number that must be zero.

``missing_fields`` carries field **names only**, never draft values (FR-018).
Naming the gap is the point; showing the draft would defeat the withholding that
made the entry pending.

**A fixture-backed run says so.** When reconciliation ran against a fixture
observation rather than the warehouse, the report carries
``observed_is_fixture`` and the limitation travels into every rendering. A green
compliance report is not a statement about production until EXT-A readiness is
declared (D-12, T101).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..contracts.metric import Lifecycle
from ..contracts.policy import CatalogPolicy, PolicySet, PolicyUnresolvableError
from ..loader.bundle import Bundle, build_bundle
from ..loader.load import LoadedCatalog, load_catalog
from ..validation.l1_schema import validate_tree
from ..validation.l2_referential import validate_references
from ..validation.l3_reconciliation import ObservedCoverageSet, validate_reconciliation
from ..validation.l4_policy import validate_policy
from ..validation.l4_version import FingerprintBaseline, validate_version_gate
from ..validation.result import Severity, ValidationFinding, ValidationReport

__all__ = [
    "ComplianceEntry",
    "ComplianceReport",
    "compliance_report",
]

#: The limitation stated on every fixture-backed report. Wording is fixed so a
#: reader can grep for it, and so it cannot be softened one caller at a time.
FIXTURE_LIMITATION = (
    "reconciliation ran against a fixture observation of metric_availability, "
    "not against the warehouse; this report says nothing about production readiness "
    "(D-12 / EXT-A)"
)


@dataclass(frozen=True, slots=True)
class ComplianceEntry:
    """One governed entry and why it is or is not compliant."""

    kind: str
    identifier: str
    lifecycle: str | None
    compliant: bool
    missing_fields: tuple[str, ...]
    findings: tuple[str, ...]

    @property
    def is_published(self) -> bool:
        return self.lifecycle in {Lifecycle.PUBLISHED.value, Lifecycle.DEPRECATED.value}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "identifier": self.identifier,
            "compliant": self.compliant,
        }
        if self.lifecycle is not None:
            payload["lifecycle"] = self.lifecycle
        if self.missing_fields:
            payload["missing_fields"] = list(self.missing_fields)
        if self.findings:
            payload["findings"] = list(self.findings)
        return payload


@dataclass(frozen=True, slots=True)
class ComplianceReport:
    """Every governed entry, plus the validation that produced the verdicts."""

    entries: tuple[ComplianceEntry, ...]
    validation: ValidationReport
    evaluated_on: date
    observed_is_fixture: bool
    reconciled: bool

    @property
    def non_compliant(self) -> tuple[ComplianceEntry, ...]:
        return tuple(e for e in self.entries if not e.compliant)

    @property
    def published_non_compliant(self) -> tuple[ComplianceEntry, ...]:
        """SC-001 requires this to be empty."""
        return tuple(e for e in self.non_compliant if e.is_published)

    @property
    def pending(self) -> tuple[ComplianceEntry, ...]:
        return tuple(e for e in self.entries if e.lifecycle == Lifecycle.PENDING.value)

    @property
    def limitations(self) -> tuple[str, ...]:
        stated: list[str] = []
        if self.observed_is_fixture:
            stated.append(FIXTURE_LIMITATION)
        if not self.reconciled:
            stated.append(
                "no observed coverage was supplied, so declared availability was not "
                "reconciled against anything (FR-009)"
            )
        return tuple(stated)

    def is_compliant(self) -> bool:
        """Published entries all compliant **and** no validation error.

        Both halves are required. A clean entry list beside a failing L1 would
        report a catalog that does not load as compliant.
        """
        return not self.published_non_compliant and self.validation.is_valid()

    def to_dict(self) -> dict[str, Any]:
        """Machine-readable form. Stable key order for diffable output."""
        return {
            "evaluated_on": self.evaluated_on.isoformat(),
            "compliant": self.is_compliant(),
            "counts": {
                "entries": len(self.entries),
                "non_compliant": len(self.non_compliant),
                "published_non_compliant": len(self.published_non_compliant),
                "pending": len(self.pending),
                "errors": len(self.validation.errors),
                "warnings": len(self.validation.warnings),
            },
            "limitations": list(self.limitations),
            "entries": [e.to_dict() for e in self.entries],
            "findings": list(self.validation.render()),
        }

    def render(self) -> Sequence[str]:
        lines = [
            f"compliance report for {self.evaluated_on}: "
            f"{'COMPLIANT' if self.is_compliant() else 'NON-COMPLIANT'}",
            f"  entries {len(self.entries)} · non-compliant {len(self.non_compliant)} "
            f"· published non-compliant {len(self.published_non_compliant)} "
            f"· pending {len(self.pending)}",
        ]
        lines += [f"  limitation: {text}" for text in self.limitations]
        for entry in self.non_compliant:
            detail = "; ".join(entry.findings) or f"unset: {', '.join(entry.missing_fields)}"
            lines.append(f"  [{entry.kind}] {entry.identifier}: {detail}")
        lines += [f"  {line}" for line in self.validation.render()]
        return lines


def _findings_by_subject(
    report: ValidationReport,
) -> Mapping[tuple[str, str], tuple[ValidationFinding, ...]]:
    grouped: dict[tuple[str, str], list[ValidationFinding]] = {}
    for finding in report.findings:
        if finding.severity is not Severity.ERROR:
            continue
        grouped.setdefault((finding.subject.kind, finding.subject.identifier), []).append(finding)
    return {key: tuple(value) for key, value in grouped.items()}


def _effective_policy(catalog: LoadedCatalog, on: date) -> CatalogPolicy | None:
    if not catalog.policies:
        return None
    try:
        return PolicySet(policies=catalog.policies).resolve_effective(on)
    except PolicyUnresolvableError:
        return None


def _entries(
    catalog: LoadedCatalog,
    bundle: Bundle,
    grouped: Mapping[tuple[str, str], tuple[ValidationFinding, ...]],
) -> tuple[ComplianceEntry, ...]:
    entries: list[ComplianceEntry] = []

    for metric_id, metric in sorted(catalog.metrics.items()):
        state = bundle.lifecycles.get(metric_id)
        findings = grouped.get(("metric", metric_id), ())
        missing = state.missing_fields if state is not None else metric.unset_required_fields()
        published = state is not None and state.lifecycle is not Lifecycle.PENDING
        entries.append(
            ComplianceEntry(
                kind="metric",
                identifier=metric_id,
                lifecycle=state.lifecycle.value if state is not None else None,
                # A pending metric is not non-compliant for being incomplete —
                # that is the lifecycle working. It is non-compliant only if a
                # validation layer says so.
                compliant=not findings and not (published and missing),
                missing_fields=missing,
                findings=tuple(f"{f.rule}: {f.message}" for f in findings),
            )
        )

    for kind, identifiers in (
        ("dimension", sorted(catalog.dimensions)),
        ("source", sorted(catalog.sources)),
        ("glossary", sorted(catalog.glossary_terms)),
        ("comparability", sorted(catalog.comparability_rules)),
    ):
        for identifier in identifiers:
            findings = grouped.get((kind, identifier), ())
            entries.append(
                ComplianceEntry(
                    kind=kind,
                    identifier=identifier,
                    lifecycle=None,
                    compliant=not findings,
                    missing_fields=(),
                    findings=tuple(f"{f.rule}: {f.message}" for f in findings),
                )
            )
    return tuple(entries)


def compliance_report(
    root: Path,
    *,
    current_commit: str,
    on: date,
    coverage: ObservedCoverageSet | None = None,
    codeowners: Path | None = None,
    baseline: FingerprintBaseline | None = None,
    pattern: str = "**/*.yaml",
) -> ComplianceReport:
    """Compliance across every layer, attributed to entries.

    ``coverage`` is the caller's observed reading of ``semantic.metric_availability``.
    Omitting it is legal and is **reported as a limitation**: without an
    observation there is nothing to reconcile against, and a report that stayed
    silent about that would read as "reconciled and clean".
    """
    catalog = load_catalog(root, pattern=pattern)
    report = validate_tree(root, pattern=pattern)
    report = report.merge(validate_references(catalog, codeowners=codeowners))
    report = report.merge(validate_version_gate(catalog, baseline))

    if coverage is not None:
        report = report.merge(validate_reconciliation(catalog, coverage))

    policy = _effective_policy(catalog, on)
    if policy is not None:
        report = report.merge(validate_policy(catalog, policy))

    bundle = build_bundle(catalog, current_commit=current_commit, on=on)
    return ComplianceReport(
        entries=_entries(catalog, bundle, _findings_by_subject(report)),
        validation=report,
        evaluated_on=on,
        observed_is_fixture=coverage is not None and coverage.is_fixture,
        reconciled=coverage is not None,
    )
