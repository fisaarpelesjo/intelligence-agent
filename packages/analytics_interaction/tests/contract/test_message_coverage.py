"""Message-coverage build gate — T025 (FR-044; SC-028).

**No orphan code, no orphan message.** A consumer-reachable code with no
effective wording fails the build, following `001`'s `FR-074`. Discovering it at
lookup time would mean discovering it while a user was already being refused —
and the fallback at that moment would have to be a generated sentence, which is
exactly the free-form narration this feature exists to remove.

The gate also enforces the two disclosure rules the wording itself carries, and
the interpolation allowlist. Those are content properties, so they are checked
against the authored document rather than asserted about the code that reads it.

**This file claims nothing about the Portuguese being correct.** Presence,
coverage, stability and safety only; linguistic correctness stays the `D-10` /
`001:T117` reviewer duty (`FR-044`). A test asserting otherwise would read as a
claim nobody made.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.messages.registry import (
    MessageRegistry,
    load_registry,
    message_for,
    registry_path,
)

pytestmark = pytest.mark.contract

REGISTRY = load_registry()
DOCUMENT = yaml.safe_load(registry_path("pt-BR").read_text(encoding="utf-8"))
ALLOWED = frozenset(DOCUMENT["allowed_arguments"])


# --- coverage in both directions ----------------------------------------------


def test_every_code_has_governed_wording() -> None:
    missing = sorted(c.value for c in InterpretationReasonCode if c not in REGISTRY.codes)
    assert not missing, f"codes with no message: {missing}"


def test_no_message_exists_for_a_code_that_does_not() -> None:
    """An orphan message is wording nobody can ever be shown.

    Enforced at load time by rejecting a non-member code, so this asserts the
    registry's own view matches the enum exactly rather than merely covering it.
    """
    assert REGISTRY.codes == frozenset(InterpretationReasonCode)


def test_removing_one_message_fails_the_gate(tmp_path: Path) -> None:
    """The gate must fail on a real gap, not merely pass on a complete registry."""
    document = dict(DOCUMENT)
    document["messages"] = DOCUMENT["messages"][1:]
    target = tmp_path / "pt-br.yaml"
    target.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ValueError, match="declares no wording"):
        load_registry("pt-BR", path=target)


def test_a_message_for_an_unknown_code_fails_the_gate(tmp_path: Path) -> None:
    document = dict(DOCUMENT)
    document["messages"] = [
        *DOCUMENT["messages"],
        {"code": "NOT_A_GOVERNED_CODE", "language": "pt-BR", "text": "x"},
    ]
    target = tmp_path / "pt-br.yaml"
    target.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ValueError, match="not an interpretation code"):
        load_registry("pt-BR", path=target)


def test_a_duplicated_code_fails_the_gate(tmp_path: Path) -> None:
    """Two wordings for one code means neither is authoritative."""
    document = dict(DOCUMENT)
    document["messages"] = [*DOCUMENT["messages"], DOCUMENT["messages"][0]]
    target = tmp_path / "pt-br.yaml"
    target.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ValueError, match="worded more than once"):
        load_registry("pt-BR", path=target)


# --- stability ----------------------------------------------------------------


@pytest.mark.parametrize("code", list(InterpretationReasonCode))
def test_the_same_key_returns_byte_identical_text(code: InterpretationReasonCode) -> None:
    assert message_for(code) == message_for(code)
    assert message_for(code).encode("utf-8") == REGISTRY.text_for(code).encode("utf-8")


def test_two_independent_loads_agree_byte_for_byte() -> None:
    """Determinism must survive a fresh load, not only a cached lookup."""
    again = load_registry()
    for code in InterpretationReasonCode:
        assert again.text_for(code) == REGISTRY.text_for(code)


# --- safety of the wording ----------------------------------------------------


@pytest.mark.parametrize("code", list(InterpretationReasonCode))
def test_no_message_interpolates_outside_the_allowlist(code: InterpretationReasonCode) -> None:
    outside = sorted(set(REGISTRY.arguments_for(code)) - ALLOWED)
    assert not outside, f"{code.value} interpolates {outside}"


def test_the_allowlist_admits_no_value_bearing_field() -> None:
    """The allowlist is the mechanism, so its membership is the thing to check.

    A metric value, a filter value, a credential or a span of the question can
    never be interpolated — which is only true while no such field is allowed.
    """
    forbidden_stems = ("value", "text", "question", "token", "credential", "secret", "row", "cell")
    offenders = [name for name in ALLOWED if any(stem in name.lower() for stem in forbidden_stems)]
    assert not offenders, f"the allowlist admits value-bearing fields: {offenders}"


def test_the_structural_limit_message_names_no_number() -> None:
    """Step 1 precedes the authorization-context preflight.

    Naming the governed bound there would disclose policy to a caller not yet
    proven entitled to hear it (`intake-contract.md` §6). Checked as "no digits,
    no interpolation" rather than "not the governed number", because the
    governed number does not exist yet and the rule must hold once it does.
    """
    text = REGISTRY.text_for(InterpretationReasonCode.QUESTION_EXCEEDS_STRUCTURAL_LIMIT)
    assert not re.search(r"\d", text), f"the structural refusal names a number: {text!r}"
    assert REGISTRY.arguments_for(InterpretationReasonCode.QUESTION_EXCEEDS_STRUCTURAL_LIMIT) == ()


def test_the_governed_limit_message_may_name_its_limit() -> None:
    """Step 4 is after the preflight, so disclosure is permitted there.

    Asserted so the pair reads as a deliberate asymmetry rather than an
    oversight in one of the two.
    """
    assert REGISTRY.arguments_for(InterpretationReasonCode.QUESTION_EXCEEDS_GOVERNED_LIMIT) == (
        "governed_limit",
    )


def test_the_not_governed_message_discloses_no_authorization_filtering() -> None:
    """`FR-050`: "not governed" and "filtered away" must be indistinguishable.

    The wording is where that property lives — a message mentioning permission,
    access or authorization would tell an unauthorized caller that something is
    there.
    """
    text = REGISTRY.text_for(InterpretationReasonCode.TERM_NOT_GOVERNED).lower()
    for leak in ("permiss", "autoriz", "acesso", "restrit", "oculto"):
        assert leak not in text, f"the not-governed wording leaks {leak!r}: {text!r}"


def test_the_injection_refusal_does_not_echo_the_refused_content() -> None:
    """`FR-045`: the content is never reproduced, in any channel."""
    assert REGISTRY.arguments_for(InterpretationReasonCode.INSTRUCTION_INJECTION_REFUSED) == ()


def test_the_registry_declares_no_seal_key_or_credential() -> None:
    """Nothing anywhere in this feature carries key material."""
    serialised = registry_path("pt-BR").read_text(encoding="utf-8").lower()
    for forbidden in ("private_key", "secret", "api_key", "bearer ", "-----begin"):
        assert forbidden not in serialised


def test_the_registry_is_immutable_once_constructed() -> None:
    assert isinstance(REGISTRY, MessageRegistry)
    with pytest.raises(AttributeError):
        REGISTRY.unexpected = 1  # type: ignore[attr-defined]
