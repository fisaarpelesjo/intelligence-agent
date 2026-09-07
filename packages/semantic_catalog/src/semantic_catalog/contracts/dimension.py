"""Dimension contracts — T011.

A dimension declares an axis of analysis and, critically, **where it applies** (FR-007, FR-010).
Absence from ``source_applicability`` means *not applicable* — it is not an oversight to be filled
in later. Application version has no meaning for the website, and store has none for product
telemetry (A-7); the catalog says so by omission, and Gate 4 (T054) refuses the combination naming
both the dimension and the source.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from ._base import CatalogModel, Identifier, PtBrContent, PtBrText

__all__ = ["Dimension", "DimensionContent", "SourceApplicability", "Synonym"]


class Synonym(CatalogModel):
    """A pt-BR term that resolves to an English canonical identifier (FR-057)."""

    text: PtBrText
    kind: Literal["formal", "informal", "abbreviation"]


class SourceApplicability(CatalogModel):
    """This dimension exists for this source, from this date."""

    source: Identifier
    available_from: date
    available_to: date | None = None

    @model_validator(mode="after")
    def _ordered(self) -> SourceApplicability:
        if self.available_to is not None and self.available_to < self.available_from:
            raise ValueError(
                f"available_to {self.available_to} precedes available_from {self.available_from}"
            )
        return self


class DimensionContent(PtBrContent):
    label: PtBrText
    description: PtBrText


class Dimension(CatalogModel):
    """``semantic/dimensions/{id}.yaml``."""

    catalog_schema_version: StrictInt
    kind: Literal["dimension"]

    id: Identifier
    owner: Identifier
    #: Access tag; gates whether this dimension may be disclosed. **Optional, and absence denies**
    #: (ADR 0029).
    #:
    #: `Metric.access` is required, because every authored metric carries one. This one stays
    #: optional, and the reason changed on 2026-08-19 rather than disappearing.
    #:
    #: It used to be optional because no authored dimension carried a tag at all, and because
    #: `standard` described itself as covering *metrics*, so reusing it here would have silently
    #: widened a governed class. The owner closed both halves in one instruction: the registry
    #: definition in ``semantic/governance/access-tags.yaml`` was corrected to state the class it
    #: actually governs — product metrics **and** semantic dimensions, and explicitly not an
    #: individual identifier or any other object — and the six authored axes now carry `standard`
    #: under that corrected definition. So the tag is no longer being stretched; it is being applied
    #: to a class it names.
    #:
    #: What keeps the field optional is the property, not the data. Absence has to remain a case the
    #: gate can **deny**, because that is what makes deny-by-default observable rather than
    #: structural. Requiring the field would refuse an untagged dimension at load time, which is a
    #: stricter rule than the disclosure contract needs and would move the guarantee out of the gate
    #: and into the loader.
    #:
    #: So absence is not "unknown" and not "to be filled in later" — it is **denied**, exactly as an
    #: absent registry denies in `search.api.authorize`. A dimension becomes disclosable when its
    #: owner authors a tag the registry admits for it, and not before.
    access: Identifier | None = Field(
        default=None,
        description=(
            "Access tag gating disclosure of this dimension. Absent means denied (ADR 0029); no "
            "default is authored here."
        ),
    )
    permitted_values: tuple[PtBrText, ...] | Literal["open"] = Field(
        description="Explicit value list, or 'open' for high-cardinality axes such as app_version.",
    )
    content: DimensionContent
    source_applicability: tuple[SourceApplicability, ...] = Field(
        default=(),
        description="Absence of a source means NOT APPLICABLE, never 'unknown' (FR-010).",
    )
    synonyms: tuple[Synonym, ...] = ()

    def applies_to(self, source_id: str) -> bool:
        """Deny-by-default: unknown source means not applicable."""
        return any(entry.source == source_id for entry in self.source_applicability)
