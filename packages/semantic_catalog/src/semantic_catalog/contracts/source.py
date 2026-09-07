"""Source contracts — T010.

A source declares where data comes from and how current it promises to be
(FR-021, data-model §2.2). Two fields carry more weight than their size suggests:

``reporting_timezone``
    The source's **native** zone, preserved verbatim and never normalised to the
    canonical business zone (research §R-10). Answers are cut in
    ``America/Sao_Paulo``; this field is what lets the offset be disclosed
    instead of silently absorbed.

``delay_tolerance``
    **Required, with no default.** It is a business decision (D-1) because it
    sets how often the system refuses to answer. A global fallback would let a
    source inherit a tolerance nobody agreed to, so a missing value makes the
    source non-compliant rather than tolerant.

``restatements`` are recorded here and are **not** definition changes: the
figures moved under an unchanged definition (FR-028). They produce a new data
revision (T072), never a new metric version.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictInt, field_validator, model_validator

from ._base import CatalogModel, Identifier, IsoDuration, PtBrContent, PtBrText

__all__ = [
    "Outage",
    "Restatement",
    "Source",
    "SourceContent",
    "SourceType",
]


class SourceType(StrEnum):
    PRODUCT_TELEMETRY = "product_telemetry"
    APP_STORE = "app_store"


class Outage(CatalogModel):
    """A window in which the source produced no usable data."""

    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    reason: PtBrText

    model_config = CatalogModel.model_config | {"populate_by_name": True}

    @model_validator(mode="after")
    def _ordered(self) -> Outage:
        if self.to_date < self.from_date:
            raise ValueError(f"outage ends {self.to_date} before it starts {self.from_date}")
        return self


class Restatement(CatalogModel):
    """The source republished figures for a past window (FR-028).

    Distinct from a definition change: the meaning did not move, the numbers did.
    """

    restated_at: date
    affects_from: date
    affects_to: date
    reason: PtBrText

    @model_validator(mode="after")
    def _ordered(self) -> Restatement:
        if self.affects_to < self.affects_from:
            raise ValueError(
                f"restatement affects_to {self.affects_to} precedes affects_from "
                f"{self.affects_from}"
            )
        return self


class SourceContent(PtBrContent):
    """pt-BR human-facing content for a source."""

    label: PtBrText
    limitations: tuple[PtBrText, ...] = ()


class Source(CatalogModel):
    """``semantic/sources/{id}.yaml``."""

    catalog_schema_version: StrictInt
    kind: Literal["source"]

    id: Identifier
    type: SourceType
    product: Identifier
    platform: Identifier
    store: Identifier | None = Field(
        default=None,
        description="Present only for app-store sources (A-7).",
    )

    reporting_timezone: str = Field(
        description="Native IANA zone, preserved verbatim and never normalised.",
    )
    earliest_available_date: date
    expected_refresh_interval: IsoDuration
    delay_tolerance: IsoDuration = Field(
        description="REQUIRED, no default. Business input D-1; sets how often the system refuses.",
    )

    owner: Identifier
    content: SourceContent
    outages: tuple[Outage, ...] = ()
    restatements: tuple[Restatement, ...] = ()

    @field_validator("reporting_timezone")
    @classmethod
    def _known_iana_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"{value!r} is not a known IANA time zone; a fixed UTC offset is not accepted "
                "because it cannot represent daylight-saving transitions (research §R-10)"
            ) from exc
        return value

    @model_validator(mode="after")
    def _store_only_for_store_sources(self) -> Source:
        if self.type is SourceType.APP_STORE and self.store is None:
            raise ValueError(f"app_store source {self.id!r} must declare a store")
        if self.type is SourceType.PRODUCT_TELEMETRY and self.store is not None:
            raise ValueError(f"product_telemetry source {self.id!r} must not declare a store (A-7)")
        return self
