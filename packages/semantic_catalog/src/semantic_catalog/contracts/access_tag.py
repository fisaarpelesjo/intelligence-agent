"""Access-tag registry — T017 (FR-073).

The authorisation gate needs a defined input domain. Without a registry, every
implementer invents a tag vocabulary and "authorised" means whatever the caller
passed in.

Every resolution failure denies. In particular, a **deprecated tag is denied even
when it declares a replacement** — the replacement is evaluated on its own
merits, never auto-granted, because inheriting authorisation from a retired tag
is how stale access survives a cleanup.

Tags are never created, inferred, expanded or translated by a language model.
Both the authorisation gate and the pending-visibility gate accept registry
identifiers only: never free text, never a synonym, never a near match.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from ._base import CatalogModel, Identifier, PtBrContent, PtBrText

__all__ = ["AccessTag", "AccessTagContent", "AccessTagRegistry", "PrincipalType", "TagDenial"]


class PrincipalType(StrEnum):
    """Humans and service principals warrant different treatment."""

    USER = "user"
    SERVICE_PRINCIPAL = "service_principal"


class TagDenial(StrEnum):
    """Why a tag failed to authorise. Maps to a reason code at the gate (T053)."""

    UNKNOWN = "unknown"
    NOT_YET_EFFECTIVE = "not_yet_effective"
    DEPRECATED = "deprecated"
    PRINCIPAL_TYPE_MISMATCH = "principal_type_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"


class AccessTagContent(PtBrContent):
    label: PtBrText
    description: PtBrText


class AccessTag(CatalogModel):
    """One authorisation tag."""

    id: Identifier
    owner_role: Identifier
    effective_from: date
    allowed_principal_types: tuple[PrincipalType, ...] = Field(min_length=1)
    allowed_authorization_scopes: tuple[Identifier, ...] = Field(min_length=1)
    content: AccessTagContent
    deprecated_from: date | None = None
    replacement_tag: Identifier | None = None

    @model_validator(mode="after")
    def _deprecation_is_dated_and_ordered(self) -> AccessTag:
        if self.replacement_tag is not None and self.deprecated_from is None:
            raise ValueError(
                f"tag {self.id!r} names a replacement but is not deprecated; "
                "a replacement without a deprecation date has no effect"
            )
        if self.deprecated_from is not None and self.deprecated_from < self.effective_from:
            raise ValueError(
                f"tag {self.id!r} is deprecated {self.deprecated_from} before it became effective "
                f"{self.effective_from}"
            )
        return self


class AccessTagRegistry(CatalogModel):
    """``semantic/governance/access-tags.yaml`` — deny-by-default."""

    catalog_schema_version: StrictInt
    kind: Literal["access_tags"]
    tags: tuple[AccessTag, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_and_resolvable(self) -> AccessTagRegistry:
        ids = [tag.id for tag in self.tags]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate access tag id")
        known = set(ids)
        for tag in self.tags:
            if tag.replacement_tag is not None and tag.replacement_tag not in known:
                raise ValueError(
                    f"tag {tag.id!r} names replacement {tag.replacement_tag!r}, which is not in "
                    "the registry; a dangling replacement leaves no valid path"
                )
        return self

    def get(self, tag_id: str) -> AccessTag | None:
        return next((tag for tag in self.tags if tag.id == tag_id), None)

    def authorize(
        self,
        tag_id: str,
        *,
        principal_type: PrincipalType,
        authorization_scope: str,
        on: date,
    ) -> TagDenial | None:
        """``None`` authorises; a :class:`TagDenial` refuses.

        Deny-by-default at every branch. A deprecated tag denies even with a
        valid replacement — the replacement must be presented and evaluated on
        its own, not inherited.
        """
        tag = self.get(tag_id)
        if tag is None:
            return TagDenial.UNKNOWN
        if on < tag.effective_from:
            return TagDenial.NOT_YET_EFFECTIVE
        if tag.deprecated_from is not None and on >= tag.deprecated_from:
            return TagDenial.DEPRECATED
        if principal_type not in tag.allowed_principal_types:
            return TagDenial.PRINCIPAL_TYPE_MISMATCH
        if authorization_scope not in tag.allowed_authorization_scopes:
            return TagDenial.SCOPE_MISMATCH
        return None
