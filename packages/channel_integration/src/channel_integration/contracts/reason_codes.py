"""Channel-layer reason codes — T012 (ADR 0018; FR-045; SC-060).

`001`'s ``ReasonCode`` is a **closed** enum of 41 codes with a frozen outcome map.
`002` hit that wall and answered it with a disjoint second namespace of 25 codes
(ADR 0004); `003` hit it again and added a third of 32 (ADR 0011). This feature
observes conditions none of the three can express — a signature that does not
validate, an external identity with no governed binding, a response no channel
representation can carry intact — and adds a **fourth disjoint namespace of 31
codes** (ADR 0018). It adds no precedent; it follows the one already set.

**The ownership rule is narrow.** A code here may only describe a condition *none*
of the three upstream layers can observe. `001` cannot know a channel exists;
`002` cannot know a signature exists; `003` cannot know a message arrived. An
upstream refusal is **passed through verbatim** and never restated in this
vocabulary (`FR-045`) — a recipient must not be able to tell which of the four
layers refused from message style.

**Three deliberate collapses**, each for a disclosure reason (ADR 0018):

* every signature failure mode is ``CHANNEL_SIGNATURE_INVALID`` — distinguishing
  them tells an attacker which half of the scheme they got right;
* every binding failure is ``CHANNEL_IDENTITY_UNMAPPED`` — distinguishing them
  describes the registry's shape, and "revoked" confirms the identity once existed;
* a missing envelope field is ``CHANNEL_ENVELOPE_INCOMPLETE`` — a field-by-field
  code set would let a caller enumerate the contract before authenticating.

The collapse is in the **emitted** code only. The distinguishing detail travels in
the audit event's ``detail_class``, readable by an operator and never returned to a
sender.

``Outcome`` is imported rather than redeclared. Four enums naming the same three
outcome classes would eventually disagree. It is the one upstream production import
this module needs, and it is a published contract of `001` rather than an internal.

Mirrors ``contracts/reason-codes.md`` §2 exactly, whose enumerated tables are
authoritative.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from semantic_catalog.contracts.reason_codes import Outcome

__all__ = [
    "CHANNEL_REASON_CODE_OUTCOME",
    "ChannelReasonCode",
    "Outcome",
    "channel_codes_with_outcome",
    "channel_outcome_for",
]


class ChannelReasonCode(StrEnum):
    """31 codes: 28 DENY, 2 ALLOW, 1 ALLOW_WITH_CAVEAT.

    Adding a code is a **new decision**, not a routine addition (ADR 0018
    § Acceptance); changing a code's meaning is breaking, exactly as upstream.
    """

    # --- authenticity and integrity (5) --------------------------------------
    CHANNEL_PAYLOAD_MALFORMED = "CHANNEL_PAYLOAD_MALFORMED"
    #: Over the structural ceiling on size, nesting depth or field count.
    #: **Names no governed limit** — the sender is unauthenticated at every step
    #: of this feature, so no refusal of it may name a `D-26` number.
    CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT = "CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT"
    #: Absent, malformed, computed over another body, produced with retired
    #: material, or valid for a different channel. **Deliberately one code.**
    CHANNEL_SIGNATURE_INVALID = "CHANNEL_SIGNATURE_INVALID"
    CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE = "CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE"
    #: Verification itself cannot run. Never bypassed on the grounds that the
    #: content looks legitimate.
    CHANNEL_VERIFICATION_UNAVAILABLE = "CHANNEL_VERIFICATION_UNAVAILABLE"

    # --- envelope and message kind (5) ---------------------------------------
    #: **One code, not nine.** A field-by-field set would let a caller enumerate
    #: the envelope contract before authenticating.
    CHANNEL_ENVELOPE_INCOMPLETE = "CHANNEL_ENVELOPE_INCOMPLETE"
    CHANNEL_ENVELOPE_FIELD_UNKNOWN = "CHANNEL_ENVELOPE_FIELD_UNKNOWN"
    #: Names the kind. Nothing accompanying or derived from a non-textual message
    #: becomes a question (`FR-108`).
    CHANNEL_MESSAGE_KIND_UNSUPPORTED = "CHANNEL_MESSAGE_KIND_UNSUPPORTED"
    CHANNEL_TEXT_NOT_USABLE = "CHANNEL_TEXT_NOT_USABLE"
    #: The governed rule set cannot decide whether an element is decoration or
    #: content. Refuses rather than choosing (`FR-039`).
    CHANNEL_NORMALISATION_AMBIGUOUS = "CHANNEL_NORMALISATION_AMBIGUOUS"

    # --- identity, tenant and isolation (3) ----------------------------------
    #: No binding, revoked, expired, ambiguous, or resolving to several
    #: principals. **Deliberately one code.**
    CHANNEL_IDENTITY_UNMAPPED = "CHANNEL_IDENTITY_UNMAPPED"
    CHANNEL_TENANT_MISMATCH = "CHANNEL_TENANT_MISMATCH"
    #: A scoped identifier presented by a different principal, tenant or channel.
    #: Discloses nothing about the referenced item's existence.
    CHANNEL_SCOPE_MISMATCH = "CHANNEL_SCOPE_MISMATCH"

    # --- configuration and governed policy (8) -------------------------------
    CHANNEL_NOT_CONFIGURED = "CHANNEL_NOT_CONFIGURED"
    CHANNEL_CREDENTIAL_UNAVAILABLE = "CHANNEL_CREDENTIAL_UNAVAILABLE"
    #: `D-26`. **One code for all seven values**, so no configuration runs with a
    #: rate limit but no replay tolerance.
    CHANNEL_TRANSPORT_POLICY_UNRESOLVABLE = "CHANNEL_TRANSPORT_POLICY_UNRESOLVABLE"
    CHANNEL_IDENTITY_POLICY_UNRESOLVABLE = "CHANNEL_IDENTITY_POLICY_UNRESOLVABLE"
    CHANNEL_RENDERING_CAPABILITY_UNRESOLVABLE = "CHANNEL_RENDERING_CAPABILITY_UNRESOLVABLE"
    CHANNEL_METADATA_POLICY_UNRESOLVABLE = "CHANNEL_METADATA_POLICY_UNRESOLVABLE"
    #: `D-31` pseudonymisation material absent, so no compliant audit event is
    #: constructible. `FR-083` forbids delivering what cannot be recorded.
    CHANNEL_AUDIT_UNAVAILABLE = "CHANNEL_AUDIT_UNAVAILABLE"
    #: The composed interaction entry point is not constructible — authorized by
    #: ADR 0017 but not yet shipped and validated by Phase D0. No locally composed
    #: substitute exists (`FR-104`).
    INTERACTION_BOUNDARY_UNAVAILABLE = "INTERACTION_BOUNDARY_UNAVAILABLE"

    # --- transport flow (5) --------------------------------------------------
    CHANNEL_RATE_LIMIT_EXCEEDED = "CHANNEL_RATE_LIMIT_EXCEEDED"
    CHANNEL_DELIVERY_FAILED = "CHANNEL_DELIVERY_FAILED"
    CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED = "CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED"
    #: Timed out **after** the provider may have accepted. A recorded third state:
    #: never reported as delivered, never resent in a way that could
    #: double-deliver (ADR 0021).
    CHANNEL_DELIVERY_INDETERMINATE = "CHANNEL_DELIVERY_INDETERMINATE"
    #: A recognised redelivery inside the governed window and the same process.
    #: Classified DENY because no new governed outcome was produced.
    CHANNEL_MESSAGE_DUPLICATE = "CHANNEL_MESSAGE_DUPLICATE"

    # --- rendering and preservation (2) --------------------------------------
    #: Neither structural degradation nor continuation can carry the payload
    #: intact. Withheld, never truncated (ADR 0022).
    CHANNEL_RESPONSE_NOT_REPRESENTABLE = "CHANNEL_RESPONSE_NOT_REPRESENTABLE"
    #: A preservation check failed: a governed string diverged, the caveat count
    #: did not match, or the leak scan tripped. Nothing is sent.
    CHANNEL_OUTBOUND_WITHHELD = "CHANNEL_OUTBOUND_WITHHELD"

    # --- permitted (3) -------------------------------------------------------
    CHANNEL_MESSAGE_ACCEPTED = "CHANNEL_MESSAGE_ACCEPTED"
    CHANNEL_RESPONSE_DELIVERED = "CHANNEL_RESPONSE_DELIVERED"
    #: The payload carried upstream caveats, or a disclosed structural degradation
    #: was applied. The caveats are the payload's, carried byte-identical.
    CHANNEL_RESPONSE_DELIVERED_WITH_CAVEAT = "CHANNEL_RESPONSE_DELIVERED_WITH_CAVEAT"


_OUTCOMES: dict[ChannelReasonCode, Outcome] = {
    ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED: Outcome.DENY,
    ChannelReasonCode.CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT: Outcome.DENY,
    ChannelReasonCode.CHANNEL_SIGNATURE_INVALID: Outcome.DENY,
    ChannelReasonCode.CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN: Outcome.DENY,
    ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED: Outcome.DENY,
    ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS: Outcome.DENY,
    ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED: Outcome.DENY,
    ChannelReasonCode.CHANNEL_TENANT_MISMATCH: Outcome.DENY,
    ChannelReasonCode.CHANNEL_SCOPE_MISMATCH: Outcome.DENY,
    ChannelReasonCode.CHANNEL_NOT_CONFIGURED: Outcome.DENY,
    ChannelReasonCode.CHANNEL_CREDENTIAL_UNAVAILABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_TRANSPORT_POLICY_UNRESOLVABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_IDENTITY_POLICY_UNRESOLVABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_RENDERING_CAPABILITY_UNRESOLVABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_METADATA_POLICY_UNRESOLVABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_AUDIT_UNAVAILABLE: Outcome.DENY,
    ChannelReasonCode.INTERACTION_BOUNDARY_UNAVAILABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_RATE_LIMIT_EXCEEDED: Outcome.DENY,
    ChannelReasonCode.CHANNEL_DELIVERY_FAILED: Outcome.DENY,
    ChannelReasonCode.CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED: Outcome.DENY,
    ChannelReasonCode.CHANNEL_DELIVERY_INDETERMINATE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_MESSAGE_DUPLICATE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_RESPONSE_NOT_REPRESENTABLE: Outcome.DENY,
    ChannelReasonCode.CHANNEL_OUTBOUND_WITHHELD: Outcome.DENY,
    ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED: Outcome.ALLOW,
    ChannelReasonCode.CHANNEL_RESPONSE_DELIVERED: Outcome.ALLOW,
    ChannelReasonCode.CHANNEL_RESPONSE_DELIVERED_WITH_CAVEAT: Outcome.ALLOW_WITH_CAVEAT,
}

#: Read-only code-to-outcome mapping. Every member appears exactly once, and every
#: outcome class is inhabited — mirroring `001`'s rule that a declared outcome no
#: code can express is a state nothing may emit or audit.
CHANNEL_REASON_CODE_OUTCOME: Mapping[ChannelReasonCode, Outcome] = MappingProxyType(_OUTCOMES)


def channel_outcome_for(code: ChannelReasonCode) -> Outcome:
    """Outcome class for ``code``.

    Raises rather than defaulting: an unmapped code means the enum and the table
    have drifted, and guessing an outcome would let a denial read as an allow.
    """
    try:
        return CHANNEL_REASON_CODE_OUTCOME[code]
    except KeyError as exc:  # pragma: no cover - guarded by the contract test
        raise ValueError(f"channel reason code {code!r} has no declared outcome class") from exc


def channel_codes_with_outcome(outcome: Outcome) -> tuple[ChannelReasonCode, ...]:
    """All codes classified as ``outcome``, in declaration order."""
    return tuple(code for code in ChannelReasonCode if CHANNEL_REASON_CODE_OUTCOME[code] is outcome)
