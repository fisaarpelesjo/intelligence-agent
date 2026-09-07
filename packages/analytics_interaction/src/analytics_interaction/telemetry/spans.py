"""Telemetry spans over the sixteen steps — T140 (FR-053; SC-026, SC-051).

**Telemetry cannot become the channel that leaks what audit forbids.**

That sentence is the task's own evidence line and the whole reason this module
exists as a declaration rather than as an integration. A span attribute is the
easiest place in a system to put "just enough context to debug this" — and the
context that helps most is the question text, the value returned, the filter that
matched. Every one of those is on the audit denylist, and a span carrying it
would leak precisely what the audit contract removed.

So the same content scan guards both (`T139`). Not a similar scan, not a scan
with a shared denylist: **the same one**, so a value that could not enter an
audit event cannot enter a span either.

## Attributes are a closed set

:data:`SPAN_ATTRIBUTES` enumerates what a span may carry — governed identifiers,
the resolved period, the declared language, the catalog release, the policy and
vocabulary versions, the route taken, the rounds consumed and the terminal
status. A caller passing anything else refuses.

An allowlist rather than a denylist, because the failure mode is *additive*:
somebody adds an attribute that seems harmless, and a denylist that never heard
of it lets it through. An allowlist refuses by default and the addition has to be
argued for.

## Cardinality is bounded by construction

Every permitted attribute is a governed identifier, a closed enum, a date or a
bounded integer. None is free text, none is a principal reference, none is an
exception message, and none varies per request in an unbounded way.

That matters beyond tidiness: a metrics backend keyed on a high-cardinality label
degrades in a way nobody notices until it falls over, and the labels most likely
to do it — question text, principal id, error string — are exactly the ones the
denylist already forbids. Bounded cardinality here is the same property as
value-freedom, seen from the operations side.

## No SDK, no exporter, no network

This module declares span shapes and validates attributes. It imports no
OpenTelemetry package, opens no socket, starts no background thread, holds no
buffer and writes no file. A deployment supplies an exporter; this feature
supplies a contract for what may cross it.

`T141`'s scan asserts the absence, because an exporter added later would be a
network egress path nobody reviewed — and it would carry exactly the attributes
this module spent its effort bounding.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

__all__ = [
    "SPAN_ATTRIBUTES",
    "SPAN_STEPS",
    "InterpretationSpan",
    "SpanStep",
    "span_for",
]


class SpanStep(StrEnum):
    """The sixteen sequence steps, named for the step.

    Named rather than numbered so a span is legible in a trace viewer without a
    lookup table — ``resolve_terms`` says what happened; ``step_7`` needs the
    plan open beside it.

    Declaration order is sequence order. Nothing here enforces that the steps
    *run* in this order — that is the sequence's own job — but a trace whose span
    names sort into the wrong order would be a trace nobody could read.
    """

    PARSE_INTAKE = "parse_intake"
    RESOLVE_AUTHORIZATION = "resolve_authorization"
    DECLARE_LANGUAGE = "declare_language"
    APPLY_GOVERNED_BOUND = "apply_governed_bound"
    SCREEN_UNTRUSTED_TEXT = "screen_untrusted_text"
    DISCOVER_CANDIDATES = "discover_candidates"
    RESOLVE_TERMS = "resolve_terms"
    NARROW_CANDIDATES = "narrow_candidates"
    ASSEMBLE_INTENT = "assemble_intent"
    DERIVE_IDENTITY = "derive_identity"
    ROUTE_COMPARISON = "route_comparison"
    OBTAIN_VERDICT = "obtain_verdict"
    BUILD_REQUEST = "build_request"
    SUBMIT_REQUEST = "submit_request"
    COMPUTE_COMPARISON = "compute_comparison"
    ASSEMBLE_ANSWER = "assemble_answer"


#: The sixteen, in sequence order.
SPAN_STEPS: tuple[SpanStep, ...] = tuple(SpanStep)

#: The closed set of attribute names a span may carry. An **allowlist**: the
#: failure mode is additive, and a denylist that never heard of a new attribute
#: lets it through.
#:
#: Every one is a governed identifier, a closed enum, a date or a bounded
#: integer. None is free text, a principal reference or an exception message.
SPAN_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "correlation_id",
        "metric_ids",
        "dimension_ids",
        "source_ids",
        "period_start",
        "period_end",
        "language",
        "catalog_release",
        "policy_version",
        "vocabulary_version",
        "route",
        "rounds_consumed",
        "status",
    }
)


@dataclass(frozen=True, slots=True)
class InterpretationSpan:
    """One span: the step it covers, the correlation it belongs to, its attributes.

    Frozen, because a span whose attributes could be added to after validation
    would make the allowlist a suggestion. The whole guarantee is that what is
    checked is what is exported.

    There is deliberately no ``events``, no ``exception``, no ``message`` and no
    ``links``. An exception message is unbounded free text produced by code
    nobody reviewed for disclosure, and it is the single likeliest way a filter
    value or a question span reaches a trace.
    """

    step: SpanStep
    correlation_id: str
    attributes: tuple[tuple[str, str], ...]


def span_for(
    step: SpanStep, *, correlation_id: str, attributes: Mapping[str, str]
) -> InterpretationSpan:
    """Build a span, or refuse. **Allowlisted attributes only.**

    Attributes arrive as strings already: a caller that had to stringify a value
    to pass it has already made the decision this function would otherwise be
    asked to make silently, and the refusal below catches the name rather than
    trusting the type.

    Sorted by name, so two identical spans serialise identically — `SC-028`'s
    reproducibility claim reaches telemetry too, and an unordered attribute map
    would make two equal traces compare unequal.

    ``correlation_id`` is required and is the only identifier that always
    appears. It is generated at step 1 and carries no principal information, so
    it joins a trace to an audit trail without joining either to a person.
    """
    unknown = sorted(set(attributes) - SPAN_ATTRIBUTES)
    if unknown:
        # The detail names the rejected keys and nothing else. Naming the
        # *values* would put into a refusal exactly what the refusal exists to
        # keep out of a span.
        raise ContractViolation(
            InterpretationReasonCode.INTAKE_MALFORMED,
            f"a span may not carry the attributes {unknown}; the permitted set is closed",
        )

    if not correlation_id:
        raise ContractViolation(
            InterpretationReasonCode.INTAKE_MALFORMED,
            "a span carries the correlation it belongs to",
        )

    return InterpretationSpan(
        step=step,
        correlation_id=correlation_id,
        attributes=tuple(sorted(attributes.items())),
    )
