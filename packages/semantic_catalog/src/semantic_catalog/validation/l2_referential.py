"""L2 referential validation — T026 (FR-032, FR-036, FR-073).

L1 asks whether a file is well-formed. L2 asks whether the things it points at
exist. Every reference resolves or the catalog is invalid: owner, dimension,
source, deprecation successor, glossary term, access tag, and each owner's
``review_group`` against ``CODEOWNERS``.

That last one is the reason L2 is not merely a tidiness pass. Ownership facts
live in ``owners.yaml`` so the catalog can read them (FR-032 requires reporting
entries that lack an owner), while merge enforcement lives in CODEOWNERS. Two
places, two jobs — and checking that every ``review_group`` exists in CODEOWNERS
is what stops them drifting into disagreement (research §R-7).

Audience: L2 messages are for the reviewer approving the change, so each one
names both ends of the broken reference.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ..loader.load import LoadedCatalog
from .result import Severity, Subject, ValidationFinding, ValidationLayer, ValidationReport

__all__ = ["parse_codeowners_groups", "validate_references"]

_CODEOWNERS_GROUP = re.compile(r"@[\w.-]+(?:/[\w.-]+)?")


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
        layer=ValidationLayer.L2_REFERENTIAL,
        rule=rule,
        severity=severity,
        subject=Subject(kind=kind, identifier=identifier, field_path=field_path),
        message=message,
    )


def parse_codeowners_groups(path: Path) -> frozenset[str]:
    """Review groups named in a CODEOWNERS file.

    A missing file yields an empty set, which makes every ``review_group``
    unresolvable — deliberately. Silently passing when the routing file is absent
    would let ownership drift unreviewed.
    """
    if not path.is_file():
        return frozenset()
    groups: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        groups.update(_CODEOWNERS_GROUP.findall(stripped))
    return frozenset(groups)


def validate_references(
    catalog: LoadedCatalog, *, codeowners: Path | None = None
) -> ValidationReport:
    """L2 over a loaded catalog. Empty report means every reference resolves."""
    findings: list[ValidationFinding] = []

    owner_ids: frozenset[str] = (
        frozenset(o.id for o in catalog.owners.owners) if catalog.owners else frozenset()
    )
    source_ids: frozenset[str] = frozenset(catalog.sources)
    dimension_ids: frozenset[str] = frozenset(catalog.dimensions)
    metric_ids: frozenset[str] = frozenset(catalog.metrics)
    tag_ids: frozenset[str] = (
        frozenset(t.id for t in catalog.access_tags.tags) if catalog.access_tags else frozenset()
    )

    findings.extend(_owner_findings(catalog, owner_ids))
    findings.extend(
        _metric_findings(catalog, owner_ids, source_ids, dimension_ids, metric_ids, tag_ids)
    )
    findings.extend(_dimension_findings(catalog, owner_ids, source_ids))
    findings.extend(_glossary_findings(catalog, owner_ids))
    findings.extend(_comparability_findings(catalog, metric_ids, source_ids))
    findings.extend(_approval_findings(catalog, owner_ids, metric_ids))
    findings.extend(_freshness_approval_findings(catalog, owner_ids, source_ids))

    if codeowners is not None:
        findings.extend(_review_group_findings(catalog, codeowners))

    return ValidationReport.from_findings(findings)


def _owner_findings(
    catalog: LoadedCatalog, owner_ids: frozenset[str]
) -> Iterable[ValidationFinding]:
    if catalog.owners is None and (catalog.metrics or catalog.sources or catalog.dimensions):
        yield _finding(
            "owners_registry_missing",
            "owners",
            "owners.yaml",
            "owners.yaml is absent, so no owner reference can resolve; every metric and "
            "dimension requires a named accountable owner (FR-032)",
        )
    _ = owner_ids


def _ref(
    findings: list[ValidationFinding],
    *,
    rule: str,
    kind: str,
    identifier: str,
    field_path: str,
    target_kind: str,
    target: str | None,
    known: frozenset[str],
) -> None:
    if target is None or target in known:
        return
    findings.append(
        _finding(
            rule,
            kind,
            identifier,
            f"{kind} {identifier!r} references {target_kind} {target!r}, which is not "
            f"defined; known: {sorted(known) or 'none'}",
            field_path=field_path,
        )
    )


def _metric_findings(
    catalog: LoadedCatalog,
    owner_ids: frozenset[str],
    source_ids: frozenset[str],
    dimension_ids: frozenset[str],
    metric_ids: frozenset[str],
    tag_ids: frozenset[str],
) -> Iterable[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for name, model in sorted(catalog.metrics.items()):
        _ref(
            findings,
            rule="owner_unresolved",
            kind="metric",
            identifier=name,
            field_path="owner",
            target_kind="owner",
            target=model.owner,
            known=owner_ids,
        )
        if tag_ids:
            _ref(
                findings,
                rule="access_tag_unresolved",
                kind="metric",
                identifier=name,
                field_path="access",
                target_kind="access tag",
                target=model.access,
                known=tag_ids,
            )
        for availability in model.source_availability:
            _ref(
                findings,
                rule="source_unresolved",
                kind="metric",
                identifier=name,
                field_path="source_availability.source",
                target_kind="source",
                target=availability.source,
                known=source_ids,
            )
        for version in model.versions:
            for dim in version.allowed_dimensions:
                _ref(
                    findings,
                    rule="dimension_unresolved",
                    kind="metric",
                    identifier=name,
                    field_path=f"versions[{version.version}].allowed_dimensions",
                    target_kind="dimension",
                    target=dim,
                    known=dimension_ids,
                )
        if model.deprecation is not None:
            _ref(
                findings,
                rule="successor_unresolved",
                kind="metric",
                identifier=name,
                field_path="deprecation.successor",
                target_kind="metric",
                target=model.deprecation.successor,
                known=metric_ids,
            )
            _ref(
                findings,
                rule="replacement_unresolved",
                kind="metric",
                identifier=name,
                field_path="deprecation.replacement_metric_id",
                target_kind="metric",
                target=model.deprecation.replacement_metric_id,
                known=metric_ids,
            )
    return findings


def _dimension_findings(
    catalog: LoadedCatalog, owner_ids: frozenset[str], source_ids: frozenset[str]
) -> Iterable[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for name, model in sorted(catalog.dimensions.items()):
        _ref(
            findings,
            rule="owner_unresolved",
            kind="dimension",
            identifier=name,
            field_path="owner",
            target_kind="owner",
            target=model.owner,
            known=owner_ids,
        )
        for applicability in model.source_applicability:
            _ref(
                findings,
                rule="source_unresolved",
                kind="dimension",
                identifier=name,
                field_path="source_applicability.source",
                target_kind="source",
                target=applicability.source,
                known=source_ids,
            )
    return findings


def _glossary_findings(
    catalog: LoadedCatalog, owner_ids: frozenset[str]
) -> Iterable[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for name, model in sorted(catalog.glossary_terms.items()):
        _ref(
            findings,
            rule="owner_unresolved",
            kind="glossary",
            identifier=name,
            field_path="owner",
            target_kind="owner",
            target=model.owner,
            known=owner_ids,
        )
    return findings


def _comparability_findings(
    catalog: LoadedCatalog, metric_ids: frozenset[str], source_ids: frozenset[str]
) -> Iterable[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for name, rule in sorted(catalog.comparability_rules.items()):
        known = metric_ids if rule.subject.value == "metric_pair" else source_ids
        target_kind = "metric" if rule.subject.value == "metric_pair" else "source"
        for side, value in (("left", rule.left), ("right", rule.right)):
            _ref(
                findings,
                rule="comparability_operand_unresolved",
                kind="comparability",
                identifier=name,
                field_path=side,
                target_kind=target_kind,
                target=value,
                known=known,
            )
    return findings


def _approval_findings(
    catalog: LoadedCatalog, owner_ids: frozenset[str], metric_ids: frozenset[str]
) -> Iterable[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if catalog.approvals is None:
        return findings
    for approval in catalog.approvals.approvals:
        identifier = f"{approval.metric_id}.{approval.field_name}"
        _ref(
            findings,
            rule="approval_metric_unresolved",
            kind="approval",
            identifier=identifier,
            field_path="metric_id",
            target_kind="metric",
            target=approval.metric_id,
            known=metric_ids,
        )
        _ref(
            findings,
            rule="approval_role_unresolved",
            kind="approval",
            identifier=identifier,
            field_path="approved_by_role",
            target_kind="owner",
            target=approval.approved_by_role,
            known=owner_ids,
        )
    return findings


def _freshness_approval_findings(
    catalog: LoadedCatalog, owner_ids: frozenset[str], source_ids: frozenset[str]
) -> Iterable[ValidationFinding]:
    """D-1 approvals must point at a real source and a real role (FR-076).

    An approval for a source that does not exist is not harmless: it reads as
    coverage that is not there, and it would silently start covering a source
    later created under that name.
    """
    findings: list[ValidationFinding] = []
    if catalog.freshness_approvals is None:
        return findings
    for approval in catalog.freshness_approvals.approvals:
        _ref(
            findings,
            rule="freshness_approval_source_unresolved",
            kind="freshness_approval",
            identifier=approval.source_id,
            field_path="source_id",
            target_kind="source",
            target=approval.source_id,
            known=source_ids,
        )
        _ref(
            findings,
            rule="freshness_approval_role_unresolved",
            kind="freshness_approval",
            identifier=approval.source_id,
            field_path="approved_by_role",
            target_kind="owner",
            target=approval.approved_by_role,
            known=owner_ids,
        )
    return findings


def _review_group_findings(catalog: LoadedCatalog, codeowners: Path) -> Iterable[ValidationFinding]:
    """Every ``review_group`` must exist in CODEOWNERS (research §R-7)."""
    if catalog.owners is None:
        return
    groups = parse_codeowners_groups(codeowners)
    for entry in catalog.owners.owners:
        if entry.review_group not in groups:
            yield _finding(
                "review_group_unresolved",
                "owner",
                entry.id,
                f"owner {entry.id!r} routes review to {entry.review_group!r}, which does not "
                f"appear in {codeowners.name}; the ownership record and the routing file must "
                "not diverge",
                field_path="review_group",
            )
