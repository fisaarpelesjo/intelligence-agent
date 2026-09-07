"""L1 schema validation — T025 (FR-002, FR-021, FR-053, FR-069).

L1 answers one question per file: *is this a well-formed contract?* Most of the
work is already done by the Pydantic models, which enforce required fields,
types, enum membership, version-range contiguity and deterministic effective
dates. This layer runs them over the authored tree and converts every failure
into a :class:`ValidationFinding` that names the offending field.

It adds the rules a single model cannot see:

* **identifier casing** — English snake_case (FR-053), checked on the identifier
  a file claims for itself;
* **filename agreement** — ``metrics/active_users.yaml`` must define
  ``active_users``. Two names for one thing is how a rename half-happens;
* **delay tolerance** — enforced by the ``Source`` model itself (FR-021 has no
  global default), so a missing tolerance surfaces here as a ``schema_violation``
  naming the field rather than as a separate L1 rule;
* **version numbers strictly increasing** — FR-069, checked here so the message
  names the metric rather than surfacing as a raw model error.

Audience: L1 messages are for the steward editing the file, so they name the
field and say what to change (research §R-4).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from ..contracts.metric import Metric
from ..loader.load import CatalogLoadError, load_file
from .result import Severity, Subject, ValidationFinding, ValidationLayer, ValidationReport

__all__ = ["IDENTIFIER_PATTERN", "validate_file", "validate_tree"]

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

_IDENTIFIER_FIELD = {
    "source": "id",
    "dimension": "id",
    "comparability": "id",
    "glossary": "id",
    "metric": "name",
    "catalog_policy": "policy_id",
}

#: Kinds whose approved contract path is ``{id}.yaml``
#: (catalog-file-contracts §4.4). Only these can be checked for filename /
#: identifier agreement. ``catalog_policy`` is deliberately absent: its contract
#: fixes the canonical filename ``catalog-policy.yaml``, which no valid
#: ``Identifier`` can ever equal, so the rule would refuse the one path the
#: contract mandates.
_FILENAME_IS_IDENTIFIER = frozenset({"source", "dimension", "comparability", "glossary", "metric"})


def _finding(
    rule: str,
    kind: str,
    identifier: str,
    message: str,
    *,
    field_path: str | None = None,
    file: Path | None = None,
    severity: Severity = Severity.ERROR,
) -> ValidationFinding:
    return ValidationFinding(
        layer=ValidationLayer.L1_SCHEMA,
        rule=rule,
        severity=severity,
        subject=Subject(
            kind=kind,
            identifier=identifier,
            field_path=field_path,
            file=str(file) if file else None,
        ),
        message=message,
    )


def validate_file(path: Path) -> tuple[ValidationFinding, ...]:
    """L1 findings for one authored file. Empty means well-formed."""
    try:
        kind, model = load_file(path)
    except CatalogLoadError as exc:
        return (_finding("load_refused", "file", path.name, f"{path.name}: {exc}", file=path),)
    except ValidationError as exc:
        findings: list[ValidationFinding] = []
        for error in exc.errors():
            field_path = ".".join(str(p) for p in error["loc"]) or "<root>"
            findings.append(
                _finding(
                    "schema_violation",
                    "file",
                    path.name,
                    f"{path.name}: field {field_path} — {error['msg']}",
                    field_path=field_path,
                    file=path,
                )
            )
        return tuple(findings)

    findings = []
    identifier_field = _IDENTIFIER_FIELD.get(kind)
    identifier = str(getattr(model, identifier_field)) if identifier_field else kind

    # Defence in depth: the `Identifier` type normally rejects this during model
    # validation, so this rule fires only for a contract whose identifier is not
    # `Identifier`-typed. Kept so the rule does not disappear if one ever is.
    if identifier_field and not IDENTIFIER_PATTERN.match(identifier):
        findings.append(
            _finding(
                "identifier_casing",
                kind,
                identifier,
                f"{kind} {identifier!r} is not English snake_case; identifiers are "
                "machine-facing and must match ^[a-z][a-z0-9_]*$ (FR-053)",
                field_path=identifier_field,
                file=path,
            )
        )

    if kind in _FILENAME_IS_IDENTIFIER and path.stem != identifier:
        findings.append(
            _finding(
                "filename_mismatch",
                kind,
                identifier,
                f"{kind} {identifier!r} is defined in {path.name}; the file name and the "
                "identifier must agree so a rename cannot half-happen",
                field_path=identifier_field,
                file=path,
            )
        )

    if isinstance(model, Metric):
        findings.extend(_metric_version_findings(model, path))

    return tuple(findings)


def _metric_version_findings(model: Metric, path: Path) -> Iterable[ValidationFinding]:
    """Version-numbering rules, reported against the metric rather than the block."""
    numbers = [v.version for v in model.versions]
    if sorted(numbers) != list(range(1, len(numbers) + 1)):
        yield _finding(
            "version_numbers_not_sequential",
            "metric",
            model.name,
            f"metric {model.name!r} has version numbers {numbers}; they must start at 1 "
            "and increase by one so a gap cannot hide a deleted definition (FR-069)",
            field_path="versions",
            file=path,
        )
    open_versions = [v.version for v in model.versions if v.effective_to is None]
    if len(open_versions) > 1:
        yield _finding(
            "multiple_open_versions",
            "metric",
            model.name,
            f"metric {model.name!r} has more than one open version {open_versions}; "
            "as-of resolution would be ambiguous for current dates",
            field_path="versions",
            file=path,
        )


def validate_tree(root: Path, *, pattern: str = "**/*.yaml") -> ValidationReport:
    """L1 over every authored file under ``root``.

    Every discovered file is validated. A file that cannot be loaded produces a
    finding rather than being skipped — a silently skipped file is an ungoverned
    metric that nobody notices.
    """
    if not root.is_dir():
        return ValidationReport.from_findings(
            [
                _finding(
                    "root_missing",
                    "tree",
                    str(root),
                    f"{root} is not a directory; nothing was validated",
                )
            ]
        )
    findings: list[ValidationFinding] = []
    for path in sorted(root.glob(pattern)):
        findings.extend(validate_file(path))
    return ValidationReport.from_findings(findings)
