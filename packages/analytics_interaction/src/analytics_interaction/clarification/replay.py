"""Replay — bounded, not eliminated — T120 (FR-080; SC-044).

    **Single-use consumption cannot be detected without state.** This is stated
    as a governed limitation rather than implied as a control.
    — `contracts/clarification-contract.md` §6

This module exists to make that sentence something a consumer receives rather
than something a reader has to find. The limitation travels **in the response**,
so anyone building on this contract inherits the knowledge instead of the
assumption.

## What is enforced, and what is not

| Enforced | Not enforced |
|---|---|
| Integrity — the seal covers every field | Single-use consumption |
| Identity binding — principal and fingerprint | Re-entry at an earlier point of one chain |
| Re-authorization at resumption | — |
| Version binding — catalog, policy, vocabulary | — |
| Explicit expiry, against a supplied instant | — |
| Round accounting, monotonic and sealed | — |

## Why no cache

An in-memory nonce registry, a process-local seen-set or a bounded LRU would all
*appear* to prevent replay and would each fail the moment a second process, a
restart or a redeploy entered the picture — and they fail **silently**, because
nothing observes that the memory was empty. `T120`'s own validation note is
blunt about it:

    a control that works only when a process happens to remember is worse than a
    stated limitation.

Worse, specifically, because a stated limitation is reasoned about and a
half-control is relied upon. So there is no cache here, no registry, no queue and
no durable store — and `T121` pins the boundary the future store will cross.

## The residual exposure, stated exactly

Replay is narrowed to: *re-enter an earlier point of one clarification chain,
inside its expiry window, as the same principal, who is still authorized.* Within
one chain the round bound can never be exceeded, because the bound is sealed into
each issued contract. And a clarification constructs no governed request and
reaches no warehouse (`FR-016`), so the residual cost is interpretation cost only
— itself attributed to a resolved principal (`FR-091`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.clarification import ClarificationContract

__all__ = [
    "ENFORCED_CONTROLS",
    "REPLAY_LIMITATION_CODE",
    "UNENFORCEABLE_WITHOUT_STATE",
    "ReplayPosture",
    "assert_not_expired",
    "assert_within_round_bound",
    "replay_posture",
]

#: The governed code under which the limitation is disclosed. It is a
#: ``LocalizedRef`` code rather than a sentence: the wording is `D-18` governed
#: content, and composing one here would be this feature authoring user-facing
#: text about its own weakness.
REPLAY_LIMITATION_CODE = "CLARIFICATION_REPLAY_NOT_DETECTABLE"

#: What a stateless contract can prove. Named so a consumer can enumerate the
#: guarantees rather than infer them from behaviour.
ENFORCED_CONTROLS: tuple[str, ...] = (
    "integrity",
    "identity_binding",
    "authorization_revalidation",
    "version_binding",
    "explicit_expiry",
    "monotonic_rounds",
)

#: What it cannot. Named for the same reason, and asserted by `T120`'s suite to
#: be disjoint from the enforced set — a control that appeared in both lists
#: would be one somebody had quietly reclassified.
UNENFORCEABLE_WITHOUT_STATE: tuple[str, ...] = (
    "single_use_consumption",
    "cross_process_replay_detection",
)


@dataclass(frozen=True, slots=True)
class ReplayPosture:
    """The exact replay position of one contract, as data a response can carry.

    A value rather than a docstring, because `FR-080` requires the limitation to
    reach the consumer. ``consumption_detected`` is permanently ``False`` and is
    present so a caller reading the field sees the answer rather than the absence
    of the question.
    """

    enforced: tuple[str, ...]
    unenforceable: tuple[str, ...]
    limitation_code: str
    consumption_detected: bool = False


def replay_posture() -> ReplayPosture:
    """The stated posture. Constant, because the limitation does not vary.

    A function rather than a module constant so a caller cannot mutate the value
    it is handed — and so the posture has one construction site if a future store
    ever narrows it.
    """
    return ReplayPosture(
        enforced=ENFORCED_CONTROLS,
        unenforceable=UNENFORCEABLE_WITHOUT_STATE,
        limitation_code=REPLAY_LIMITATION_CODE,
    )


def assert_not_expired(contract: ClarificationContract, *, at: datetime) -> None:
    """Refuse an expired contract, against an **explicitly supplied** instant.

    No clock is read. A system clock here would make the same contract valid or
    invalid depending on when a test ran, and expiry is a governed boundary that
    must be reproducible: `SC-005` requires identical output for identical input,
    and "now" is not an input a caller supplied.

    The boundary is exclusive at the far end — a contract is live *until* its
    expiry instant, and ``at == expires_at`` refuses. Both sides of that boundary
    are asserted, because an off-by-one here silently extends every contract's
    life by one tick.
    """
    if at.tzinfo is None:
        # A naive instant cannot be compared with an aware one, and coercing it
        # would be assuming a zone this feature has no business choosing.
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_EXPIRED,
            "the evaluation instant carries no time zone; expiry is not evaluable",
        )
    if at >= contract.expires_at:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_EXPIRED,
            "the clarification contract has expired; it is never renewed or extended",
        )


def assert_within_round_bound(contract: ClarificationContract) -> None:
    """Refuse once the governed round bound is reached.

    **Reached, not violated** (`FR-017`). The bound is a `D-19` value sealed into
    each issued contract, so it cannot be raised by editing a resubmitted one —
    and within a chain it can never be exceeded, because every issued contract
    carries the bound the issuer applied.

    ``CLARIFICATION_EXHAUSTED`` rather than a tamper code: a caller who used every
    round did nothing wrong, and coding it as tampering would tell them they had.
    """
    if contract.rounds_consumed >= contract.round_bound:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_EXHAUSTED,
            "the governed clarification round bound is reached; the question abstains",
        )
