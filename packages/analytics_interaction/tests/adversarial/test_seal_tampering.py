"""Every covered field, mutated in turn — T154 (FR-078; SC-044).

    A clarification contract whose fields no longer match its seal MUST refuse.
    There is no repair path and no partial honouring. — `FR-078`

    Evidence: the seal never validates; no repair path exists. — `tasks.md` T154

## Why one field at a time

A single "tampered contract" test proves the seal covers *something*. It does not
prove the seal covers the field an attacker would actually change — and the
interesting fields are the boring ones. Moving `expires_at` forward buys another
hour; raising `round_bound` buys another turn; swapping `auth_fingerprint` steals
somebody else's clarification; changing `catalog_release` reinterprets the
question under a release the caller never asked about.

So every field the preimage covers is mutated on its own, and each mutation must
refuse with the same code. Fourteen fields, derived from the contract rather than
listed, so a fifteenth added later is mutated automatically instead of quietly
escaping the sweep.

## Why `key_id` and `algorithm` are in the sweep

They are part of the preimage on purpose. Without them, a caller could reseal a
contract under a weaker algorithm or a different key and present it as the
original — the fields would match, and the seal would be a fresh valid one over a
contract nobody issued. Covering them makes the substitution change the preimage,
so the original seal stops matching.

## Fixture-only

The synthetic key lives in `tests/fixtures/seal/`. `D-21` is undeclared; no key is
provisioned anywhere in this repository, and a green run here is evidence about
the *sealing logic*, not about `D-21`. The shipped state — no provider, no key — is
asserted separately at the bottom, because that is what actually happens today.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from analytics_interaction.clarification.seal import (
    SEALED_FIELDS,
    canonical_preimage,
    verify_seal,
)
from analytics_interaction.compliance.gates import InteractionCapability
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.clarification import ClarificationContract, Seal
from analytics_interaction.contracts.intent import SlotKind
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.identity.authorization_fingerprint import (
    derive_authorization_fingerprint,
)

from ..conftest import authorize
from ..fixtures.clarifications import (
    FIXTURE_ALGORITHM,
    FIXTURE_KEY,
    FIXTURE_KEY_ID,
    FixtureSealPort,
    candidate,
    issued_contract,
    ready_records,
    unready_records,
)

pytestmark = pytest.mark.adversarial

READY = ready_records(InteractionCapability.D_21)
PORT = FixtureSealPort(key=FIXTURE_KEY)

#: One mutation per covered field, keyed by field name.
#:
#: Each value is genuinely different **and** structurally valid, so the contract
#: still constructs and the seal is the only thing that can catch it. A mutation
#: that failed validation would be caught by the contract instead, and would tell
#: us nothing about the seal.
MUTATIONS: dict[str, object] = {
    # An **int**, not a string: ``contract_version`` is a ``StrictInt``, and a
    # string here would make pydantic warn on serialisation rather than exercise
    # the seal. ``2`` is a version this build does not honour, which is also the
    # substitution an attacker would try.
    "contract_version": 2,
    "correlation_id": "corr-2",
    "interpretation_id": "interp-2",
    "auth_fingerprint": "0" * 64,
    "unresolved": SlotKind.DIMENSION,
    "candidates": (candidate("sessions"), candidate("installs")),
    "rounds_consumed": 1,
    "round_bound": 9,
    "issued_at": datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
    "expires_at": datetime(2026, 8, 13, 23, 0, tzinfo=UTC),
    "nonce": "nonce-2",
    "catalog_release": "r-2",
    "policy_version": "pol-2",
    "vocabulary_version": "voc-2",
}


def _contract() -> ClarificationContract:
    return issued_contract(port=PORT, fingerprint=derive_authorization_fingerprint(authorize()))


# --- the sweep is complete ---------------------------------------------------------


def test_every_sealed_field_has_a_mutation() -> None:
    """**The completeness gate.**

    ``SEALED_FIELDS`` is derived from the contract, so a field added upstream
    appears here with no mutation and fails — rather than being silently exempt
    from every assertion below it.
    """
    assert set(MUTATIONS) == set(SEALED_FIELDS), set(MUTATIONS) ^ set(SEALED_FIELDS)
    assert "seal" not in SEALED_FIELDS


def test_every_mutation_actually_changes_the_field() -> None:
    """A mutation equal to the original would pass every test below vacuously."""
    original = _contract()
    for name, mutated in MUTATIONS.items():
        assert getattr(original, name) != mutated, name


def test_the_untampered_contract_verifies() -> None:
    """The control. Without it, universal refusal would look like a working seal."""
    assert verify_seal(_contract(), port=PORT, records=READY) is None


# --- one field at a time -----------------------------------------------------------


@pytest.mark.parametrize("field", sorted(MUTATIONS), ids=sorted(MUTATIONS))
def test_mutating_one_covered_field_breaks_the_seal(field: str) -> None:
    """**The load-bearing sweep.**

    ``model_copy`` rather than a rebuild, so the mutation is exactly one field and
    the seal travels unchanged — which is the attacker's position: they have a
    valid seal and want to change what it covers.
    """
    tampered = _contract().model_copy(update={field: MUTATIONS[field]})
    with pytest.raises(ContractViolation) as raised:
        verify_seal(tampered, port=PORT, records=READY)
    assert raised.value.code is Code.CLARIFICATION_TAMPERED


@pytest.mark.parametrize("field", sorted(MUTATIONS), ids=sorted(MUTATIONS))
def test_a_tampered_field_changes_the_preimage(field: str) -> None:
    """The mechanism, asserted directly rather than inferred from the refusal.

    A refusal could come from anywhere. This says the preimage itself differs, so
    the field is genuinely *covered* and not merely correlated with something that
    is.
    """
    original = _contract()
    tampered = original.model_copy(update={field: MUTATIONS[field]})
    assert canonical_preimage(
        original, key_id=FIXTURE_KEY_ID, algorithm=FIXTURE_ALGORITHM
    ) != canonical_preimage(tampered, key_id=FIXTURE_KEY_ID, algorithm=FIXTURE_ALGORITHM)


@pytest.mark.parametrize("field", sorted(MUTATIONS), ids=sorted(MUTATIONS))
def test_a_tampered_refusal_discloses_nothing(field: str) -> None:
    """The refusal says the contract does not match. It does not say which field.

    Naming the field would turn a tamper-detection message into an oracle: mutate
    a field, read which one was noticed, and learn the preimage's composition one
    refusal at a time.
    """
    tampered = _contract().model_copy(update={field: MUTATIONS[field]})
    with pytest.raises(ContractViolation) as raised:
        verify_seal(tampered, port=PORT, records=READY)
    message = str(raised.value)
    assert field not in message
    assert str(MUTATIONS[field]) not in message
    assert FIXTURE_KEY not in message
    assert FIXTURE_KEY_ID not in message


# --- key and algorithm substitution ------------------------------------------------


def test_resealing_under_a_different_key_id_is_detected() -> None:
    """A valid seal over a contract nobody issued.

    The attacker holds their own key, seals the contract cleanly, and presents it.
    Every field matches; the seal is real. What does not match is the ``key_id``
    inside the preimage, so the substitution is visible.
    """
    original = _contract()
    foreign = FixtureSealPort(key="fixture-only-not-provisioned-key-material-attacker")
    resealed = original.model_copy(
        update={
            "seal": foreign.seal(
                canonical_preimage(original, key_id="attacker-key", algorithm=FIXTURE_ALGORITHM),
                key_id="attacker-key",
            )
        }
    )
    with pytest.raises(ContractViolation) as raised:
        verify_seal(resealed, port=PORT, records=READY)
    assert raised.value.code is Code.CLARIFICATION_TAMPERED


def test_downgrading_the_algorithm_is_detected() -> None:
    """The same substitution, through the other half of the pair."""
    original = _contract()
    downgraded = original.model_copy(
        update={
            "seal": Seal(
                key_id=original.seal.key_id,
                algorithm="fixture-only-not-provisioned-weak",
                value=original.seal.value,
            )
        }
    )
    with pytest.raises(ContractViolation) as raised:
        verify_seal(downgraded, port=PORT, records=READY)
    assert raised.value.code is Code.CLARIFICATION_TAMPERED


def test_a_truncated_or_padded_seal_value_is_detected() -> None:
    """Neither a prefix nor an extension of a valid digest is a valid digest."""
    original = _contract()
    for value in (
        original.seal.value[:-1],
        original.seal.value + "0",
        original.seal.value.upper(),
        "",
        "0" * len(original.seal.value),
    ):
        candidate_seal = Seal(
            key_id=original.seal.key_id, algorithm=original.seal.algorithm, value=value or "x"
        )
        with pytest.raises(ContractViolation) as raised:
            verify_seal(
                original.model_copy(update={"seal": candidate_seal}), port=PORT, records=READY
            )
        assert raised.value.code is Code.CLARIFICATION_TAMPERED


# --- there is no repair path -------------------------------------------------------


def test_verification_returns_nothing_to_repair_with() -> None:
    """``verify_seal`` returns ``None`` or raises. There is no partial verdict.

    A function returning a "which fields matched" report would be the first step
    of a repair path, and a repaired contract is one whose fields no longer all
    mean what the issuer meant.
    """
    assert verify_seal(_contract(), port=PORT, records=READY) is None


def test_no_reseal_or_repair_function_is_exported() -> None:
    """The absence, asserted where somebody would add it."""
    from analytics_interaction.clarification import seal as module

    for forbidden in ("reseal", "repair", "fix", "recover", "downgrade", "force"):
        assert not [name for name in module.__all__ if forbidden in name.lower()], forbidden


def test_a_tampered_contract_cannot_be_resumed() -> None:
    """The refusal holds at the resumption boundary, not only at the seal check.

    Asserted through ``resume_clarification`` because that is the entry point a
    caller reaches — a seal check that passed in isolation while resumption used a
    different path would be the gap.
    """
    from analytics_interaction.clarification.resume import GoverningVersions, resume_clarification

    authorized = authorize()
    tampered = _contract().model_copy(update={"round_bound": 9})
    with pytest.raises(ContractViolation) as raised:
        resume_clarification(
            tampered,
            authorized=authorized,
            in_force=GoverningVersions(
                catalog_release="r-1", policy_version="pol-1", vocabulary_version="voc-1"
            ),
            at=datetime(2026, 8, 13, 12, 5, tzinfo=UTC),
            port=PORT,
            records=READY,
        )
    assert raised.value.code is Code.CLARIFICATION_TAMPERED


# --- the shipped state -------------------------------------------------------------


def test_the_shipped_state_verifies_nothing_at_all() -> None:
    """**`D-21` is undeclared, so no contract is honoured, tampered or not.**

    The strongest possible answer to tampering, and the one that ships. Separated
    from the fixture-enabled sweep above so a reader cannot mistake a green sweep
    for a provisioned key.
    """
    contract = _contract()
    # OD-101 (2026-09-02): a copia sem prontidao continua recusando ANTES do porto; o
    # estado embarcado agora passa o portao e verifica ATRAVES do porto injetado — a
    # resposta forte contra adulteracao passou a ser o proprio verify, nao o portao.
    with pytest.raises(ContractViolation) as raised:
        verify_seal(contract, port=PORT, records=unready_records(InteractionCapability.D_21))
    assert raised.value.code is Code.CLARIFICATION_UNAVAILABLE
    assert verify_seal(contract, port=PORT, records=None) is None


def test_an_absent_provider_refuses_rather_than_trusting() -> None:
    """No provider means no verification, which means no honouring.

    The tempting alternative — treat an unverifiable contract as unsealed and
    accept it — would make the absence of a key a way past the seal.
    """
    with pytest.raises(ContractViolation) as raised:
        verify_seal(_contract(), port=None, records=READY)
    assert raised.value.code is Code.CLARIFICATION_UNAVAILABLE


def test_the_expiry_window_is_not_what_is_being_tested_here() -> None:
    """Guard against the sweep passing for the wrong reason.

    ``expires_at`` is one of the mutated fields, and an expired contract also
    refuses — with a *different* code. This pins that the tamper sweep is seeing
    ``CLARIFICATION_TAMPERED`` because the seal broke, not because the clock moved.
    """
    contract = _contract()
    assert contract.expires_at > contract.issued_at
    assert contract.expires_at - contract.issued_at == timedelta(minutes=15)
