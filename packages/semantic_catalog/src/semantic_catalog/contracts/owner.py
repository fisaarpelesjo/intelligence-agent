"""Owner registry — T014.

Owners are **stable teams or roles, never individuals** (FR-032, data-model
§2.1). Three consequences follow, and all three are the reason for the rule:

* no personal data enters the catalog (FR-041, NG-10);
* a person leaving does not orphan a metric;
* accountability survives reorganisation.

``review_group`` links an owner to the CODEOWNERS group that approves its
changes. The registry is the ownership **record**; CODEOWNERS is routing and
merge enforcement only (research §R-7). L2 validation (T026) checks that every
``review_group`` exists in CODEOWNERS so the two cannot diverge.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from ._base import CatalogModel, Identifier, PtBrText

__all__ = ["Owner", "OwnerKind", "OwnerRegistry"]


class OwnerKind(StrEnum):
    """An owner is a team or a role. There is deliberately no ``person``."""

    TEAM = "team"
    ROLE = "role"


# Shapes that indicate an individual rather than a team or role. This is a
# tripwire for the obvious mistake, not identity detection: a reviewer remains
# responsible for judging whether an entry names a person.
_INDIVIDUAL_MARKERS = (
    re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+"),  # email address
    re.compile(r"^\s*(mr|mrs|ms|dr|prof)\b\.?\s", re.IGNORECASE),  # personal title
)


class Owner(CatalogModel):
    """One accountable team or role."""

    id: Identifier = Field(description="English identifier referenced by metrics and dimensions.")
    name: PtBrText = Field(description="Team or role name.")
    kind: OwnerKind = Field(description="team or role — never an individual.")
    review_group: PtBrText = Field(
        description="CODEOWNERS group that approves this owner's changes; validated at L2.",
    )

    @field_validator("name", "review_group")
    @classmethod
    def _reject_individuals(cls, value: str) -> str:
        for marker in _INDIVIDUAL_MARKERS:
            if marker.search(value):
                raise ValueError(
                    "owners are teams or roles, never individuals; "
                    f"{value!r} looks like a person (FR-032, NG-10)"
                )
        return value


class OwnerRegistry(CatalogModel):
    """``semantic/owners.yaml`` — the ownership record."""

    catalog_schema_version: StrictInt
    kind: Literal["owners"]
    owners: tuple[Owner, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> OwnerRegistry:
        seen: set[str] = set()
        for owner in self.owners:
            if owner.id in seen:
                raise ValueError(f"duplicate owner id {owner.id!r}")
            seen.add(owner.id)
        return self

    def resolve(self, owner_id: str) -> Owner | None:
        """Return the owner, or ``None``. Callers must fail closed on ``None``."""
        return next((o for o in self.owners if o.id == owner_id), None)
