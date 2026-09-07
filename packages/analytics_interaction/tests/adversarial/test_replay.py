"""Replay, expiry, exhaustion and re-authorization — T155 (FR-079, FR-080; SC-013, SC-044).

`SC-013` is cited here because "zero exchanges exceed the governed round bound" is what
this file establishes twice over: the bound cannot be exceeded at issuance, and a
resubmitted contract carrying a widened bound breaks its seal.

    A resubmitted clarification contract MUST refuse with the governed code for the
    condition that failed. The single-use limitation MUST be disclosed rather than
    implied. — `FR-079`, `FR-080`

    Evidence: expiry, context mismatch and tampering each refuse with their governed
    code; round exhaustion is prevented at issuance. — `tasks.md` T155

## Three governed refusal categories, and why they are three

The reason-code contract exposes exactly three resumption outcomes, and the grain is
deliberate:

| Condition | Governed code |
|---|---|
| the contract's window has passed | `CLARIFICATION_EXPIRED` |
| a mismatched context (see below) | `CLARIFICATION_CONTEXT_MISMATCH` |
| any sealed field no longer matches its seal | `CLARIFICATION_TAMPERED` |

A **mismatched context** is any of: the wrong principal, a revoked grant, a changed
scope, a re-pinned authorization policy, or a superseded catalog, policy or vocabulary
binding. All five carry the one code.

Round exhaustion is not on this list because it is not a resumption outcome. A
contract at its governed bound **cannot be issued**: the contract's own validator
refuses it, so no over-bound contract exists to resubmit. `CLARIFICATION_EXHAUSTED`
belongs to issuance, and `assert_within_round_bound` is defence in depth for a
contract that arrived some other way.

## Why one code covers five context conditions

**Disclosure symmetry.** Splitting them would leak which internal binding moved.

A caller presenting somebody else's contract and a caller whose own access was
revoked must be indistinguishable — otherwise the pair of refusals is an oracle for
whose contract exists and whose grants changed. Once those two share a code, a
superseded catalog release must share it too: a distinct "the release moved" code
would let a caller subtract it from the set and learn that a context mismatch which
is *not* a version move is a principal fact about them or about somebody else.

So the contract exposes **one** governed mismatch category, and this file asserts
that grain rather than a finer one. The refusal names no version, no principal, no
scope and no tag. Where a caller should go next is the governed message contract's to
say, and it may differentiate guidance only where it explicitly permits doing so —
which is a wording decision, not a code decision, and not this suite's.

## Why expiry and tampering stay separate

They are not principal facts. An expiry is a property of the contract the caller
holds and the instant they resubmitted it — both already known to them. A tamper is
not a caller mistake at all. Neither discloses anything about another principal's
authorization, so neither has a reason to be folded into the mismatch category, and
folding them would send a caller who simply waited too long looking for a governance
problem.

## What replay prevention this feature does *and does not* have

Stateless by design, so there is no record of a contract having been used. A contract
resubmitted twice inside its window validates twice, and that is a **stated
limitation** rather than a bug: preventing it needs a durable store, which would need
its own access control, retention and audit, and which nothing here owns.

`FR-080` requires the limitation to reach the consumer, so it is a value on the
response — `ReplayPosture` — and this file asserts the honest shape of it:
`consumption_detected` is permanently `False`, the unenforceable controls are named,
and nothing claims single-use. A suite that tested replay *prevention* would be
testing something this feature does not do, and would pass only by accident.

## Fixture-only

`D-21` is undeclared. The synthetic key lives in `tests/fixtures/seal/`; the shipped
state refuses everything and is asserted separately.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType

from analytics_interaction.clarification.replay import (
    ENFORCED_CONTROLS,
    REPLAY_LIMITATION_CODE,
    UNENFORCEABLE_WITHOUT_STATE,
    assert_not_expired,
    assert_within_round_bound,
    replay_posture,
)
from analytics_interaction.clarification.resume import GoverningVersions, resume_clarification
from analytics_interaction.compliance.gates import InteractionCapability
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.clarification import ClarificationContract
from analytics_interaction.contracts.intake import PrincipalContext
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.identity.authorization_fingerprint import (
    derive_authorization_fingerprint,
)

from ..conftest import RESOLVED_PRINCIPAL, authorize
from ..fixtures.clarifications import (
    EXPIRY,
    FIXTURE_KEY,
    ISSUED_AT,
    FixtureSealPort,
    issued_contract,
    ready_records,
    unready_records,
)

pytestmark = pytest.mark.adversarial

READY = ready_records(InteractionCapability.D_21)
PORT = FixtureSealPort(key=FIXTURE_KEY)
IN_FORCE = GoverningVersions(
    catalog_release="r-1", policy_version="pol-1", vocabulary_version="voc-1"
)

#: Inside the window, and comfortably so. A boundary instant is tested separately.
LIVE = ISSUED_AT + timedelta(minutes=5)

#: A second, fully-resolved principal. Everything about their authorization matches
#: the first except who they are — so a binding that compared grants rather than
#: identity would let this one resume somebody else's clarification.
OTHER_PRINCIPAL = PrincipalContext(
    principal_ref="p-2",
    principal_type=PrincipalType.USER,
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    authorization_policy_pin="authpol-1",
)


def _contract(**overrides: object) -> ClarificationContract:
    return issued_contract(
        port=PORT,
        fingerprint=derive_authorization_fingerprint(authorize()),
        **overrides,  # pyright: ignore[reportArgumentType]
    )


def _authorize(resolved: PrincipalContext) -> object:
    """Run the real preflight for an arbitrary resolved context.

    The supplied half must agree with the resolved half on ``principal_ref`` and
    ``principal_type``, or the preflight refuses before any of this file's
    conditions can be reached — a caller supplying their own type is *asserting*
    authorization, which is its own refusal and would mask the one under test.
    """
    from analytics_interaction.authorization.context_preflight import (
        resolve_authorization_context,
    )

    from ..fixtures.counters import CountingResolver, Surfaces

    return resolve_authorization_context(
        PrincipalContext(
            principal_ref=resolved.principal_ref, principal_type=resolved.principal_type
        ),
        resolver=CountingResolver(Surfaces(), answer=resolved),
    )


def _resume(
    contract: ClarificationContract,
    *,
    at: datetime = LIVE,
    principal: PrincipalContext = RESOLVED_PRINCIPAL,
    in_force: GoverningVersions = IN_FORCE,
    records: object = READY,
) -> ClarificationContract:
    return resume_clarification(
        contract,
        authorized=_authorize(principal),  # pyright: ignore[reportArgumentType]
        in_force=in_force,
        at=at,
        port=PORT,
        records=records,  # pyright: ignore[reportArgumentType]
    )


def _refusal(**kwargs: object) -> ContractViolation:
    with pytest.raises(ContractViolation) as raised:
        _resume(**kwargs)  # pyright: ignore[reportArgumentType]
    return raised.value


# --- the control --------------------------------------------------------------------


def test_a_live_contract_resumes_unchanged() -> None:
    """The control, and the identity claim.

    ``resume_clarification`` returns the **same object** rather than a copy, so a
    caller cannot proceed on a contract that did not pass validation while
    believing it did.
    """
    contract = _contract()
    assert _resume(contract) is contract


# --- condition 1: expiry -----------------------------------------------------------


def test_an_expired_contract_refuses_with_its_own_code() -> None:
    assert _refusal(contract=_contract(), at=ISSUED_AT + EXPIRY + timedelta(seconds=1)).code is (
        Code.CLARIFICATION_EXPIRED
    )


def test_the_expiry_boundary_is_exclusive_at_the_far_end() -> None:
    """``at == expires_at`` refuses; one tick earlier does not.

    Both sides, because an off-by-one here silently extends every contract's life
    by one tick — and a test of only the far side would pass against an
    implementation that had extended it by a minute.
    """
    contract = _contract()
    assert_not_expired(contract, at=contract.expires_at - timedelta(microseconds=1))
    with pytest.raises(ContractViolation) as raised:
        assert_not_expired(contract, at=contract.expires_at)
    assert raised.value.code is Code.CLARIFICATION_EXPIRED


def test_a_naive_instant_refuses_rather_than_assuming_a_zone() -> None:
    """Coercing it would be choosing a zone this feature has no business choosing.

    And the failure would be silent: a naive instant read as UTC extends or
    shortens every window by the caller's offset, in a direction nobody declared.
    """
    with pytest.raises(ContractViolation) as raised:
        assert_not_expired(_contract(), at=datetime(2026, 8, 13, 12, 5))
    assert raised.value.code is Code.CLARIFICATION_EXPIRED


def test_an_expired_contract_is_never_renewed() -> None:
    """No extension path, and none reachable by resubmitting.

    Asserted by resubmitting the same expired contract three times: an
    implementation that renewed on first contact would let the second attempt
    through.
    """
    contract = _contract()
    late = contract.expires_at + timedelta(hours=1)
    for _ in range(3):
        assert _refusal(contract=contract, at=late).code is Code.CLARIFICATION_EXPIRED


# --- condition 2: the round bound is reached --------------------------------------


def test_the_bound_is_enforced_at_issuance_not_only_at_resumption() -> None:
    """**Where the bound actually bites**, which is earlier than expected.

    A contract at its bound cannot be *issued*: the contract's own validator
    refuses it, so ``resume_clarification`` never sees one through the real
    issuance path. That is the stronger placement — an exhausted contract does not
    exist to be resubmitted — and it means ``assert_within_round_bound`` is
    defence in depth for a contract that arrived some other way.

    Asserted at both sites rather than only at the one that fires today, because a
    later edit relaxing the validator would silently make the resumption check the
    only guard, and it is the one nothing currently exercises end to end.
    """
    with pytest.raises(ContractViolation) as issuance:
        _contract(rounds_consumed=2, round_bound=2)
    assert "round bound" in str(issuance.value)

    at_bound = _contract().model_copy(update={"rounds_consumed": 2, "round_bound": 2})
    with pytest.raises(ContractViolation) as resumption:
        assert_within_round_bound(at_bound)
    assert resumption.value.code is Code.CLARIFICATION_EXHAUSTED


def test_the_bound_cannot_be_raised_by_editing_the_resubmission() -> None:
    """The bound is sealed into the contract, so raising it breaks the seal.

    This is why the bound lives in the contract rather than being looked up at
    resumption: a looked-up bound would move when the policy moved, and a caller
    holding a contract issued under a bound of 2 could be granted 5 by a policy
    edit between turns.

    Started from a *live* contract, because one at its bound cannot be issued at
    all — so the attacker's real position is holding a live contract and trying to
    buy extra rounds by widening the bound on the way back in.
    """
    live = _contract(rounds_consumed=1, round_bound=2)
    widened = live.model_copy(update={"round_bound": 9})
    assert _refusal(contract=widened).code is Code.CLARIFICATION_TAMPERED


def test_one_round_short_of_the_bound_still_resumes() -> None:
    """The control for the bound. Without it, exhaustion could mean "always"."""
    assert assert_within_round_bound(_contract(rounds_consumed=1, round_bound=2)) is None


# --- condition 3: a foreign contract ----------------------------------------------


def test_a_contract_issued_to_another_principal_refuses_with_its_own_code() -> None:
    """The fingerprint is the binding, and it does not match.

    Asserted through a genuinely different principal rather than a mutated
    fingerprint: mutating the field would break the seal and refuse with the
    tamper code, which is a different mechanism and would hide this one.
    """
    assert _refusal(contract=_contract(), principal=OTHER_PRINCIPAL).code is (
        Code.CLARIFICATION_CONTEXT_MISMATCH
    )


def test_the_mismatch_refusal_names_no_principal() -> None:
    """A refusal naming either principal would leak who the contract belongs to."""
    message = str(_refusal(contract=_contract(), principal=OTHER_PRINCIPAL))
    for leaked in ("p-1", "p-2", "tenant-a", "authpol-1", "installs:read"):
        assert leaked not in message


# --- condition 4: still the same principal, no longer entitled --------------------


@pytest.mark.parametrize(
    "revoked",
    [
        pytest.param({"granted_access_tags": frozenset[str]()}, id="tag-withdrawn"),
        pytest.param({"granted_access_tags": frozenset({"sessions:read"})}, id="tag-swapped"),
        pytest.param({"authorization_scope": "tenant-b"}, id="scope-moved"),
        pytest.param({"authorization_policy_pin": "authpol-2"}, id="policy-repinned"),
    ],
)
def test_a_revoked_grant_refuses_even_for_the_same_principal_ref(
    revoked: dict[str, object],
) -> None:
    """**The load-bearing one.** Same ``principal_ref``, different entitlement.

    This is the case a naive binding misses: comparing ``principal_ref`` would
    match, and the contract would resume for somebody who has since lost the
    access it was issued under. The fingerprint covers the whole resolved context,
    so each of these five changes produces a different digest.
    """
    principal = RESOLVED_PRINCIPAL.model_copy(update=revoked)
    assert principal.principal_ref == RESOLVED_PRINCIPAL.principal_ref
    assert _refusal(contract=_contract(), principal=principal).code is (
        Code.CLARIFICATION_CONTEXT_MISMATCH
    )


def test_a_changed_principal_type_refuses_too() -> None:
    """Separated from the sweep because the preflight also has an opinion here.

    A caller whose *supplied* type disagrees with the resolved one is asserting
    authorization and is refused before this file's binding is reached. Supplying
    a matching type isolates the binding: same ref, same grants, different type,
    different fingerprint.
    """
    service = RESOLVED_PRINCIPAL.model_copy(
        update={"principal_type": PrincipalType.SERVICE_PRINCIPAL}
    )
    assert _refusal(contract=_contract(), principal=service).code is (
        Code.CLARIFICATION_CONTEXT_MISMATCH
    )


# --- condition 5: the governed world moved ---------------------------------------


@pytest.mark.parametrize(
    "moved",
    [
        pytest.param({"catalog_release": "r-2"}, id="release-published"),
        pytest.param({"policy_version": "pol-2"}, id="policy-superseded"),
        pytest.param({"vocabulary_version": "voc-2"}, id="vocabulary-superseded"),
    ],
)
def test_a_superseded_governing_version_refuses(moved: dict[str, str]) -> None:
    """Never re-pinned to current, and reported as a **context mismatch**.

    Re-pinning was the tempting alternative and is exactly wrong: it would
    reinterpret the caller's earlier question under rules that arrived afterwards and
    present the result as a continuation of what they asked.

    The code is the governed mismatch category rather than a version-specific one. A
    distinct code here would let a caller subtract version moves from the set and
    learn that a remaining mismatch is a principal fact — about themselves or about
    whoever the contract belongs to.
    """
    in_force = GoverningVersions(
        catalog_release=moved.get("catalog_release", "r-1"),
        policy_version=moved.get("policy_version", "pol-1"),
        vocabulary_version=moved.get("vocabulary_version", "voc-1"),
    )
    assert _refusal(contract=_contract(), in_force=in_force).code is (
        Code.CLARIFICATION_CONTEXT_MISMATCH
    )


# --- the four codes are four ------------------------------------------------------


def test_each_condition_has_its_governed_code() -> None:
    """**The governed grain, asserted in one place.**

    Six resumption conditions, **three** codes. Exhaustion is absent on purpose: it is
    enforced at issuance, so it is not a resumption outcome at all.

    Stated on its own because every assertion above only checks its own condition. A
    collapse — expiry folded into mismatch, say — would pass all of them individually
    and would only be visible here. So would a *split*, which is the direction that
    breaks disclosure symmetry.
    """
    codes = {
        "expired": _refusal(contract=_contract(), at=ISSUED_AT + EXPIRY).code,
        "foreign": _refusal(contract=_contract(), principal=OTHER_PRINCIPAL).code,
        "unentitled": _refusal(
            contract=_contract(),
            principal=RESOLVED_PRINCIPAL.model_copy(update={"granted_access_tags": frozenset()}),
        ).code,
        "superseded": _refusal(
            contract=_contract(),
            in_force=GoverningVersions(
                catalog_release="r-2", policy_version="pol-1", vocabulary_version="voc-1"
            ),
        ).code,
        "tampered": _refusal(
            contract=_contract(rounds_consumed=1, round_bound=2).model_copy(
                update={"round_bound": 9}
            )
        ).code,
    }
    # Expiry and tampering are not principal facts, so they carry their own codes.
    assert codes["expired"] is Code.CLARIFICATION_EXPIRED
    assert codes["tampered"] is Code.CLARIFICATION_TAMPERED

    # Everything about "the context this contract was issued into no longer holds"
    # shares **one** governed category. Splitting any of these would leak which
    # internal binding moved: distinguishing foreign from unentitled discloses whose
    # grants changed, and distinguishing superseded from either lets a caller subtract
    # version moves and learn that the remainder is a principal fact.
    assert (
        codes["foreign"]
        is codes["unentitled"]
        is codes["superseded"]
        is Code.CLARIFICATION_CONTEXT_MISMATCH
    )

    assert len(set(codes.values())) == 3, codes


# --- the mismatch category is disclosure-symmetric -------------------------------


def test_every_context_mismatch_produces_a_byte_identical_refusal() -> None:
    """**The reason the category is one category.**

    Five conditions, one response. Compared byte-for-byte rather than by code, because
    a shared code with differing messages is the same oracle arriving one field over:
    iterate the conditions, read which refusals differ, and learn whose grants moved.

    The five deliberately span both kinds of fact — two about *who is asking* (a
    foreign contract, a revoked grant) and three about *what the world looks like* (a
    moved release, policy, vocabulary). If the version moves were distinguishable, a
    caller could subtract them and learn that the remainder is a principal fact.
    """
    responses = {
        "foreign": _refusal(contract=_contract(), principal=OTHER_PRINCIPAL),
        "tag-withdrawn": _refusal(
            contract=_contract(),
            principal=RESOLVED_PRINCIPAL.model_copy(
                update={"granted_access_tags": frozenset[str]()}
            ),
        ),
        "release-moved": _refusal(
            contract=_contract(),
            in_force=GoverningVersions(
                catalog_release="r-2", policy_version="pol-1", vocabulary_version="voc-1"
            ),
        ),
        "policy-moved": _refusal(
            contract=_contract(),
            in_force=GoverningVersions(
                catalog_release="r-1", policy_version="pol-2", vocabulary_version="voc-1"
            ),
        ),
        "vocabulary-moved": _refusal(
            contract=_contract(),
            in_force=GoverningVersions(
                catalog_release="r-1", policy_version="pol-1", vocabulary_version="voc-2"
            ),
        ),
    }

    rendered = {
        name: f"{refusal.code.value}|{refusal}".encode() for name, refusal in responses.items()
    }
    assert len(set(rendered.values())) == 1, sorted(rendered)


def test_no_mismatch_refusal_names_the_binding_that_moved() -> None:
    """And none of the five carries an identifier a caller could read the answer off.

    The byte-identity above already forecloses this — five identical strings cannot each
    name their own binding. Stated separately so a future edit that made all five name
    *the same* thing would fail here rather than pass the equality check.
    """
    refusal = _refusal(
        contract=_contract(),
        in_force=GoverningVersions(
            catalog_release="r-2", policy_version="pol-2", vocabulary_version="voc-2"
        ),
    )
    message = str(refusal)
    for leaked in (
        "r-1",
        "r-2",
        "pol-1",
        "pol-2",
        "voc-1",
        "voc-2",
        "p-1",
        "p-2",
        "tenant-a",
        "authpol-1",
        "installs:read",
        "catalog_release",
        "policy_version",
        "vocabulary_version",
        "granted_access_tags",
        "principal_ref",
    ):
        assert leaked not in message, leaked


# --- replay: the stated limitation, not a claim ----------------------------------


def test_the_same_contract_validates_twice_inside_its_window() -> None:
    """**Stateless, so there is no consumption.** Asserted rather than hidden.

    A suite that omitted this would leave a reader assuming single-use. Resumed
    three times, all succeeding — which is the honest behaviour and the reason the
    limitation below is disclosed.
    """
    contract = _contract()
    for _ in range(3):
        assert _resume(contract) is contract


def test_the_posture_names_what_is_not_enforced() -> None:
    """`FR-080`'s disclosure, as a value on the response.

    ``consumption_detected`` is permanently ``False`` and is *present* rather than
    omitted, so a caller reading the field sees the answer rather than the absence
    of the question.
    """
    posture = replay_posture()
    assert posture.consumption_detected is False
    assert posture.unenforceable == UNENFORCEABLE_WITHOUT_STATE
    assert posture.enforced == ENFORCED_CONTROLS
    assert posture.limitation_code == REPLAY_LIMITATION_CODE
    assert "single_use_consumption" in posture.unenforceable
    assert "cross_process_replay_detection" in posture.unenforceable


def test_the_enforced_and_unenforceable_sets_are_disjoint() -> None:
    """A control claimed in both places would be a claim and a disclaimer at once."""
    assert not set(ENFORCED_CONTROLS) & set(UNENFORCEABLE_WITHOUT_STATE)
    assert ENFORCED_CONTROLS
    assert UNENFORCEABLE_WITHOUT_STATE


def test_the_posture_cannot_be_mutated_by_a_caller() -> None:
    """A frozen value, and a fresh one per call.

    A module-level constant handed out by reference could be edited by one caller
    and read as governed truth by the next.
    """
    posture = replay_posture()
    with pytest.raises((AttributeError, TypeError)):
        posture.consumption_detected = True  # pyright: ignore[reportAttributeAccessIssue]


def test_nothing_claims_single_use() -> None:
    """The absence, asserted where somebody would add the claim."""
    from analytics_interaction.clarification import replay as module

    assert "single_use_consumption" not in ENFORCED_CONTROLS
    assert not [name for name in module.__all__ if "consume" in name.lower()]


# --- the shipped state ----------------------------------------------------------


@pytest.mark.parametrize(
    "condition",
    [
        pytest.param({}, id="live"),
        pytest.param({"at": ISSUED_AT + EXPIRY + timedelta(hours=1)}, id="expired"),
    ],
)
def test_the_shipped_state_resumes_nothing(condition: dict[str, object]) -> None:
    """**`D-21` is undeclared, so no contract resumes — live or expired.**

    The capability gate runs before expiry, so both report the unavailable
    capability rather than the condition. That ordering is correct: a build that
    cannot verify a seal cannot establish that the contract is the one it issued,
    and reporting "expired" would imply it had.
    """
    refusal = _refusal(
        contract=_contract(),
        records=unready_records(InteractionCapability.D_21),
        **condition,  # pyright: ignore[reportArgumentType]
    )
    assert refusal.code is Code.CLARIFICATION_UNAVAILABLE
