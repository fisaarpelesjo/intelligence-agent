"""Resumption validation — T116 (FR-017, FR-079; SC-013, SC-044).

**Seven checks, each with its own governed code, none repairing.**

`contracts/clarification-contract.md` §5, in order:

| # | Check | On failure |
|---|---|---|
| 1 | `contract_version` known to this build | `CLARIFICATION_VERSION_UNKNOWN` — never half-honour |
| 2 | Seal validates over every field | `CLARIFICATION_TAMPERED` — never repair |
| 3 | `expires_at` is in the future | `CLARIFICATION_EXPIRED` — never renew or extend |
| 4 | `rounds_consumed < round_bound` | `CLARIFICATION_EXHAUSTED` — abstain; reached, not violated |
| 5 | Governing versions still in force | `CLARIFICATION_CONTEXT_MISMATCH` — never re-pin |
| 6 | Principal and authorization context match the binding | `CLARIFICATION_CONTEXT_MISMATCH` |
| 7 | Principal re-authorized **now** | the preflight's own refusal |

**None of them repairs.** Not by re-pinning a stale version to the current one,
not by extending an expiry, not by downgrading a failed seal to a fresh question.
A contract that fails any check is refused whole — a half-honoured contract is
one whose sealed fields no longer all mean what the issuer meant.

## Why check 7 is not check 6 again

Check 6 proves the contract belongs to this principal. Check 7 proves the
principal is **still entitled**. Authorization is revoked between turns, and a
contract that outlived its holder's access would be a stored grant — precisely
what a stateless design must not accidentally create.

So the caller passes a freshly resolved ``AuthorizedContext``: resolution happens
in the caller's step 2, and this function compares its fingerprint against the
sealed one. It cannot resolve authorization itself, because a function that
resolved it could be handed a resolver that always says yes.

## Order matters

The seal is verified **second**, before any field it covers is read for meaning.
Reading ``round_bound`` from an unverified contract and then verifying would let
a tampered bound influence a decision that a later check happened to undo. The
version check comes first only because a contract of an unknown version has no
guaranteed field set to verify a seal over.

## Statelessness

## AMENDED by `OD-69`, 2026-08-31

The sentence below said *"Nothing here reads a store, a cache or a prior turn"*, and it was true —
and load-bearing — until the owner amended the boundary: `resume` may now touch `011`'s memory
**through `ConversationMemory`** (the contract in `future_store`), never through a path of its own
and never carrying what `FR-082` forbids. The WRITE side is wired: a successfully resumed turn is
remembered, structured fields only, when a memory is supplied. The READ side stops at a measured
frontier: its only consumer is interpretation, `D-19`'s policy is `instances: []` by design, and a
node driving a synthetic path nobody can reach is the 408 tautology — so consumption waits for
governed content, and this paragraph is where that is written.

Apart from that one amended door: nothing here reads any OTHER store, cache or prior turn. Every
other input is the
resubmitted contract, the freshly resolved context, the governing versions in
force and an explicit evaluation instant. `T117` proves it by resuming against a
freshly constructed instance holding nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.clarification import SUPPORTED_CONTRACT_VERSIONS
from ..contracts.reason_codes import InterpretationReasonCode
from ..identity.authorization_fingerprint import derive_authorization_fingerprint
from .future_store import ConversationMemory
from .replay import assert_not_expired, assert_within_round_bound
from .seal import verify_seal

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable
    from datetime import datetime

    from ..authorization.context_preflight import AuthorizedContext
    from ..compliance.readiness import ReadinessRecord
    from ..contracts.clarification import ClarificationContract
    from .seal import SealPort

#: The one detail every context mismatch carries, whichever binding moved.
#:
#: Shared deliberately, and it is the disclosure control rather than a tidy-up. Checks
#: 5 and 6 both raise ``CLARIFICATION_CONTEXT_MISMATCH``, so the code already refuses to
#: say which binding failed — but two different detail strings put that distinction
#: straight back, one field over. A caller who can tell "the versions moved" from "this
#: is not your contract" can subtract the version moves and learn that the remainder is
#: a fact about a principal: their own revoked grant, or the existence of somebody
#: else's contract.
#:
#: So the sentence names neither the binding nor the principal. It says the contract no
#: longer matches the context it was issued into, which is true of every condition in
#: the category and is all the caller is told.
CONTEXT_MISMATCH_DETAIL = (
    "the clarification contract no longer matches the governed context it was issued "
    "into; it is never re-pinned, reassigned or partially honoured"
)

__all__ = [
    "CONTEXT_MISMATCH_DETAIL",
    "RESUMPTION_CHECKS",
    "GoverningVersions",
    "resume_clarification",
]

#: The seven checks, in the order they run. Named so `T116`'s suite asserts the
#: sequence rather than the presence of seven functions somewhere in the module —
#: and so a reader can map a refusal back to §5's table.
RESUMPTION_CHECKS: tuple[str, ...] = (
    "contract_version",
    "seal",
    "expiry",
    "round_bound",
    "governing_versions",
    "principal_binding",
    "reauthorization",
)


@dataclass(frozen=True, slots=True)
class GoverningVersions:
    """The catalog release, policy and vocabulary versions **currently in force**.

    Supplied by the caller rather than resolved here, for the same reason the
    authorization context is: a function that resolved its own comparison values
    could be handed ones that always match.

    A frozen triple rather than three loose strings, because check 5 compares all
    three and three separate parameters is how one of them gets forgotten at a
    call site.
    """

    catalog_release: str
    policy_version: str
    vocabulary_version: str


def resume_clarification(
    contract: ClarificationContract,
    *,
    authorized: AuthorizedContext,
    in_force: GoverningVersions,
    at: datetime,
    port: SealPort | None,
    records: Iterable[ReadinessRecord] | None = None,
    memory: ConversationMemory | None = None,
) -> ClarificationContract:
    """Validate a resubmitted contract, or refuse. Returns it **unchanged**.

    Returning the contract rather than ``None`` means a caller cannot proceed on
    one it did not pass through here — the validated value and the submitted
    value are the same object, so there is nothing to accidentally use instead.

    ``authorized`` must be the result of a **fresh** step-2 preflight. The type
    carries that: an ``AuthorizedContext`` cannot be constructed without one.
    """
    # 1. version — first, because an unknown version has no guaranteed field set.
    if contract.contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_VERSION_UNKNOWN,
            "the clarification contract version is not one this build honours; "
            "it is never partially honoured",
        )

    # 2. seal — before any covered field is read for meaning.
    verify_seal(contract, port=port, records=records)

    # 3. expiry — against the supplied instant, never a clock.
    assert_not_expired(contract, at=at)

    # 4. round bound — reached is an abstention, not a violation.
    assert_within_round_bound(contract)

    # 5. governing versions — never re-pinned to current.
    _assert_versions_in_force(contract, in_force)

    # 6. principal binding — the contract belongs to this principal.
    # 7. re-authorization — and this principal is still entitled.
    #
    # One comparison satisfies both, and that is not a shortcut. The fingerprint
    # is derived from the context the preflight resolved **now**; a revoked scope,
    # a withdrawn tag or a changed policy pin produces a different digest, so a
    # contract issued to a principal who has since lost access no longer matches.
    # The freshness lives in the type — ``AuthorizedContext`` is unconstructible
    # without a preflight — and the binding lives in the digest.
    if derive_authorization_fingerprint(authorized) != contract.auth_fingerprint:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_CONTEXT_MISMATCH,
            CONTEXT_MISMATCH_DETAIL,
        )

    # 8. memory — `OD-69`, and it runs LAST, only after every check above accepted the contract.
    #    A refused resume remembers nothing: memory of a turn that never happened would be the
    #    store asserting more than the system did. Structured fields only, from the contract and
    #    the authorized context — there is no parameter raw text could travel in. When no memory
    #    is supplied, this function is byte-identical to what it was before the amendment, and the
    #    whole existing suite is the proof.
    if memory is not None:
        memory.remember_turn(
            identity=authorized.context.principal_ref,
            scope=authorized.context.authorization_scope or "",
            message_id=contract.correlation_id,
            intent="clarification_resumed",
            metric_ids=tuple(candidate.identifier for candidate in contract.candidates),
            period="",
            filter_fields=(),
            instant=at,
        )

    return contract


def _assert_versions_in_force(contract: ClarificationContract, in_force: GoverningVersions) -> None:
    """Check 5. The governed world must not have moved under the contract.

    A catalog release published between turns changes what a metric *means*; a
    policy version changes what may be disclosed; a vocabulary version changes
    what a period expression resolves to. Resuming across any of them would
    answer a question interpreted under rules that no longer apply.

    Re-pinning to the current versions was the tempting alternative and is
    exactly wrong: it would silently reinterpret the caller's earlier question
    under new rules and present the result as a continuation.

    The refusal names no version, and carries the **same** detail as the
    authorization-binding check — see :data:`CONTEXT_MISMATCH_DETAIL`. A caller learns
    the contract no longer applies, and cannot tell whether the catalog moved or their
    own authorization did.
    """
    moved = (
        contract.catalog_release != in_force.catalog_release
        or contract.policy_version != in_force.policy_version
        or contract.vocabulary_version != in_force.vocabulary_version
    )
    if moved:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_CONTEXT_MISMATCH,
            CONTEXT_MISMATCH_DETAIL,
        )
