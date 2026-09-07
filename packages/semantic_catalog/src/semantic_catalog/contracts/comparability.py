"""Comparability rules — T012.

Metrics that look alike across sources frequently are not (FR-029 - FR-031).
Store-reported downloads and device-reported installs are near-synonyms in
conversation and different events in reality.

**Deny-by-default is the point.** The absence of a rule for a cross-source pair
is not permission — Gate 6 (T082) requires an explicit ``combinable`` relation
before summing across sources. A rule that merely *permits* still has to be
authored deliberately.

Every non-permissive relation carries a business-language reason, because
"refused" without "why" sends the reader to build their own number.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import StrictInt, model_validator

from ._base import CatalogModel, Identifier, PtBrContent, PtBrText

__all__ = ["ComparabilityContent", "ComparabilityRule", "Relation", "RuleSubject"]


class Relation(StrEnum):
    """Closed set. Anything not declared is denied by Gate 6."""

    COMBINABLE = "combinable"
    COMPARABLE_WITH_CAVEAT = "comparable_with_caveat"
    NOT_COMPARABLE = "not_comparable"


class RuleSubject(StrEnum):
    METRIC_PAIR = "metric_pair"
    SOURCE_PAIR = "source_pair"


class ComparabilityContent(PtBrContent):
    reason: PtBrText | None = None
    caveat: PtBrText | None = None


class ComparabilityRule(CatalogModel):
    """``semantic/comparability/{id}.yaml``."""

    catalog_schema_version: StrictInt
    kind: Literal["comparability"]

    id: Identifier
    subject: RuleSubject
    left: Identifier
    right: Identifier
    relation: Relation
    content: ComparabilityContent

    @model_validator(mode="after")
    def _distinct_operands(self) -> ComparabilityRule:
        if self.left == self.right:
            raise ValueError(f"comparability rule {self.id!r} relates {self.left!r} to itself")
        return self

    @model_validator(mode="after")
    def _reason_and_caveat_required_where_they_matter(self) -> ComparabilityRule:
        if self.relation is not Relation.COMBINABLE and not self.content.reason:
            raise ValueError(
                f"rule {self.id!r} declares {self.relation.value!r} and must state a pt-BR reason "
                "(FR-030): a refusal without a reason sends the reader elsewhere"
            )
        if self.relation is Relation.COMPARABLE_WITH_CAVEAT and not self.content.caveat:
            raise ValueError(
                f"rule {self.id!r} is comparable_with_caveat and must state the caveat (FR-031)"
            )
        if self.relation is Relation.COMBINABLE and self.content.caveat:
            raise ValueError(f"rule {self.id!r} is combinable; a caveat would never be surfaced")
        return self
