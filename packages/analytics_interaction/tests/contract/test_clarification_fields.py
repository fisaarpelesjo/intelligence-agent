"""Clarification contract fields — T042 (FR-076, FR-077; SC-044).

Two properties.

**Every field is required.** Asserted field by field by omitting each in turn,
because an optional field inside a sealed contract is a field an attacker can
simply remove — and the seal would then cover a smaller object than the one the
issuer meant.

The authoritative enumerations in `clarification-contract.md` §2 and
`data-model.md` §5 give **fourteen content fields plus the seal — fifteen in
all**, and that is what the contract carries.

**Governed identifiers and enumerations only.** No question text, no free-text
reply content, no metric value, no filter value (`FR-077`). Enforced twice,
following the pattern `002` established for its audit event: by the declared
field set — no field *can* hold free text — and by a serialised-content scan over
a fully populated contract, which catches a value smuggled into a field whose
name sounds innocent. Either check alone misses the other's failure mode.

`D-21` is undeclared, so no real seal exists. The fixture below carries a
**structurally shaped placeholder** and nothing else: no key, no algorithm
default, no generator. Constructing a ``Seal`` here proves the contract's shape,
never that a contract could be issued — issuance is gated by `T065`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from analytics_interaction.contracts import (
    SUPPORTED_CONTRACT_VERSIONS,
    CandidateRef,
    ClarificationContract,
    LocalizedRef,
    Seal,
    SlotKind,
    build,
)
from analytics_interaction.contracts.clarification import CLARIFICATION_CONTRACT_FIELDS

pytestmark = pytest.mark.contract

ISSUED = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
EXPIRES = datetime(2026, 8, 13, 12, 10, tzinfo=UTC)

#: The fourteen content fields, transcribed from `clarification-contract.md` §2
#: and `data-model.md` §5. Every one appears in both documents and none was
#: added here; the seal is asserted alongside them below, for fifteen in all.
ENUMERATED_FIELDS = (
    "contract_version",
    "correlation_id",
    "interpretation_id",
    "auth_fingerprint",
    "unresolved",
    "candidates",
    "rounds_consumed",
    "round_bound",
    "issued_at",
    "expires_at",
    "nonce",
    "catalog_release",
    "policy_version",
    "vocabulary_version",
)


def _candidate(identifier: str = "installs") -> CandidateRef:
    return CandidateRef(
        identifier=identifier,
        slot=SlotKind.METRIC,
        distinguishing=LocalizedRef(
            code="CLARIFICATION_REQUIRED", language="pt-BR", content_version="unversioned"
        ),
    )


def _fields() -> dict[str, Any]:
    """A complete contract, with a structurally shaped placeholder seal."""
    return {
        "contract_version": 1,
        "correlation_id": "corr-1",
        "interpretation_id": "intp-1",
        "auth_fingerprint": "fp-1",
        "unresolved": SlotKind.METRIC,
        "candidates": (_candidate("installs"), _candidate("sessions")),
        "rounds_consumed": 0,
        "round_bound": 2,
        "issued_at": ISSUED,
        "expires_at": EXPIRES,
        "nonce": "n-1",
        "catalog_release": "r-1",
        "policy_version": "pol-1",
        "vocabulary_version": "voc-1",
        "seal": Seal(key_id="PLACEHOLDER", algorithm="PLACEHOLDER", value="PLACEHOLDER"),
    }


# --- every field is required --------------------------------------------------


def test_the_contract_declares_every_enumerated_field_and_nothing_else() -> None:
    """Field-for-field against the enumeration, not against the summary count.

    Asserting the tuple rather than a length means a field silently added or
    dropped fails here **by name**. A count alone would pass on a contract that
    had swapped one field for another.
    """
    assert (*ENUMERATED_FIELDS, "seal") == CLARIFICATION_CONTRACT_FIELDS
    assert len(CLARIFICATION_CONTRACT_FIELDS) == 15


def test_a_complete_contract_constructs() -> None:
    contract = build(ClarificationContract, **_fields())
    assert contract.contract_version in SUPPORTED_CONTRACT_VERSIONS


@pytest.mark.parametrize("field", CLARIFICATION_CONTRACT_FIELDS)
def test_omitting_any_field_fails_construction(field: str) -> None:
    """An optional field in a sealed contract is one an attacker can remove."""
    fields = _fields()
    del fields[field]
    with pytest.raises((ValidationError, ValueError)):
        build(ClarificationContract, **fields)


@pytest.mark.parametrize("field", CLARIFICATION_CONTRACT_FIELDS)
def test_no_field_declares_a_default(field: str) -> None:
    """A default is an omission the seal would silently cover."""
    assert ClarificationContract.model_fields[field].is_required()


def test_an_undeclared_field_is_refused() -> None:
    with pytest.raises((ValidationError, ValueError)):
        build(ClarificationContract, **_fields(), reply_text="pode ser instalações")


# --- governed identifiers and enumerations only -------------------------------


FORBIDDEN_FIELDS = (
    "text",
    "question",
    "question_text",
    "reply",
    "reply_text",
    "value",
    "filter_value",
    "metric_value",
    "note",
    "comment",
    "prompt",
)


@pytest.mark.parametrize("field", FORBIDDEN_FIELDS)
def test_the_contract_declares_no_free_text_or_value_field(field: str) -> None:
    assert field not in ClarificationContract.model_fields
    assert field not in CandidateRef.model_fields


def test_a_candidate_points_at_governed_content_rather_than_carrying_a_string() -> None:
    """`CandidateRef.distinguishing` is a pointer, never a built sentence.

    A built string would put unreviewed wording — potentially derived from the
    question — inside a sealed contract the caller transports.
    """
    annotation = CandidateRef.model_fields["distinguishing"].annotation
    assert annotation is LocalizedRef
    assert tuple(CandidateRef.model_fields) == ("identifier", "slot", "distinguishing")


def test_a_candidate_carries_a_governed_identifier_and_a_closed_slot() -> None:
    candidate = _candidate()
    assert candidate.identifier == "installs"
    assert candidate.slot in set(SlotKind)


def test_the_serialised_contract_carries_no_text_value_or_key_material() -> None:
    """The second half of the double enforcement.

    A field-set test cannot catch a value smuggled into a field whose name sounds
    innocent; a content scan over a fully populated instance can.
    """
    serialised = build(ClarificationContract, **_fields()).model_dump_json().lower()
    for forbidden in (
        "quantas",
        "instalações em julho",
        "select ",
        "password",
        "token",
        "bearer",
        "private_key",
        "-----begin",
    ):
        assert forbidden not in serialised, f"the contract carried {forbidden!r}"


def test_the_scan_would_catch_a_smuggled_span() -> None:
    """A content scan never shown to fail proves nothing about the content."""
    smuggled = build(ClarificationContract, **{**_fields(), "nonce": "quantas instalações"})
    assert "quantas" in smuggled.model_dump_json().lower()


# --- the seal boundary --------------------------------------------------------


def test_the_seal_declares_shape_and_holds_no_default_key_or_algorithm() -> None:
    """`D-21` is undeclared. A convenience default would remove the fail-closed."""
    for field in ("key_id", "algorithm", "value"):
        assert Seal.model_fields[field].is_required(), f"{field} has a default"


def test_no_module_generates_or_hardcodes_key_material() -> None:
    """Nothing invents a key while `D-21` is open.

    Scanned over the whole source tree, not just the clarification module: a
    generator anywhere would be reachable from issuance.
    """
    import inspect
    from pathlib import Path

    import analytics_interaction

    root = Path(inspect.getfile(analytics_interaction)).resolve().parent
    forbidden = (
        "secrets.token",
        "os.urandom",
        "Fernet",
        "hmac.new",
        "-----BEGIN",
        "SEAL_KEY",
        "signing_key =",
    )
    offenders = [
        f"{path.name}: {token}"
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"key material or a generator was found: {offenders}"


# --- sealed accounting --------------------------------------------------------


def test_a_contract_already_at_the_round_bound_is_not_issuable() -> None:
    """Reaching the bound is an abstention (`FR-017`), not a contract to offer."""
    with pytest.raises((ValidationError, ValueError), match="round bound is reached"):
        build(ClarificationContract, **{**_fields(), "rounds_consumed": 2, "round_bound": 2})


def test_an_expiry_that_precedes_issuance_is_refused() -> None:
    with pytest.raises((ValidationError, ValueError), match="expires_at must follow"):
        build(ClarificationContract, **{**_fields(), "expires_at": ISSUED})


def test_the_contract_is_frozen_so_a_sealed_field_cannot_be_edited_in_place() -> None:
    contract = build(ClarificationContract, **_fields())
    with pytest.raises(ValidationError):
        contract.rounds_consumed = 0  # type: ignore[misc]


def test_the_binding_is_a_pair_rather_than_an_identity_alone() -> None:
    """`002`'s security amendment, applied before the same mistake can be made.

    Identity-only keying let a differently-authorized caller attach to another
    principal's execution. Identity stays principal-independent so audit can see
    the same question asked twice; the fingerprint carries the authorization
    dimension, alongside and never folded in.
    """
    assert "interpretation_id" in ClarificationContract.model_fields
    assert "auth_fingerprint" in ClarificationContract.model_fields
    assert ClarificationContract.model_fields["auth_fingerprint"].is_required()


def test_the_contract_version_set_is_closed_and_known() -> None:
    """An unknown version refuses; it is never partially honoured."""
    assert frozenset({1}) == SUPPORTED_CONTRACT_VERSIONS
