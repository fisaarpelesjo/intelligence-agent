"""Whole-release atomic validation — T088 (FR-069).

A release is valid or it is not. There is no partially valid catalog: the public
bundle is one artifact with one content hash, and publishing "most of it" would
publish a release whose id describes content nobody validated.

So this module runs **every layer over the whole tree and returns one verdict**.
L1 schema, L2 referential, L3 reconciliation, L4 policy and L4 version all merge
into a single :class:`~semantic_catalog.validation.result.ValidationReport`, and
:class:`ReleaseValidation` carries it together with the commit it was computed
from. T091 accepts that object and nothing else, which is what keeps the
active-release pointer from moving on an assertion.

**Resolving a version-control conflict is not validation** (FR-069). Two branches
can each append ``version: 2`` to the same metric and merge without a textual
conflict — Git sees two additions to different lines and takes both. The result
is a file with two blocks numbered 2, which is a broken catalog that merged
cleanly. Detecting it *after* the merge is the only place it can be detected, and
that is what :func:`detect_version_collisions` is for.

It reads **raw YAML, before the models**, and that is deliberate. The ``Metric``
contract refuses duplicate version numbers by raising, and a raised exception is
not a report: a steward would see a stack trace naming a pydantic validator
instead of a finding naming their metric and the number they collided on. Reading
the payload first turns the crash into a message.

Unresolved conflict markers left in a file are caught here too, for the same
reason: a file containing ``<<<<<<<`` is not YAML, and "cannot parse" is a much
worse answer than "this file still has a merge conflict in it".
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..contracts.policy import CatalogPolicy, PolicySet, PolicyUnresolvableError
from ..contracts.reason_codes import ReasonCode
from ..loader.load import CatalogLoadError, LoadedCatalog, load_catalog
from .l1_schema import validate_tree
from .l2_referential import validate_references
from .l3_reconciliation import ObservedCoverageSet, validate_reconciliation
from .l4_policy import validate_policy
from .l4_version import FingerprintBaseline, validate_version_gate
from .result import Severity, Subject, ValidationFinding, ValidationLayer, ValidationReport

__all__ = [
    "ReleaseValidation",
    "detect_version_collisions",
    "validate_release",
]

_CONFLICT_MARKER = re.compile(r"^(<{7}|={7}|>{7})(\s|$)", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class ReleaseValidation:
    """One verdict for one commit.

    The commit travels with the verdict because FR-069 requires a release to be
    published from a **single validated commit**. A bare boolean would let a
    caller validate one tree and publish another.
    """

    commit: str
    report: ValidationReport

    @property
    def valid(self) -> bool:
        return self.report.is_valid()

    @property
    def errors(self) -> tuple[ValidationFinding, ...]:
        return self.report.errors


def _finding(
    rule: str,
    kind: str,
    identifier: str,
    message: str,
    *,
    layer: ValidationLayer = ValidationLayer.L1_SCHEMA,
    field_path: str | None = None,
    severity: Severity = Severity.ERROR,
) -> ValidationFinding:
    return ValidationFinding(
        layer=layer,
        rule=rule,
        severity=severity,
        subject=Subject(kind=kind, identifier=identifier, field_path=field_path),
        message=message,
    )


def _raw_metric_payloads(root: Path, pattern: str) -> Iterable[tuple[Path, Mapping[str, Any]]]:
    for path in sorted(root.glob(pattern)):
        text = path.read_text(encoding="utf-8")
        if _CONFLICT_MARKER.search(text):
            yield path, {"__conflict__": True}
            continue
        try:
            raw: Any = yaml.safe_load(text)
        except yaml.YAMLError:
            continue  # L1 reports unparseable files with a better message
        if isinstance(raw, dict) and raw.get("kind") == "metric":  # pyright: ignore[reportUnknownMemberType]
            yield path, raw  # pyright: ignore[reportUnknownArgumentType]


def _version_entries(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    versions: Any = payload.get("versions")
    if not isinstance(versions, list):
        return ()
    return [item for item in versions if isinstance(item, dict)]  # pyright: ignore[reportUnknownVariableType]


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def detect_version_collisions(root: Path, *, pattern: str = "**/*.yaml") -> ValidationReport:
    """Post-merge collisions in authored metric files, read before the models.

    Three collisions, all of which a clean merge can produce:

    * two blocks with the same ``version`` number;
    * two blocks whose effective ranges overlap;
    * two open blocks, which makes "the current definition" ambiguous.
    """
    findings: list[ValidationFinding] = []
    for path, payload in _raw_metric_payloads(root, pattern):
        if payload.get("__conflict__"):
            findings.append(
                _finding(
                    "unresolved_merge_conflict",
                    "metric",
                    path.stem,
                    f"file for {path.stem!r} still contains version-control conflict markers; a "
                    "release is published from a single validated commit, never from a tree "
                    "mid-merge (FR-069)",
                )
            )
            continue

        name = str(payload.get("name") or path.stem)
        entries = _version_entries(payload)

        numbers = [entry.get("version") for entry in entries]
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1 and n is not None})  # pyright: ignore[reportUnknownArgumentType]
        for number in duplicates:
            findings.append(
                _finding(
                    "concurrent_version_collision",
                    "metric",
                    name,
                    f"metric {name!r} declares version {number} more than once. Two changes "
                    "appended the same number and merged cleanly; a clean merge is not "
                    "validation, and duplicate version numbers are invalid (FR-069)",
                    field_path="versions",
                )
            )

        open_blocks = [e for e in entries if e.get("effective_to") in (None, "")]
        if len(open_blocks) > 1:
            findings.append(
                _finding(
                    "multiple_open_versions",
                    "metric",
                    name,
                    f"metric {name!r} has {len(open_blocks)} version blocks with no effective_to; "
                    "only the newest version may be open, or the current definition is ambiguous",
                    field_path="versions",
                )
            )

        findings.extend(_overlap_findings(name, entries))
    return ValidationReport.from_findings(findings)


def _overlap_findings(
    name: str, entries: Sequence[Mapping[str, Any]]
) -> Iterable[ValidationFinding]:
    spans: list[tuple[Any, date, date]] = []
    for entry in entries:
        start = _as_date(entry.get("effective_from"))
        if start is None:
            continue
        end = _as_date(entry.get("effective_to")) or date.max
        spans.append((entry.get("version"), start, end))

    for index, (left_version, left_start, left_end) in enumerate(spans):
        for right_version, right_start, right_end in spans[index + 1 :]:
            if left_start <= right_end and right_start <= left_end:
                yield _finding(
                    "version_ranges_overlap",
                    "metric",
                    name,
                    f"metric {name!r} versions {left_version} and {right_version} claim "
                    "overlapping effective ranges; a date must resolve to exactly one "
                    "definition (FR-034, FR-069)",
                    field_path="versions",
                )


def _effective_policy(catalog: LoadedCatalog, on: date) -> CatalogPolicy | None:
    if not catalog.policies:
        return None
    try:
        return PolicySet(policies=catalog.policies).resolve_effective(on)
    except PolicyUnresolvableError:
        return None


def validate_release(
    root: Path,
    *,
    commit: str,
    on: date,
    baseline: FingerprintBaseline | None = None,
    codeowners: Path | None = None,
    observed: ObservedCoverageSet | None = None,
    publishable: frozenset[ReasonCode] | None = None,
    pattern: str = "**/*.yaml",
) -> ReleaseValidation:
    """Validate an entire release atomically and return one verdict.

    Collisions are detected first, from raw payloads, because a collided file
    cannot load into a model at all. When one is present the report is returned
    immediately: everything after it would be a cascade of consequences from a
    catalog that has not been repaired yet.
    """
    report = detect_version_collisions(root, pattern=pattern)
    if not report.is_valid():
        return ReleaseValidation(commit=commit, report=report)

    report = report.merge(validate_tree(root, pattern=pattern))

    try:
        catalog = load_catalog(root, pattern=pattern)
    except (CatalogLoadError, ValidationError) as exc:
        return ReleaseValidation(
            commit=commit,
            report=report.merge(
                ValidationReport.from_findings(
                    [
                        _finding(
                            "release_does_not_load",
                            "catalog",
                            str(root.name),
                            f"the release rooted at {root.name!r} does not load, so no part of it "
                            f"can be published: {exc}",
                        )
                    ]
                )
            ),
        )

    report = report.merge(validate_references(catalog, codeowners=codeowners))
    report = report.merge(validate_version_gate(catalog, baseline))

    if observed is not None:
        report = report.merge(validate_reconciliation(catalog, observed))

    policy = _effective_policy(catalog, on)
    if policy is None:
        report = report.merge(
            ValidationReport.from_findings(
                [
                    _finding(
                        "policy_unresolvable",
                        "catalog_policy",
                        ReasonCode.POLICY_UNRESOLVABLE.value,
                        f"no single catalog policy is effective on {on}, so "
                        f"{ReasonCode.POLICY_UNRESOLVABLE.value} would be the answer to every "
                        "request; a release cannot be validated under a policy nobody approved "
                        "(FR-072)",
                        layer=ValidationLayer.L4_POLICY,
                    )
                ]
            )
        )
    else:
        report = report.merge(validate_policy(catalog, policy, publishable=publishable))

    return ReleaseValidation(commit=commit, report=report)
