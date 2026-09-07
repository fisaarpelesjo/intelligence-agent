"""Result provenance — T094 (FR-042, FR-045, FR-072; SC-005).

All ten elements are **required**. Incomplete provenance is an abstention, not a
warning: a result is never returned with a partial provenance block.

The reason is that provenance is what makes a figure checkable later. A number
without its contributing sources, resolved versions and data revisions cannot be
reproduced, disputed or superseded — it is just a number someone once saw. So
"we could not establish where this came from" and "here it is anyway" must not
be combinable, and the model makes them uncombinable by requiring every element
at construction.

``policy_version`` is here for a specific reason (`FR-072`): when suppression or
a limit changes behaviour, the change must be attributable to the **policy**
rather than to the catalog. Without the policy version on the result, a figure
that appeared last month and is withheld today looks like a catalog change.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from ._base import ContractViolation, QueryModel
from .provenance import CostProvenance
from .reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

__all__ = ["REQUIRED_ELEMENTS", "ResultProvenance", "SourceUpdate"]

#: The ten elements `FR-042` enumerates. Named so the coverage assertion is
#: about the requirement rather than about whatever fields happen to exist.
REQUIRED_ELEMENTS = (
    "contributing_sources",
    "resolved_metric_versions",
    "data_revisions",
    "data_as_of",
    "source_updates",
    "dimensional_coverage",
    "limitations",
    "cost",
    "execution_identifiers",
    "policy_version",
)


#: The subset that carries no meaning when empty. The other three are listed in
#: `is_complete`, with the reason each may legitimately be empty.
_NON_EMPTY_ELEMENTS = (
    "contributing_sources",
    "resolved_metric_versions",
    "source_updates",
    "execution_identifiers",
    "policy_version",
)


class SourceUpdate(QueryModel):
    """When one contributing source was last updated."""

    source_id: str = Field(min_length=1)
    last_updated_at: datetime


class ResultProvenance(QueryModel):
    """Where a figure came from. Every element required, no exceptions."""

    contributing_sources: tuple[str, ...] = Field(min_length=1)
    resolved_metric_versions: tuple[str, ...] = Field(min_length=1)
    data_revisions: tuple[str, ...]
    data_as_of: datetime
    source_updates: tuple[SourceUpdate, ...] = Field(min_length=1)
    dimensional_coverage: tuple[str, ...]
    limitations: tuple[str, ...]
    cost: CostProvenance
    execution_identifiers: tuple[str, ...] = Field(min_length=1)
    #: `FR-072`: attributes a behaviour change to the policy, not the catalog.
    policy_version: str = Field(min_length=1)
    catalog_release_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _every_contributing_source_reports_an_update(self) -> ResultProvenance:
        """A source that contributed but reported no update time is unexplained.

        Its freshness cannot be checked, so the figure cannot be judged — which
        is the abstention case, not a returnable result with a gap in it.
        """
        described = {update.source_id for update in self.source_updates}
        missing = set(self.contributing_sources) - described
        if missing:
            raise ContractViolation(
                AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
                "a contributing source reports no last-update time; provenance is incomplete",
            )
        return self

    @classmethod
    def required_element_names(cls) -> tuple[str, ...]:
        """The ten elements, for the coverage assertion."""
        return REQUIRED_ELEMENTS

    def is_complete(self) -> bool:
        """Whether every required element is *present*.

        Presence, not non-emptiness. Three of the ten may legitimately be empty
        and saying so is complete information, not a gap:

        * ``data_revisions`` — no source supplied a stable revision, which is
          what makes the decision `reproducibility: limited`;
        * ``dimensional_coverage`` — no breakdown was requested;
        * ``limitations`` — the figure carries no caveat.

        Treating those as incomplete would make an unqualified result look
        unprovenanced, and would push someone toward inventing a placeholder
        caveat to satisfy the check.
        """
        return all(getattr(self, name, None) is not None for name in REQUIRED_ELEMENTS) and all(
            getattr(self, name) for name in _NON_EMPTY_ELEMENTS
        )
