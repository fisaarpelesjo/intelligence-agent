"""Clarification issuance — T114 (FR-015, FR-016; SC-012, SC-014).

**Unresolved or multi-candidate slots clarify rather than guess.**

The alternative — picking the most likely candidate — is the failure this whole
subsystem exists to prevent. A guessed resolution produces a confident answer to
a question nobody asked, and the reader has no way to tell. `FR-015` is explicit:
return the candidates, never choose among them.

## Refuses `CLARIFICATION_UNAVAILABLE` without a seal

`D-21` is undeclared, so **no contract can be issued today** and an ambiguous
question refuses instead of clarifying. That is a real capability loss and it is
stated rather than engineered around: an unsealed contract would make the rounds
consumed, the round bound, the expiry, the candidate set and the principal
binding caller-editable, which is to say absent.

The gate is reached through :func:`analytics_interaction.clarification.seal.issue_seal`,
before anything is constructed — so a refused issuance builds nothing, not even a
draft it then discards.

## Every governed input is supplied, none is invented

``round_bound`` and the expiry come from `D-19`. ``issued_at`` is passed in.
Nothing here reads a clock, chooses a bound, picks an expiry or generates a
nonce from a random source this feature selected — a clock would make issuance
irreproducible, and `SC-005` requires identical output for identical input.

## A clarification costs nothing downstream

No governed request is constructed and no execution port is touched (`FR-016`).
`T115` counts both and expects zero. That is why the ambiguity is worth
surfacing: asking costs interpretation only, while guessing costs a wrong answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation, build
from ..contracts.clarification import (
    SUPPORTED_CONTRACT_VERSIONS,
    CandidateRef,
    ClarificationContract,
    Seal,
)
from ..contracts.reason_codes import InterpretationReasonCode
from .seal import issue_seal

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable
    from datetime import datetime, timedelta

    from ..compliance.readiness import ReadinessRecord
    from ..contracts.intent import SlotKind
    from .seal import SealPort

__all__ = [
    "CURRENT_CONTRACT_VERSION",
    "issue_clarification",
]

#: The version this build issues. Read from the supported set rather than written
#: twice, so "what we issue" and "what we honour" cannot drift.
CURRENT_CONTRACT_VERSION: int = max(SUPPORTED_CONTRACT_VERSIONS)


def issue_clarification(
    *,
    correlation_id: str,
    interpretation_id: str,
    auth_fingerprint: str,
    unresolved: SlotKind,
    candidates: tuple[CandidateRef, ...],
    rounds_consumed: int,
    round_bound: int,
    issued_at: datetime,
    expiry: timedelta,
    nonce: str,
    catalog_release: str,
    policy_version: str,
    vocabulary_version: str,
    port: SealPort | None,
    key_id: str,
    algorithm: str,
    records: Iterable[ReadinessRecord] | None = None,
) -> ClarificationContract:
    """Issue a sealed clarification contract, or refuse.

    Keyword-only throughout. Fourteen governed bindings travel together and a
    positional call would let two of them be transposed — ``interpretation_id``
    and ``correlation_id`` are both opaque strings, and swapping them would
    produce a contract that seals cleanly and binds the wrong thing.

    Order matters:

    1. **candidates** — a contract offering nothing to choose between is not a
       clarification;
    2. **the draft** — built through the contract, so its own validators run: the
       expiry must follow issuance, and a contract already at the round bound is
       not issuable;
    3. **the seal** — which reaches the `D-21` gate and refuses today.

    The draft is sealed with a placeholder and then rebuilt with the real seal.
    The placeholder never leaves this function and is never returned: the
    preimage excludes ``seal``, so the value sealed over is identical either way.
    """
    if not candidates:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_REQUIRED,
            "a clarification offers governed candidates; there are none to offer",
        )

    draft = build(
        ClarificationContract,
        contract_version=CURRENT_CONTRACT_VERSION,
        correlation_id=correlation_id,
        interpretation_id=interpretation_id,
        auth_fingerprint=auth_fingerprint,
        unresolved=unresolved,
        candidates=candidates,
        rounds_consumed=rounds_consumed,
        round_bound=round_bound,
        issued_at=issued_at,
        expires_at=issued_at + expiry,
        nonce=nonce,
        catalog_release=catalog_release,
        policy_version=policy_version,
        vocabulary_version=vocabulary_version,
        seal=Seal(key_id=key_id, algorithm=algorithm, value="unsealed"),
    )

    seal = issue_seal(draft, port=port, key_id=key_id, algorithm=algorithm, records=records)
    return draft.model_copy(update={"seal": seal})
