"""Provenance passthrough — T129 (FR-037, FR-072; SC-041).

**Both sides unmerged; incomplete provenance abstains.**

`002` produces a ten-element ``ResultProvenance`` per execution. This module
carries them, one entry per side, and does two things only: check that each is
complete, and refuse to combine them.

## Why merging is the failure

A comparison draws on two executions with two freshness facts, two revision sets,
two cost records and possibly two source lists. A merged provenance has to pick:
the earlier update time or the later, the union of sources or the intersection.
Every choice produces a plausible record that describes neither execution — and
the reader cannot tell, because a merged provenance looks exactly like a real
one.

So there is no merge function here, and no place to put one. The answer contract
declares ``provenance`` as a tuple with one entry per side, and this module
returns a tuple.

## Incomplete provenance abstains rather than warns

`FR-037` is explicit. An answer whose freshness, revisions or contributing
sources are partly unknown is not an answer with a caveat — it is a figure whose
basis nobody can check, and a warning beside it invites the reader to use it
anyway.

`002` already refuses to construct an incomplete ``ResultProvenance``: every
element is required and three are ``min_length=1``. The check here is not a second
opinion about those — it is about the elements a contract can hold *empty*, which
construction cannot catch: a data-revision list nobody filled, a limitation
tuple that lost its contents in transit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from analytics_query.contracts.result_provenance import ResultProvenance

__all__ = [
    "REQUIRED_ELEMENTS",
    "assert_provenance_is_complete",
    "carry_provenance",
]

#: The ten elements `002` declares, named so this module's completeness check is
#: readable beside `002`'s contract rather than derived from it silently.
REQUIRED_ELEMENTS: tuple[str, ...] = (
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

#: Elements that must be **non-empty** to release an answer. ``dimensional_coverage``
#: and ``limitations`` are legitimately empty — a request with no dimensions has
#: no coverage to state, and an unqualified answer has no limitations — so
#: requiring them would refuse correct answers. ``data_revisions`` is required
#: because a figure standing on no revision is one nobody can reproduce.
NON_EMPTY_ELEMENTS: tuple[str, ...] = (
    "contributing_sources",
    "resolved_metric_versions",
    "data_revisions",
    "source_updates",
    "execution_identifiers",
)


def assert_provenance_is_complete(provenance: ResultProvenance) -> None:
    """Refuse an answer whose basis is partly unknown. **Abstain, never warn.**

    The refusal names no element. Which part of the provenance was missing
    describes the shape of an execution the caller is not receiving, and on a
    comparison it would describe a side they may not have access to.
    """
    for element in REQUIRED_ELEMENTS:
        if getattr(provenance, element, None) is None:
            raise ContractViolation(
                InterpretationReasonCode.DISCLOSURE_WOULD_RECONSTRUCT,
                "the answer's provenance is incomplete; the answer abstains rather than warns",
            )

    for element in NON_EMPTY_ELEMENTS:
        if not getattr(provenance, element):
            raise ContractViolation(
                InterpretationReasonCode.DISCLOSURE_WOULD_RECONSTRUCT,
                "the answer's provenance is incomplete; the answer abstains rather than warns",
            )

    if not provenance.catalog_release_id or not provenance.policy_version:
        raise ContractViolation(
            InterpretationReasonCode.DISCLOSURE_WOULD_RECONSTRUCT,
            "the answer's provenance is incomplete; the answer abstains rather than warns",
        )


def carry_provenance(*sides: ResultProvenance) -> tuple[ResultProvenance, ...]:
    """One entry per side, checked and **unmerged**.

    Returns the same objects, in the order given. Not copies, not a summary, not
    a combined record — the order is the caller's because it is the side order,
    and re-sorting here would detach a provenance from the side it describes.

    At least one is required: an answer standing on no execution has no basis to
    state, and the contract's ``min_length=1`` says so too.
    """
    if not sides:
        raise ContractViolation(
            InterpretationReasonCode.DISCLOSURE_WOULD_RECONSTRUCT,
            "an answer states the provenance of at least one execution",
        )

    for side in sides:
        assert_provenance_is_complete(side)
    return tuple(sides)


def freshness_of(provenance: ResultProvenance) -> tuple[tuple[str, str], ...]:
    """Per-source freshness, as ``(source_id, last_updated_at)`` pairs.

    Per-source rather than a single timestamp, because a result drawing on two
    sources has two freshness facts and collapsing them would let the fresher one
    speak for the staler. `FR-032`'s freshness element resolves through exactly
    this field — ``provenance[].source_updates[].last_updated_at`` — and a helper
    that returned one instant would be the collapse the contract avoided.
    """
    return tuple(
        (update.source_id, update.last_updated_at.isoformat())
        for update in provenance.source_updates
    )
