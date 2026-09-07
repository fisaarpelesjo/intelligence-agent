"""Interpretation-layer reason codes — T021 (FR-020, FR-025; SC-015).

`001`'s ``ReasonCode`` is a **closed** enum of 41 codes with a frozen outcome map.
`002` hit the same wall and answered it with a **disjoint** second namespace of 25
execution-layer codes rather than editing an approved, merged artifact (ADR 0004).

This feature inherits both walls and adds no third precedent — it follows the one
already set (ADR 0011).

**The ownership rule is narrow.** A code here may only describe a condition
*neither* upstream layer can observe. Metric existence, lifecycle, authorization,
combination, grain, comparability, coverage, freshness, period, retention and
versioning stay with `001`; malformed requests, cost, rows, timeout, dry run,
shape, suppression and warehouse availability stay with `002`. An upstream
refusal is **passed through verbatim** and never restated in this vocabulary
(`FR-021`) — a consumer must not be able to tell which layer refused from message
style.

``Outcome`` is imported rather than redeclared. Three enums naming the same three
outcome classes would eventually disagree.

Mirrors `contracts/reason-codes.md` §3 exactly, whose enumerated tables are
authoritative.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from semantic_catalog.contracts.reason_codes import Outcome

__all__ = [
    "REASON_CODE_OUTCOME",
    "InterpretationReasonCode",
    "Outcome",
    "codes_with_outcome",
    "outcome_for",
]


class InterpretationReasonCode(StrEnum):
    """32 codes: 30 DENY, 1 ALLOW_WITH_CAVEAT, 1 ALLOW.

    Adding a code is a minor change; changing a code's meaning is breaking,
    exactly as upstream.
    """

    # --- intake (8) ----------------------------------------------------------
    INTAKE_MALFORMED = "INTAKE_MALFORMED"
    QUESTION_EMPTY = "QUESTION_EMPTY"
    #: Over the contract's structural ceiling. **Names no governed limit** — the
    #: principal is not yet proven entitled to be told one
    #: (`intake-contract.md` §6). Its governed twin below may name it.
    QUESTION_EXCEEDS_STRUCTURAL_LIMIT = "QUESTION_EXCEEDS_STRUCTURAL_LIMIT"
    QUESTION_EXCEEDS_GOVERNED_LIMIT = "QUESTION_EXCEEDS_GOVERNED_LIMIT"
    QUESTION_CONTENT_NOT_TEXTUAL = "QUESTION_CONTENT_NOT_TEXTUAL"
    #: Never detected, inferred or scored. The absence of a detector is the
    #: mechanism (`FR-100`).
    LANGUAGE_NOT_DECLARED = "LANGUAGE_NOT_DECLARED"
    LANGUAGE_NOT_SUPPORTED = "LANGUAGE_NOT_SUPPORTED"
    QUESTION_NOT_ANALYTICAL = "QUESTION_NOT_ANALYTICAL"

    # --- authorization context (1) -------------------------------------------
    #: Deliberately **one** code, not four. Distinguishing *which* part of the
    #: context failed to resolve would tell an unauthenticated caller something
    #: about the identity system's shape.
    AUTHORIZATION_CONTEXT_UNRESOLVABLE = "AUTHORIZATION_CONTEXT_UNRESOLVABLE"

    # --- governed content (2) ------------------------------------------------
    #: Separate from the policy code because vocabulary and policy are separately
    #: owned and separately approved (`DEP-3`, `DEP-4`). Merging them would let a
    #: vocabulary addition ship without privacy review.
    INTERPRETATION_VOCABULARY_UNRESOLVABLE = "INTERPRETATION_VOCABULARY_UNRESOLVABLE"
    #: Covers all six `D-19` fields under one code, so no configuration can run
    #: with some of them and not others.
    INTERPRETATION_POLICY_UNRESOLVABLE = "INTERPRETATION_POLICY_UNRESOLVABLE"

    # --- term resolution (4) -------------------------------------------------
    TERM_NOT_GOVERNED = "TERM_NOT_GOVERNED"
    INTENT_AMBIGUOUS = "INTENT_AMBIGUOUS"
    SLOT_ROLE_AMBIGUOUS = "SLOT_ROLE_AMBIGUOUS"
    #: Distinct from ``TERM_NOT_GOVERNED``: the caller named an identifier, not a
    #: concept.
    IDENTIFIER_FABRICATED = "IDENTIFIER_FABRICATED"

    # --- period (2) ----------------------------------------------------------
    PERIOD_EXPRESSION_NOT_GOVERNED = "PERIOD_EXPRESSION_NOT_GOVERNED"
    PERIOD_CONVENTION_UNDECLARED = "PERIOD_CONVENTION_UNDECLARED"

    # --- clarification (7) ---------------------------------------------------
    #: The one code here that is not a failure. Classified ``DENY`` nonetheless,
    #: because no answer was produced and no request was constructed — treating
    #: it as permissive would let a caller read "clarification" as "partial
    #: success".
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    #: No seal key (`D-21`), so no tamper-evident contract can be issued. The
    #: question refuses instead of clarifying.
    CLARIFICATION_UNAVAILABLE = "CLARIFICATION_UNAVAILABLE"
    CLARIFICATION_EXHAUSTED = "CLARIFICATION_EXHAUSTED"
    CLARIFICATION_EXPIRED = "CLARIFICATION_EXPIRED"
    CLARIFICATION_TAMPERED = "CLARIFICATION_TAMPERED"
    CLARIFICATION_VERSION_UNKNOWN = "CLARIFICATION_VERSION_UNKNOWN"
    CLARIFICATION_CONTEXT_MISMATCH = "CLARIFICATION_CONTEXT_MISMATCH"

    # --- calculation and safety (3) ------------------------------------------
    CALCULATION_NOT_SUPPORTED = "CALCULATION_NOT_SUPPORTED"
    #: The content is never echoed back — not in the response, the logs, the
    #: traces or the audit event (`FR-045`).
    INSTRUCTION_INJECTION_REFUSED = "INSTRUCTION_INJECTION_REFUSED"
    DISCLOSURE_WOULD_RECONSTRUCT = "DISCLOSURE_WOULD_RECONSTRUCT"

    # --- comparison and surfaces (3) -----------------------------------------
    #: Absence of a route is never permission.
    COMPARISON_NOT_ROUTABLE = "COMPARISON_NOT_ROUTABLE"
    #: The **whole** comparison refuses; neither side is returned.
    COMPARISON_SIDE_INVALID = "COMPARISON_SIDE_INVALID"
    #: Model narrowing was required and `D-20` is undeclared. Ambiguity clarifies
    #: or refuses; it never waits.
    MODEL_SURFACE_UNAVAILABLE = "MODEL_SURFACE_UNAVAILABLE"

    # --- permitted (2) -------------------------------------------------------
    QUESTION_ANSWERED = "QUESTION_ANSWERED"
    QUESTION_ANSWERED_WITH_CAVEAT = "QUESTION_ANSWERED_WITH_CAVEAT"


_OUTCOMES: dict[InterpretationReasonCode, Outcome] = {
    InterpretationReasonCode.INTAKE_MALFORMED: Outcome.DENY,
    InterpretationReasonCode.QUESTION_EMPTY: Outcome.DENY,
    InterpretationReasonCode.QUESTION_EXCEEDS_STRUCTURAL_LIMIT: Outcome.DENY,
    InterpretationReasonCode.QUESTION_EXCEEDS_GOVERNED_LIMIT: Outcome.DENY,
    InterpretationReasonCode.QUESTION_CONTENT_NOT_TEXTUAL: Outcome.DENY,
    InterpretationReasonCode.LANGUAGE_NOT_DECLARED: Outcome.DENY,
    InterpretationReasonCode.LANGUAGE_NOT_SUPPORTED: Outcome.DENY,
    InterpretationReasonCode.QUESTION_NOT_ANALYTICAL: Outcome.DENY,
    InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE: Outcome.DENY,
    InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE: Outcome.DENY,
    InterpretationReasonCode.INTERPRETATION_POLICY_UNRESOLVABLE: Outcome.DENY,
    InterpretationReasonCode.TERM_NOT_GOVERNED: Outcome.DENY,
    InterpretationReasonCode.INTENT_AMBIGUOUS: Outcome.DENY,
    InterpretationReasonCode.SLOT_ROLE_AMBIGUOUS: Outcome.DENY,
    InterpretationReasonCode.IDENTIFIER_FABRICATED: Outcome.DENY,
    InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED: Outcome.DENY,
    InterpretationReasonCode.PERIOD_CONVENTION_UNDECLARED: Outcome.DENY,
    InterpretationReasonCode.CLARIFICATION_REQUIRED: Outcome.DENY,
    InterpretationReasonCode.CLARIFICATION_UNAVAILABLE: Outcome.DENY,
    InterpretationReasonCode.CLARIFICATION_EXHAUSTED: Outcome.DENY,
    InterpretationReasonCode.CLARIFICATION_EXPIRED: Outcome.DENY,
    InterpretationReasonCode.CLARIFICATION_TAMPERED: Outcome.DENY,
    InterpretationReasonCode.CLARIFICATION_VERSION_UNKNOWN: Outcome.DENY,
    InterpretationReasonCode.CLARIFICATION_CONTEXT_MISMATCH: Outcome.DENY,
    InterpretationReasonCode.CALCULATION_NOT_SUPPORTED: Outcome.DENY,
    InterpretationReasonCode.INSTRUCTION_INJECTION_REFUSED: Outcome.DENY,
    InterpretationReasonCode.DISCLOSURE_WOULD_RECONSTRUCT: Outcome.DENY,
    InterpretationReasonCode.COMPARISON_NOT_ROUTABLE: Outcome.DENY,
    InterpretationReasonCode.COMPARISON_SIDE_INVALID: Outcome.DENY,
    InterpretationReasonCode.MODEL_SURFACE_UNAVAILABLE: Outcome.DENY,
    InterpretationReasonCode.QUESTION_ANSWERED_WITH_CAVEAT: Outcome.ALLOW_WITH_CAVEAT,
    InterpretationReasonCode.QUESTION_ANSWERED: Outcome.ALLOW,
}

#: Read-only code-to-outcome mapping. Every member appears exactly once, and
#: every outcome class is inhabited — mirroring `001`'s rule that a declared
#: outcome no code can express is a state nothing may emit or audit.
REASON_CODE_OUTCOME: Mapping[InterpretationReasonCode, Outcome] = MappingProxyType(_OUTCOMES)


def outcome_for(code: InterpretationReasonCode) -> Outcome:
    """Outcome class for ``code``.

    Raises rather than defaulting: an unmapped code means the enum and the table
    have drifted, and guessing an outcome would let a denial read as an allow.
    """
    try:
        return REASON_CODE_OUTCOME[code]
    except KeyError as exc:  # pragma: no cover - guarded by the contract test
        raise ValueError(f"reason code {code!r} has no declared outcome class") from exc


def codes_with_outcome(outcome: Outcome) -> tuple[InterpretationReasonCode, ...]:
    """All codes classified as ``outcome``, in declaration order."""
    return tuple(code for code in InterpretationReasonCode if REASON_CODE_OUTCOME[code] is outcome)
