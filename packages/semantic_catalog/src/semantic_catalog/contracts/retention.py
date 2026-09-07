"""Retention contract — T013 (FR-044 - FR-047).

Three separate metrics, not one parameterised metric: ``retention_rate_d1``,
``retention_rate_d7`` and ``retention_rate_d30`` do not share maturity,
availability or limitations, so one contract cannot carry all three.

**Classic exact-day retention only.** A user returning on day 6 and day 8 is not
retained at D7. That reads as wrong to anyone expecting rolling retention, which
is exactly why rolling is named in ``exclusions`` rather than silently absent.

The fields that matter most here are the ones that are **required but ship
unset**: ``cohort_timezone``, ``eligible_event`` and ``identity_rule`` are
business inputs (D-8, D-9). FR-048 forbids inferring, defaulting or
approximating them. ``None`` therefore means *not yet authored*, and
:meth:`RetentionContract.unset_required_fields` reports exactly which — it never
substitutes a value. The consequence is deliberate: all three retention metrics
are ``pending`` at launch by construction, which is specified behaviour rather
than an incomplete build.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictInt, field_validator, model_validator

from ._base import CatalogModel, PtBrText

__all__ = ["CohortAssignment", "RetentionContract", "RetentionStyle"]

#: Fields that are contractually required but are authored externally (D-8, D-9).
#: They are nullable in the model so an unauthored metric can still be *loaded*
#: and reported as pending; they are never given a default.
EXTERNALLY_AUTHORED_FIELDS: tuple[str, ...] = (
    "cohort_timezone",
    "eligible_event",
    "identity_rule",
)


class RetentionStyle(StrEnum):
    """Fixed. Rolling retention is forbidden (FR-045)."""

    EXACT_DAY = "exact_day"


class CohortAssignment(StrEnum):
    """Fixed. Cohort membership is the user's first eligible activity (FR-046)."""

    FIRST_ELIGIBLE_ACTIVITY = "first_eligible_activity"


class RetentionContract(CatalogModel):
    """Required when ``grain_family == cohort``."""

    window_days: Literal[1, 7, 30] = Field(
        description="One metric per window (FR-044, A-16); not a parameter of a shared metric.",
    )
    retention_style: RetentionStyle
    cohort_assignment: CohortAssignment

    cohort_timezone: str | None = Field(
        default=None,
        description="REQUIRED, authored externally (D-9). Never defaulted to the canonical zone.",
    )
    eligible_event: PtBrText | None = Field(
        default=None,
        description="REQUIRED, authored externally (D-8). Never inferred (FR-048).",
    )
    identity_rule: PtBrText | None = Field(
        default=None,
        description="REQUIRED, authored externally (D-8). Never inferred (FR-048).",
    )

    numerator: PtBrText
    denominator: PtBrText
    min_maturity_days: StrictInt = Field(
        ge=1,
        description="Defaults to window_days when authored (A-15); a longer value may be declared.",
    )

    @field_validator("cohort_timezone")
    @classmethod
    def _known_zone_when_present(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"{value!r} is not a known IANA time zone") from exc
        return value

    @model_validator(mode="after")
    def _maturity_covers_window(self) -> RetentionContract:
        if self.min_maturity_days < self.window_days:
            raise ValueError(
                f"min_maturity_days {self.min_maturity_days} is shorter than the "
                f"D{self.window_days} window; a figure would be reported before the cohort "
                "could produce it (A-15)"
            )
        return self

    def unset_required_fields(self) -> tuple[str, ...]:
        """Names of externally-authored fields still unset.

        Returns **names only, never draft values** (FR-018). A non-empty result
        makes the metric incomplete under FR-002 and therefore pending.
        """
        return tuple(name for name in EXTERNALLY_AUTHORED_FIELDS if getattr(self, name) is None)

    @property
    def is_publishable(self) -> bool:
        """False while any externally-authored field is unset — no fallback."""
        return not self.unset_required_fields()
