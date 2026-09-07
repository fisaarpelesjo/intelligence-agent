"""The narrowing-only model port — T082 (FR-041, FR-046, FR-047; SC-054).

`FR-047` is this module's because the payload types below *are* the governance: what may
cross to a model-facing surface is bounded by what ``DelimitedQuestionData`` and
``CandidateSet`` can hold, and neither can hold a value.

**Absent by default, and that is the shipped state.** `D-20` is undeclared, the
gate in `compliance/gates.py` refuses to construct an implementation, and
interpretation is deterministic-only. A question deterministic resolution leaves
ambiguous **clarifies or refuses** — it never waits for a model that is not there.

ADR 0013 gives the port three properties. None is a policy or a validation; each
is a property of the type signature or of the sequence position.

## 1. Candidate-narrowing only

    narrow(question: DelimitedQuestionData, candidates: CandidateSet)
        -> CandidateSelection | None

The return type is a **selection from a set the port was given**. It carries an
``identifier``, and validation refuses any identifier the request did not
contain — so an unresolved term stays unresolved regardless of what a provider
returns. `FR-041` is enforced by the signature plus one total check, not by a
validator that could be incomplete.

Generate-then-validate was considered and rejected: it makes the governed
vocabulary a *filter on model output* rather than the *source of it*, and a
filter that is ever incomplete admits an ungoverned identifier. Narrowing
inverts the dependency — the vocabulary is the input, and nothing outside it can
come back.

## 2. Structurally value-free

No parameter type can express a result, a row, an aggregate, a filter value or a
cost figure. Every field below is a governed identifier, a governed pointer, a
bounded enum or a version string. Combined with the port's sequence position —
step 8, before any execution — **no result exists in the process while the port
is reachable**.

Verified by a static **reachability** check rather than a redaction test.
Redaction proves a value was removed; reachability proves one was never present,
and only the second survives a future edit nobody reviewed.

The alternative — letting the model see aggregated evidence, as Constitution IV
would permit — was rejected. This feature narrates nothing and assembles answers
from governed content, so it needs no number on the model side. An unused egress
path is still an egress path.

## 3. Untrusted output, validated deterministically

A provider's response is **data**, exactly as the question is. It cannot create
a filter, a period, a calculation, an operator, a metric, a dimension or a
source; it cannot override deterministic canonical resolution; and prose,
confidence scores, tool calls and extra fields have nowhere to land because the
selection type declares none of them and forbids extras.

## No provider

This module declares a ``Protocol`` and nothing else. No SDK, no HTTP client, no
endpoint, no model name, no token or cost limit, no credential lookup and no
default construction. A provider, if one is ever approved, arrives behind its own
ADR in its own confined adapter subpackage — as `002`'s ADR 0007 did for
BigQuery.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field, model_validator

from ..compliance.gates import require_model_participation
from ..compliance.readiness import ReadinessRecord
from ..contracts._base import ContractViolation, InteractionModel, LocalizedRef
from ..contracts.intent import SlotKind
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "CandidateOption",
    "CandidateSelection",
    "CandidateSet",
    "DelimitedQuestionData",
    "InterpretationModelPort",
    "narrow_candidates",
    "validate_selection",
]


class DelimitedQuestionData(InteractionModel):
    """The question, as **isolated non-instructional data**.

    Constitution IV requires untrusted text to be isolated before it can reach a
    prompt. ``text`` is screened `D-19` content by the time it arrives — step 5
    precedes step 8 — and it is carried as a *field*, never concatenated into
    governance instructions.

    ``delimiter`` names the boundary an adapter must wrap the text in. It is
    carried explicitly rather than left to the adapter so that "the question was
    delimited" is a property of the request the port received, checkable without
    reading whichever provider client eventually exists.

    No field here can carry a value, a row or a query: there are two, and both
    are text the caller already sent.
    """

    text: str = Field(min_length=1)
    delimiter: str = Field(min_length=1, default="<<<QUESTION>>>")


class CandidateOption(InteractionModel):
    """One already-governed, already-authorised candidate.

    Produced by deterministic resolution against `001`'s access-filtered
    surface, so a candidate the caller may not see never reaches this type — the
    filtering happened at read time and is not repeated here.

    ``distinguishing`` is a ``LocalizedRef`` into governed content: a pointer,
    never a built string and never a span of the question. It is the only
    human-facing metadata the contract allows across, and it is governed wording
    somebody approved.
    """

    identifier: str = Field(min_length=1)
    slot: SlotKind
    distinguishing: LocalizedRef


class CandidateSet(InteractionModel):
    """The closed set the model may select from, and the context for doing so.

    ``options`` is what deterministic resolution already found. The model ranks
    within it and cannot add to it.

    The version fields travel because a selection made under one catalog release
    and one vocabulary version is not a selection made under another — and
    because an audit trail needs to say which.
    """

    slot: SlotKind
    options: tuple[CandidateOption, ...] = Field(min_length=2)
    catalog_release: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    vocabulary_version: str = Field(min_length=1)
    contract_version: int = Field(gt=0, default=1)

    @model_validator(mode="after")
    def _every_option_belongs_to_the_slot(self) -> CandidateSet:
        """A set mixing slots would let a metric be selected as a source.

        Fewer than two options is refused by ``min_length`` above: narrowing a
        set of one is not narrowing, and calling a provider for it would be cost
        incurred for no decision.
        """
        wrong = [option.identifier for option in self.options if option.slot is not self.slot]
        if wrong:
            raise ValueError(f"options do not belong to slot {self.slot.value}: {wrong}")
        return self

    @model_validator(mode="after")
    def _identifiers_are_unique(self) -> CandidateSet:
        identifiers = [option.identifier for option in self.options]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("candidate identifiers must be unique within a set")
        return self

    @property
    def identifiers(self) -> frozenset[str]:
        return frozenset(option.identifier for option in self.options)


class CandidateSelection(InteractionModel):
    """One identifier, chosen from the set the port was given.

    **One field.** No confidence, no score, no rationale, no alternatives, no
    tool call, no free text — a provider that returns any of them finds nowhere
    to put them, because the model forbids extras and declares none.

    That absence is deliberate beyond tidiness. A confidence score would invite a
    threshold, a threshold would be a tuned number nobody governed, and
    answerability would start depending on it — which is exactly what `FR-041`
    forbids. A rationale would be free-form narration entering answer
    construction through the side door.
    """

    identifier: str = Field(min_length=1)


@runtime_checkable
class InterpretationModelPort(Protocol):
    """The provider-neutral narrowing interface. **No implementation ships.**

    One method, two value-free parameters, and a return type that cannot name an
    identifier it was not given. ``None`` means "no selection" and is a complete,
    permitted answer — the deterministic path then treats the term as it would
    have without the model, so a provider declining to choose never changes what
    is reachable.

    An implementation is supplied by a deployment **only once `D-20` is
    declared with evidence**. This package ships none: a default provider would
    be a default answer to a question nobody approved asking.
    """

    def narrow(
        self, question: DelimitedQuestionData, candidates: CandidateSet
    ) -> CandidateSelection | None:
        """Rank within ``candidates``. Never introduce an identifier."""
        ...


def validate_selection(selection: object, candidates: CandidateSet) -> CandidateSelection | None:
    """Validate a provider's answer deterministically. Untrusted until it passes.

    ``None`` passes through: declining to choose is permitted and means the
    deterministic outcome stands.

    Everything else must be a ``CandidateSelection`` whose identifier is **in the
    set the request carried**. A foreign, fabricated, empty or malformed answer
    refuses rather than being coerced or ignored — silently ignoring it would
    make a provider's misbehaviour invisible, and the whole point of the port is
    that its output cannot widen anything.

    Duplicate and contradictory selections have nowhere to arise: the type holds
    exactly one identifier, and the set's identifiers are unique by construction.
    """
    if selection is None:
        return None

    if not isinstance(selection, CandidateSelection):
        raise ContractViolation(
            InterpretationReasonCode.MODEL_SURFACE_UNAVAILABLE,
            "the model surface returned something that is not a candidate selection",
        )

    if selection.identifier not in candidates.identifiers:
        raise ContractViolation(
            InterpretationReasonCode.MODEL_SURFACE_UNAVAILABLE,
            "the model surface selected an identifier the request did not contain",
        )

    return selection


def narrow_candidates(
    question: DelimitedQuestionData,
    candidates: CandidateSet,
    *,
    port: InterpretationModelPort | None,
    records: tuple[ReadinessRecord, ...] | None = None,
) -> CandidateSelection | None:
    """Narrow through the model port, or refuse. **Gated before any provider call.**

    The order is the security property:

    1. ``require_model_participation`` — refuses ``MODEL_SURFACE_UNAVAILABLE``
       while `D-20` is undeclared, or declared without evidence. **No provider is
       touched.** In the shipped repository every call stops here;
    2. the port must have been supplied. A missing collaborator is never a pass;
    3. a provider exception, timeout or malformed response fails closed —
       whatever went wrong, the model did not choose;
    4. the answer is validated against the request's own candidate set.

    Nothing is cached: not the question, not the candidates, not the response. A
    cached selection would be a stored answer to a question somebody else asked.
    """
    require_model_participation(records=records)

    if port is None:
        raise ContractViolation(
            InterpretationReasonCode.MODEL_SURFACE_UNAVAILABLE,
            "no model port was supplied",
        )

    try:
        answer = port.narrow(question, candidates)
    except ContractViolation:
        raise
    except Exception as exc:
        # Deliberately broad. A provider can fail in ways this package cannot
        # enumerate — timeout, transport, quota, a client raising on a shape it
        # did not expect — and every one of them means the same thing: no
        # selection was made.
        raise ContractViolation(
            InterpretationReasonCode.MODEL_SURFACE_UNAVAILABLE,
            "the model surface failed to produce a selection",
        ) from exc

    return validate_selection(answer, candidates)
