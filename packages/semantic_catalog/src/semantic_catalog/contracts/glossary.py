"""Business glossary — T012 (FR-019).

Metric and dimension descriptions reference business concepts. The glossary is
where those concepts are defined once, in pt-BR, with an owner — so a
description can point at a definition instead of restating it slightly
differently each time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import StrictInt

from ._base import CatalogModel, Identifier, PtBrContent, PtBrText
from .dimension import Synonym

__all__ = ["GlossaryContent", "GlossaryTerm"]


class GlossaryContent(PtBrContent):
    term: PtBrText
    definition: PtBrText


class GlossaryTerm(CatalogModel):
    """``semantic/glossary/{id}.yaml``."""

    catalog_schema_version: StrictInt
    kind: Literal["glossary"]

    id: Identifier
    owner: Identifier
    content: GlossaryContent
    synonyms: tuple[Synonym, ...] = ()
