"""Statelessness, and the seven resumption checks — T117 (FR-075, FR-079; SC-043).

    Evidence: identical outcome from an instance holding nothing.
    — `tasks.md` T117

**The proof is an integration test, not a claim.** A contract issued in one
process resumes against a **freshly imported** module holding nothing, and
produces an identical outcome. The import is reloaded rather than reused, so a
module-level cache somebody added later would be discarded between the two halves
and the test would fail — which is the only way "holds no state" stays true after
this file is written.

The seven checks of `contracts/clarification-contract.md` §5 are asserted one at
a time. A single "an invalid contract refuses" case would pass while six of the
seven were missing, and the six most likely to be missing are the ones nobody
sees fail: a stale vocabulary version, a re-pinned catalog release, a principal
whose access was revoked between turns.

**Nothing repairs.** Not by extending an expiry, not by re-pinning a version, not
by downgrading a failed seal to a fresh question. Each refusal is checked for its
own governed code, so a check that fired for the wrong reason is visible.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from analytics_interaction.authorization.context_preflight import (
    AuthorizedContext,
    resolve_authorization_context,
)
from analytics_interaction.clarification.resume import (
    RESUMPTION_CHECKS,
    GoverningVersions,
    resume_clarification,
)
from analytics_interaction.compliance.gates import InteractionCapability
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.clarification import ClarificationContract
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code

from ..conftest import RESOLVED_PRINCIPAL, SUPPLIED_PRINCIPAL
from ..fixtures.clarifications import (
    FIXTURE_KEY,
    FixtureSealPort,
    candidate,
    issued_contract,
    ready_records,
)
from ..fixtures.counters import CountingResolver, Surfaces

pytestmark = pytest.mark.integration

SEALING = ready_records(InteractionCapability.D_21)
PORT = FixtureSealPort(key=FIXTURE_KEY)

ISSUED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
DURING = datetime(2026, 8, 13, 12, 5, tzinfo=UTC)
IN_FORCE = GoverningVersions(
    catalog_release="r-1", policy_version="pol-1", vocabulary_version="voc-1"
)


def _resume(
    contract: ClarificationContract,
    *,
    authorized: AuthorizedContext,
    in_force: GoverningVersions = IN_FORCE,
    at: datetime = DURING,
) -> ClarificationContract:
    return resume_clarification(
        contract, authorized=authorized, in_force=in_force, at=at, port=PORT, records=SEALING
    )


# --- statelessness ------------------------------------------------------------------


def test_a_contract_resumes_against_a_freshly_imported_module(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`SC-043`. The module is **reloaded**, so any cache is discarded first.

    Reusing the already-imported module would prove only that state was not
    consulted this time. Reloading proves there was nothing to consult.
    """
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)

    from analytics_interaction.clarification import resume as resume_module

    fresh = importlib.reload(resume_module)
    resumed = fresh.resume_clarification(
        contract,
        authorized=authorized,
        in_force=fresh.GoverningVersions(
            catalog_release="r-1", policy_version="pol-1", vocabulary_version="voc-1"
        ),
        at=DURING,
        port=PORT,
        records=SEALING,
    )

    assert resumed == contract


def test_the_outcome_is_identical_across_two_independent_resumptions(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """No first-time path, no warm-up, no remembered turn."""
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)

    first = _resume(contract, authorized=authorized)
    second = _resume(contract, authorized=authorized)

    assert first.model_dump_json() == second.model_dump_json() == contract.model_dump_json()


def test_the_contract_is_returned_unchanged(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Validated and submitted are the same object; nothing is rewritten."""
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)
    assert _resume(contract, authorized=authorized) is contract


# --- the seven checks, one at a time ------------------------------------------------


def test_the_seven_checks_are_named_in_order() -> None:
    """Mapped to §5's table, so a refusal is traceable to a row."""
    assert RESUMPTION_CHECKS == (
        "contract_version",
        "seal",
        "expiry",
        "round_bound",
        "governing_versions",
        "principal_binding",
        "reauthorization",
    )


def test_an_unknown_contract_version_refuses(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Check 1. Never partially honoured: a half-understood contract's sealed
    fields no longer all mean what the issuer meant."""
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint).model_copy(update={"contract_version": 99})

    with pytest.raises(ContractViolation) as refusal:
        _resume(contract, authorized=authorized)
    assert refusal.value.code is Code.CLARIFICATION_VERSION_UNKNOWN


def test_an_expired_contract_refuses(authorized_pair: tuple[AuthorizedContext, str]) -> None:
    """Check 3. Never renewed, never extended."""
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)

    with pytest.raises(ContractViolation) as refusal:
        _resume(contract, authorized=authorized, at=contract.expires_at + timedelta(seconds=1))
    assert refusal.value.code is Code.CLARIFICATION_EXPIRED


def test_the_expiry_boundary_is_exact(authorized_pair: tuple[AuthorizedContext, str]) -> None:
    """Both sides of it, against an **explicitly supplied** instant.

    A contract is live *until* its expiry. One tick before is valid; the instant
    itself is not. An off-by-one here silently extends every contract's life.
    """
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)

    _resume(contract, authorized=authorized, at=contract.expires_at - timedelta(microseconds=1))
    with pytest.raises(ContractViolation):
        _resume(contract, authorized=authorized, at=contract.expires_at)


def test_no_clock_is_read_during_resumption() -> None:
    """`SC-005`: the same inputs must produce the same answer.

    Read from the source, because a clock call on a branch a test never took
    would not show up behaviourally.
    """
    import ast
    import inspect
    from pathlib import Path

    from analytics_interaction.clarification import replay, resume

    for module in (resume, replay):
        tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
        called = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute | ast.Name)
        }
        assert not called & {"now", "utcnow", "today", "time", "monotonic"}


def test_a_naive_instant_refuses_rather_than_being_assumed(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Coercing it would assume a zone this feature has no business choosing."""
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)

    with pytest.raises(ContractViolation) as refusal:
        _resume(contract, authorized=authorized, at=datetime(2026, 8, 13, 12, 5))
    assert refusal.value.code is Code.CLARIFICATION_EXPIRED


def test_editing_the_round_count_is_caught_by_the_seal_first(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Check 2 runs before check 4, and the ordering is the protection.

    A caller who edits ``rounds_consumed`` to buy another round does not reach
    the round check at all — the seal no longer matches, so the contract is
    refused as tampered. Reading a covered field for meaning *before* verifying
    would let an edited bound influence a decision.
    """
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint, rounds_consumed=1, round_bound=2)
    edited = contract.model_copy(update={"rounds_consumed": 0})

    with pytest.raises(ContractViolation) as refusal:
        _resume(edited, authorized=authorized)
    assert refusal.value.code is Code.CLARIFICATION_TAMPERED


def test_reaching_the_round_bound_abstains() -> None:
    """Check 4, at the level it is reachable.

    A contract **at** the bound is not issuable — the contract's own validator
    refuses one, so within a chain the bound can never be exceeded. The check
    therefore lives below resumption, and this asserts it there rather than
    constructing a contract issuance would never produce.

    ``CLARIFICATION_EXHAUSTED`` rather than a tamper code: a caller who used
    every round did nothing wrong, and coding it as tampering would say they had.
    """
    from analytics_interaction.clarification.replay import assert_within_round_bound

    from ..fixtures.clarifications import ISSUED_AT

    at_bound = ClarificationContract.model_construct(
        contract_version=1,
        correlation_id="corr-1",
        interpretation_id="interp-1",
        auth_fingerprint="fp-1",
        unresolved=candidate("installs").slot,
        candidates=(candidate("installs"),),
        rounds_consumed=2,
        round_bound=2,
        issued_at=ISSUED_AT,
        expires_at=ISSUED_AT + timedelta(minutes=15),
        nonce="nonce-1",
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
        seal=None,
    )

    with pytest.raises(ContractViolation) as refusal:
        assert_within_round_bound(at_bound)
    assert refusal.value.code is Code.CLARIFICATION_EXHAUSTED


def test_a_contract_at_the_bound_is_not_issuable(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The reason the check above needs ``model_construct`` to reach it.

    Issuing a contract already at the bound would offer a round that cannot be
    taken, so the contract refuses at construction — which is what makes the
    bound un-exceedable within a chain rather than merely un-exceeded.
    """
    _, fingerprint = authorized_pair
    with pytest.raises(ContractViolation):
        issued_contract(fingerprint=fingerprint, rounds_consumed=2, round_bound=2)


def test_round_accounting_is_monotonic_within_a_chain(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Each issued contract carries the round the issuer applied.

    The bound is sealed in, so replaying an earlier contract cannot raise it —
    within one chain the bound can never be exceeded.
    """
    _, fingerprint = authorized_pair
    chain = [
        issued_contract(fingerprint=fingerprint, rounds_consumed=consumed, round_bound=3)
        for consumed in (0, 1, 2)
    ]
    assert [contract.rounds_consumed for contract in chain] == [0, 1, 2]
    assert {contract.round_bound for contract in chain} == {3}


@pytest.mark.parametrize(
    "moved",
    [
        pytest.param(GoverningVersions("r-2", "pol-1", "voc-1"), id="catalog-release"),
        pytest.param(GoverningVersions("r-1", "pol-2", "voc-1"), id="policy-version"),
        pytest.param(GoverningVersions("r-1", "pol-1", "voc-2"), id="vocabulary-version"),
    ],
)
def test_a_governing_version_that_moved_refuses(
    authorized_pair: tuple[AuthorizedContext, str], moved: GoverningVersions
) -> None:
    """Check 5. Never re-pinned to current.

    Re-pinning would silently reinterpret the caller's earlier question under new
    rules and present the result as a continuation.
    """
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)

    with pytest.raises(ContractViolation) as refusal:
        _resume(contract, authorized=authorized, in_force=moved)
    assert refusal.value.code is Code.CLARIFICATION_CONTEXT_MISMATCH


def test_the_version_refusal_names_no_version(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """A caller learns the contract no longer applies, not what the catalog is on."""
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)

    with pytest.raises(ContractViolation) as refusal:
        _resume(
            contract,
            authorized=authorized,
            in_force=GoverningVersions("r-secret-9", "pol-1", "voc-1"),
        )
    assert "r-secret-9" not in str(refusal.value)
    assert "r-1" not in str(refusal.value)


def test_another_principals_context_refuses(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Checks 6 and 7. The contract belongs to one principal, and only to them."""
    _, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)
    other = resolve_authorization_context(
        SUPPLIED_PRINCIPAL.model_copy(update={"principal_ref": "p-2"}),
        resolver=CountingResolver(
            Surfaces(), answer=RESOLVED_PRINCIPAL.model_copy(update={"principal_ref": "p-2"})
        ),
    )

    with pytest.raises(ContractViolation) as refusal:
        _resume(contract, authorized=other)
    assert refusal.value.code is Code.CLARIFICATION_CONTEXT_MISMATCH


def test_a_revoked_grant_refuses(authorized_pair: tuple[AuthorizedContext, str]) -> None:
    """Check 7, distinctly from check 6.

    The same principal, whose access narrowed between turns. The fingerprint
    covers the tag set, so a revoked grant produces a different digest — and a
    contract that outlived its holder's access would be a stored grant.
    """
    _, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)
    narrowed = resolve_authorization_context(
        SUPPLIED_PRINCIPAL,
        resolver=CountingResolver(
            Surfaces(),
            answer=RESOLVED_PRINCIPAL.model_copy(update={"granted_access_tags": frozenset()}),
        ),
    )

    with pytest.raises(ContractViolation) as refusal:
        _resume(contract, authorized=narrowed)
    assert refusal.value.code is Code.CLARIFICATION_CONTEXT_MISMATCH


# --- nothing repairs -----------------------------------------------------------------


def test_a_failed_resumption_returns_no_partial_contract(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """No repaired copy, no downgraded fresh question, no salvaged field."""
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint).model_copy(update={"contract_version": 99})

    with pytest.raises(ContractViolation) as refusal:
        _resume(contract, authorized=authorized)

    for attribute in ("contract", "candidates", "seal", "repaired"):
        assert not hasattr(refusal.value, attribute)


def test_the_candidate_set_is_not_disclosed_by_a_refusal(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """A refused resumption tells a caller nothing about what was on offer."""
    _, fingerprint = authorized_pair
    contract = issued_contract(
        fingerprint=fingerprint, candidates=(candidate("secret_metric"), candidate("installs"))
    )
    other = resolve_authorization_context(
        SUPPLIED_PRINCIPAL.model_copy(update={"principal_ref": "p-2"}),
        resolver=CountingResolver(
            Surfaces(), answer=RESOLVED_PRINCIPAL.model_copy(update={"principal_ref": "p-2"})
        ),
    )

    with pytest.raises(ContractViolation) as refusal:
        _resume(contract, authorized=other)
    assert "secret_metric" not in str(refusal.value)


# --- OD-69: the amended boundary, driven in both directions ----------------------------------


class _MemorySpy:
    """A `ConversationMemory` that records what reached it — the write side's witness."""

    def __init__(self) -> None:
        self.turns: list[dict[str, object]] = []

    def remember_turn(
        self,
        *,
        identity: str,
        scope: str,
        message_id: str,
        intent: str,
        metric_ids: tuple[str, ...],
        period: str,
        filter_fields: tuple[str, ...],
        instant: datetime,
    ) -> bool:
        self.turns.append(
            {
                "identity": identity,
                "scope": scope,
                "message_id": message_id,
                "intent": intent,
                "metric_ids": metric_ids,
                "period": period,
                "filter_fields": filter_fields,
                "instant": instant,
            }
        )
        return True

    def remembered_window(
        self, identity: str, *, now: datetime
    ) -> tuple[Mapping[str, object], ...] | None:
        return ()


def test_a_resumed_turn_is_remembered_through_the_contract_and_only_after_every_check(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`OD-69`'s write side, on the REAL resume with the suite's own fixtures.

    Structured fields only, from the contract and the authorized context; and the memory runs
    LAST — a refused resume remembers nothing, because memory of a turn that never happened would
    be the store asserting more than the system did.
    """
    authorized, fingerprint = authorized_pair
    contract = issued_contract(fingerprint=fingerprint)
    spy = _MemorySpy()

    returned = resume_clarification(
        contract,
        authorized=authorized,
        in_force=IN_FORCE,
        at=DURING,
        port=PORT,
        records=SEALING,
        memory=spy,
    )
    assert returned is contract
    assert len(spy.turns) == 1, "a successful resume did not reach the memory"
    turn = spy.turns[0]
    assert turn["identity"] == authorized.context.principal_ref
    assert turn["message_id"] == contract.correlation_id
    assert turn["intent"] == "clarification_resumed"
    assert turn["metric_ids"] == tuple(c.identifier for c in contract.candidates)
    assert turn["instant"] == DURING
    #: **No parameter carried content** — the signature is the `FR-082` enforcement.
    assert not set(turn) & {"question", "text", "reply", "value", "values", "payload"}


def test_a_refused_resume_remembers_nothing(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The order is load-bearing: memory runs only after every check accepted the contract."""
    authorized, _fingerprint = authorized_pair
    contract = issued_contract(fingerprint="uma-impressao-que-nao-e-a-dele")
    spy = _MemorySpy()
    with pytest.raises(ContractViolation):
        resume_clarification(
            contract,
            authorized=authorized,
            in_force=IN_FORCE,
            at=DURING,
            port=PORT,
            records=SEALING,
            memory=spy,
        )
    assert spy.turns == [], "a refused resume reached the memory"


def test_without_memory_the_resume_is_byte_identical_to_before_the_amendment() -> None:
    """The other direction: `memory` defaults to `None` — the entire pre-amendment suite is the
    proof of identical behaviour, and this node pins the default so nobody makes it ambient."""
    import inspect as _inspect

    parameter = _inspect.signature(resume_clarification).parameters["memory"]
    assert parameter.default is None
