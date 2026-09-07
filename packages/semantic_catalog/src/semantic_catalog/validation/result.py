"""Deny-by-default validation result — T027 (FR-012, SC-004).

Every finding names the thing that is wrong. There is no way to construct a
result without a subject, because SC-004 requires zero generic refusals: "the
catalog is invalid" tells a steward nothing, while "metric `active_users`
version 2 overlaps version 1" tells them exactly what to edit.

The default is refusal. :meth:`ValidationReport.is_valid` is true only when the
report holds no ``ERROR`` finding, so an empty or unpopulated report from a
validator that crashed reads as *valid only if it genuinely found nothing*, and
every construction path forces a subject.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ..contracts._base import CatalogModel

__all__ = [
    "Severity",
    "Subject",
    "ValidationFinding",
    "ValidationLayer",
    "ValidationReport",
]


class ValidationLayer(StrEnum):
    """Which layer raised the finding (research §R-4)."""

    L1_SCHEMA = "L1"
    L2_REFERENTIAL = "L2"
    L3_RECONCILIATION = "L3"
    L4_POLICY = "L4"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Subject(CatalogModel):
    """What a finding is about. Never optional."""

    kind: str = Field(min_length=1, description="Contract kind, e.g. metric, source.")
    identifier: str = Field(min_length=1, description="The entity's own identifier.")
    field_path: str | None = Field(
        default=None,
        description="Dotted path to the offending field, when the finding is field-level.",
    )
    file: str | None = None

    def describe(self) -> str:
        base = f"{self.kind} {self.identifier!r}"
        return f"{base} field {self.field_path}" if self.field_path else base


class ValidationFinding(CatalogModel):
    """One violation, always attributed to a subject."""

    layer: ValidationLayer
    rule: str = Field(min_length=1, description="Stable rule name, e.g. version_ranges_overlap.")
    severity: Severity = Severity.ERROR
    subject: Subject
    message: str = Field(min_length=1)

    @model_validator(mode="after")
    def _message_names_the_subject(self) -> Self:
        if self.subject.identifier not in self.message:
            raise ValueError(
                f"finding {self.rule!r} does not name its subject "
                f"{self.subject.identifier!r} in the message; generic refusals are "
                "forbidden (FR-012, SC-004)"
            )
        return self


class ValidationReport(CatalogModel):
    """Findings from one or more layers. Invalid unless proven otherwise."""

    findings: tuple[ValidationFinding, ...] = ()

    @classmethod
    def from_findings(cls, findings: Iterable[ValidationFinding]) -> ValidationReport:
        return cls(findings=tuple(findings))

    @property
    def errors(self) -> tuple[ValidationFinding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationFinding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)

    def is_valid(self) -> bool:
        """True only when no ``ERROR`` finding is present."""
        return not self.errors

    def by_layer(self, layer: ValidationLayer) -> tuple[ValidationFinding, ...]:
        return tuple(f for f in self.findings if f.layer is layer)

    def merge(self, other: ValidationReport) -> ValidationReport:
        return ValidationReport(findings=self.findings + other.findings)

    def render(self) -> Sequence[str]:
        """One line per finding, each naming its subject and rule."""
        return [
            f"[{f.layer.value}/{f.severity.value}] {f.rule}: {f.message}" for f in self.findings
        ]
