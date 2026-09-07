"""The stateless clarification contract — T038 (FR-076, FR-077; SC-044).

**The feature holds no state.** Not "minimal state", not "cache-only state" —
none. A clarification is a self-contained contract the caller transports and
resubmits, and resumption depends on no record this feature kept (`FR-075`).

All fifteen top-level fields are required — fourteen content fields plus the seal
— and the model contains **governed identifiers and enumerations only**: no
question text, no free-text reply content, no metric value, no filter value
(`FR-077`). ``CandidateRef.distinguishing`` is a ``LocalizedRef`` — a pointer
into governed content — and never a built string.

**Why the binding is a pair.** The contract binds
``(interpretation_id, auth_fingerprint)``, not identity alone. This is `002`'s
security amendment applied *before* the same mistake can be made here: `002`
keyed its execution ledger on ``QueryIdentity`` alone, and identity-only keying
let a caller in a different authorization scope attach to an execution acquired
by another. The fix was to split the key rather than pollute identity. Identity
stays principal-independent so audit can see the same question asked twice; the
fingerprint carries the authorization dimension.

**Sealing requires `D-21`, which is undeclared.** ``Seal`` declares the shape of
tamper-evidence and holds **no key material, no algorithm default and no
generator**. While `D-21` is undeclared no contract can be issued, and an
ambiguous question refuses instead of clarifying — a real capability loss, stated
rather than engineered around. Issuing unsealed contracts would make the rounds
consumed, the round bound, the expiry, the candidate set and the principal
binding caller-editable, which is to say absent.

Issuance, validation and resumption are Phase 12 (`T112`+). This module declares
the carrier.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, StrictInt, model_validator

from ._base import InteractionModel, LocalizedRef
from .intent import SlotKind

__all__ = [
    "CLARIFICATION_CONTRACT_FIELDS",
    "SUPPORTED_CONTRACT_VERSIONS",
    "CandidateRef",
    "ClarificationContract",
    "Seal",
]

#: Contract versions this build knows how to honour. An unknown version refuses
#: (``CLARIFICATION_VERSION_UNKNOWN``) and is **never partially honoured** — a
#: contract half-understood is a contract whose sealed fields no longer all mean
#: what the issuer meant.
SUPPORTED_CONTRACT_VERSIONS: frozenset[int] = frozenset({1})


class CandidateRef(InteractionModel):
    """One governed option a caller may choose between.

    Authorization-filtered **at read time** by `001`'s discovery surface, not
    filtered here: filtering is a property of the surface being used, not
    something this feature adds on top.

    ``distinguishing`` is what tells two candidates apart, and it is a pointer
    into governed content rather than free text. A built string would put an
    unreviewed sentence — potentially derived from the question — into a sealed
    contract the caller transports.
    """

    identifier: str = Field(min_length=1)
    slot: SlotKind
    distinguishing: LocalizedRef


class Seal(InteractionModel):
    """Tamper-evidence over **every** field of the contract.

    A mutation to any one of them fails validation, and the response is a refusal
    that never repairs, partially honours, or downgrades the contract to a fresh
    question (`FR-078`).

    ``key_id`` names the `D-21` key; ``value`` is the computed seal. **Neither is
    produced here.** There is no default algorithm, no generated key, no
    hardcoded secret and no fallback that seals with something weaker — the
    absence is the fail-closed behaviour, and a convenience default would quietly
    remove it.
    """

    key_id: str = Field(min_length=1)
    algorithm: str = Field(min_length=1)
    value: str = Field(min_length=1)


class ClarificationContract(InteractionModel):
    """Self-contained, versioned, sealed. The **only** carrier of continuity.

    Fourteen content fields plus the seal, fifteen in all. Nothing is optional,
    because an optional field in a sealed contract is a field an attacker can
    remove — the seal would then cover a smaller object than the issuer meant.

    **Replay is bounded, not eliminated.** Single-use consumption cannot be
    detected without state, and `FR-080` requires that to be stated as a governed
    limitation rather than implied as a control. The nonce, the issue instant and
    the expiry are validated; nothing can observe that a contract was already
    resumed. Replay is narrowed to *re-entering an earlier point of one
    clarification chain, inside its expiry window, as the same principal, who is
    still authorized* — and within one chain the round bound can never be
    exceeded, because the bound is sealed into each issued contract.
    """

    contract_version: StrictInt = Field(gt=0)
    correlation_id: str = Field(min_length=1)
    interpretation_id: str = Field(min_length=1)
    auth_fingerprint: str = Field(min_length=1)
    unresolved: SlotKind
    candidates: tuple[CandidateRef, ...]
    rounds_consumed: StrictInt = Field(ge=0)
    round_bound: StrictInt = Field(gt=0)
    issued_at: datetime
    expires_at: datetime
    nonce: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    vocabulary_version: str = Field(min_length=1)
    seal: Seal

    @model_validator(mode="after")
    def _the_expiry_follows_the_issue_instant(self) -> ClarificationContract:
        """An already-expired contract is not issuable.

        Expiry is a `D-19` value applied at issuance. A contract whose window
        closed before it opened would be one no caller could ever resume, which
        is a defect rather than a refusal.
        """
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must follow issued_at")
        return self

    @model_validator(mode="after")
    def _rounds_remain_within_the_sealed_bound(self) -> ClarificationContract:
        """The bound is sealed into the contract, so it cannot be raised by replay.

        Reaching it is an abstention, not a violation (`FR-017`) — but *issuing* a
        contract already at the bound would offer a round that cannot be taken.
        """
        if self.rounds_consumed >= self.round_bound:
            raise ValueError(
                "the governed clarification round bound is reached; no further contract is issued"
            )
        return self


#: The fourteen content fields plus the seal, named once so the field-set test
#: asserts against the contract rather than against a list restated in the test.
CLARIFICATION_CONTRACT_FIELDS: tuple[str, ...] = tuple(
    ClarificationContract.model_fields  # pyright: ignore[reportUnannotatedClassAttribute]
)
