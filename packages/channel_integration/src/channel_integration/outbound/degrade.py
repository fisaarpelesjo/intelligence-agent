"""Structural degradation, from the matrix only — T072 (ADR 0022; FR-051, FR-110; SC-021).

A degradation is a change of **structure** that a channel's declared capabilities require: a table
rendered as a list where the matrix declares no table support, emphasis dropped where the channel
has none. Every instance must be a member of the `D-28` capability matrix, and every instance must
be **disclosed** using the matrix's own pt-BR wording.

**What is not a degradation.** Shortening, summarising, rewording, rounding, rescaling, re-
unitising, localising, eliding and omitting are **content changes**, and they are forbidden
outright rather than permitted-with-disclosure. This module therefore has no operation that could
perform one: there is no function here that takes a string and returns a shorter one. The absence
is the mechanism (`FR-110`).

**An invented degradation refuses.** A degradation whose name the matrix does not declare produces
``CHANNEL_RESPONSE_NOT_REPRESENTABLE`` and the response is withheld. That is the difference
between a governed adaptation and a channel quietly deciding what it may do to a governed answer.

While `D-28` is undeclared the matrix does not resolve at all, so nothing is degradable and nothing
renders — the lock ADR 0022 exists to hold (`FR-103`, `SC-059`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from ..contracts.presentation import Degradation
from .withhold import NotRepresentable

__all__ = [
    "FORBIDDEN_CONTENT_OPERATIONS",
    "declared_degradations",
    "disclosure_for",
    "require_declared_degradation",
]

#: Named so a reader and a scanner see the same list, and so `T094` can assert that no member of it
#: appears as an operation in this package. These are the words a content change hides behind.
FORBIDDEN_CONTENT_OPERATIONS: tuple[str, ...] = (
    "truncate",
    "shorten",
    "summarise",
    "summarize",
    "abbreviate",
    "reword",
    "rephrase",
    "paraphrase",
    "round",
    "rescale",
    "reunit",
    "localise",
    "localize",
    "translate",
    "elide",
    "omit",
    "sample",
    "trim",
    "clip",
)


def declared_degradations(capability: Mapping[str, Any]) -> tuple[str, ...]:
    """The degradation names this channel's matrix entry declares.

    Refuses rather than defaulting to none: an entry whose ``permitted_degradations`` is not a
    list is
    a malformed governed document, and treating it as "no degradations permitted" would silently
    turn a
    content defect into a stricter-looking rule.
    """
    declared: object = capability.get("permitted_degradations")
    if not isinstance(declared, Sequence) or isinstance(declared, str | bytes):
        raise NotRepresentable("the capability entry declares no permitted_degradations list")
    names: list[str] = []
    for entry in cast("Sequence[object]", declared):
        if not isinstance(entry, str) or not entry.strip():
            raise NotRepresentable("a permitted degradation is not a named string")
        names.append(entry)
    return tuple(names)


def disclosure_for(capability: Mapping[str, Any], name: str) -> str:
    """The governed pt-BR disclosure code for ``name``, or refuse.

    A degradation the matrix declares but for which it carries no disclosure wording cannot be
    applied:
    applying it would be a silent structural change, which `FR-051` forbids as firmly as an
    invented one.
    """
    wording: object = capability.get("disclosure_wording")
    if not isinstance(wording, Mapping):
        raise NotRepresentable("the capability entry declares no disclosure_wording mapping")
    disclosure: object = cast("Mapping[str, Any]", wording).get(name)
    if not isinstance(disclosure, str) or not disclosure.strip():
        raise NotRepresentable(f"no governed disclosure wording for degradation {name}")
    return disclosure


def require_declared_degradation(
    capability: Mapping[str, Any], name: str, capability_ref: str
) -> Degradation:
    """One matrix-declared, disclosed degradation, or refuse.

    ``capability_ref`` is carried on the result so an auditor can see which matrix entry
    authorised the
    adaptation, rather than having to trust that one did.
    """
    if name not in declared_degradations(capability):
        raise NotRepresentable(f"degradation {name} is not declared by the capability matrix")
    return Degradation(
        capability_ref=capability_ref, disclosure_code=disclosure_for(capability, name)
    )
