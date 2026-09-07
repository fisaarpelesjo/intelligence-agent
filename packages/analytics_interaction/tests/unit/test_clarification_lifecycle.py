"""The clarification lifecycle — T122 (FR-015, FR-017, FR-018, FR-081, FR-082).

    Evidence: a guessed resolution fails the test; an implementation of the
    future store fails the boundary assertion. — `tasks.md` T122

Four claims, and the first is the one the whole subsystem exists for:

* **unresolved and multi-candidate slots clarify rather than guess.** A guessed
  resolution produces a confident answer to a question nobody asked, and the
  reader cannot tell;
* **reaching the round bound abstains** — reached, not violated;
* **a reply is re-interpreted with no elevated trust**, so a reply introducing a
  new metric, period or filter is a new question;
* **the future store declares types only**, and the semantics it must preserve
  are pinned now rather than negotiated later.

Also here: the seal-coverage inventory and the field-by-field tamper matrix. Every
covered field is mutated in turn and every mutation must invalidate the seal —
one "a tampered contract refuses" case would pass while thirteen fields were
uncovered, and the uncovered ones would be exactly the fields worth changing.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from analytics_interaction.clarification import future_store
from analytics_interaction.clarification.candidates import (
    NOT_GOVERNED_DETAIL,
    governed_candidates,
    not_governed,
)
from analytics_interaction.clarification.future_store import (
    INVARIANT_SEMANTICS,
    STORE_MUST_NEVER_OWN,
    STORE_WOULD_OWN,
    ConversationStore,
)
from analytics_interaction.clarification.replay import (
    ENFORCED_CONTROLS,
    REPLAY_LIMITATION_CODE,
    UNENFORCEABLE_WITHOUT_STATE,
    replay_posture,
)
from analytics_interaction.clarification.reply import ClarificationReply, apply_reply
from analytics_interaction.clarification.seal import (
    SEALED_FIELDS,
    canonical_preimage,
    verify_seal,
)
from analytics_interaction.compliance.gates import InteractionCapability
from analytics_interaction.contracts._base import ContractViolation, LocalizedRef
from analytics_interaction.contracts.clarification import ClarificationContract
from analytics_interaction.contracts.intent import SlotKind
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code

from ..fixtures.clarifications import (
    FIXTURE_ALGORITHM,
    FIXTURE_KEY,
    FIXTURE_KEY_ID,
    FixtureSealPort,
    candidate,
    issued_contract,
    ready_records,
)

pytestmark = pytest.mark.unit

SEALING = ready_records(InteractionCapability.D_21)
PORT = FixtureSealPort(key=FIXTURE_KEY)
FINGERPRINT = "fp-1"


def _ref(identifier: str) -> LocalizedRef:
    return LocalizedRef(code=f"candidate.{identifier}", language="pt-BR", content_version="v1")


# --- clarify rather than guess --------------------------------------------------------


def test_a_multi_candidate_slot_offers_every_candidate() -> None:
    """`FR-015`: return them, never choose among them."""
    contract = issued_contract(
        fingerprint=FINGERPRINT,
        candidates=(candidate("installs"), candidate("sessions"), candidate("opens")),
    )
    assert {c.identifier for c in contract.candidates} == {"installs", "sessions", "opens"}


def test_issuance_refuses_when_there_is_nothing_to_choose_between() -> None:
    """A contract offering no candidates is not a clarification.

    Called through ``issue_clarification`` directly rather than the fixture:
    the fixture substitutes a default pair when handed none, which is convenient
    for every other test here and would hide exactly this case.
    """
    from analytics_interaction.clarification.issue import issue_clarification

    from ..fixtures.clarifications import ISSUED_AT

    with pytest.raises(ContractViolation) as refusal:
        issue_clarification(
            correlation_id="corr-1",
            interpretation_id="interp-1",
            auth_fingerprint=FINGERPRINT,
            unresolved=SlotKind.METRIC,
            candidates=(),
            rounds_consumed=0,
            round_bound=2,
            issued_at=ISSUED_AT,
            expiry=timedelta(minutes=15),
            nonce="nonce-1",
            catalog_release="r-1",
            policy_version="pol-1",
            vocabulary_version="voc-1",
            port=PORT,
            key_id=FIXTURE_KEY_ID,
            algorithm=FIXTURE_ALGORITHM,
            records=SEALING,
        )
    assert refusal.value.code is Code.CLARIFICATION_REQUIRED


def test_candidate_ordering_is_deterministic() -> None:
    """Two identical questions produce byte-identical contracts.

    A seal computed over a differently-ordered candidate list is a different
    seal, so ordering is not cosmetic here — it is part of what is signed.
    """
    forward = governed_candidates(
        [("sessions", _ref("sessions")), ("installs", _ref("installs"))], slot=SlotKind.METRIC
    )
    reversed_ = governed_candidates(
        [("installs", _ref("installs")), ("sessions", _ref("sessions"))], slot=SlotKind.METRIC
    )
    assert [c.identifier for c in forward] == ["installs", "sessions"]
    assert forward == reversed_


def test_an_emptied_candidate_set_is_byte_identical_to_not_governed() -> None:
    """`FR-019`: filtering is never signalled.

    "You may not see the three that matched" tells an unauthorized caller the
    term exists, resolves, and how many things it resolves to. Repeated across a
    vocabulary, that maps the catalog from outside.
    """
    with pytest.raises(ContractViolation) as filtered:
        governed_candidates([], slot=SlotKind.METRIC)

    unmatched = not_governed()
    assert filtered.value.code is unmatched.code
    assert filtered.value.detail == unmatched.detail == NOT_GOVERNED_DETAIL


def test_a_duplicated_candidate_refuses_rather_than_collapsing() -> None:
    """Deduplicating would narrow the choice that was actually ambiguous."""
    with pytest.raises(ContractViolation) as refusal:
        governed_candidates(
            [("installs", _ref("installs")), ("installs", _ref("installs"))], slot=SlotKind.METRIC
        )
    assert refusal.value.code is Code.INTENT_AMBIGUOUS


# --- the seal covers every field ------------------------------------------------------


def test_the_sealed_field_set_is_derived_from_the_contract() -> None:
    """Not a list. A field added upstream joins the preimage automatically."""
    declared = set(ClarificationContract.model_fields) - {"seal"}
    assert set(SEALED_FIELDS) == declared
    assert len(SEALED_FIELDS) == 14


def test_the_preimage_covers_the_key_and_the_algorithm() -> None:
    """A contract resealed under another key, or a downgraded algorithm, differs."""
    contract = issued_contract(fingerprint=FINGERPRINT)
    base = canonical_preimage(contract, key_id=FIXTURE_KEY_ID, algorithm=FIXTURE_ALGORITHM)

    assert base != canonical_preimage(contract, key_id="other", algorithm=FIXTURE_ALGORITHM)
    assert base != canonical_preimage(contract, key_id=FIXTURE_KEY_ID, algorithm="other")


def test_the_preimage_is_deterministic() -> None:
    contract = issued_contract(fingerprint=FINGERPRINT)
    first = canonical_preimage(contract, key_id=FIXTURE_KEY_ID, algorithm=FIXTURE_ALGORITHM)
    second = canonical_preimage(contract, key_id=FIXTURE_KEY_ID, algorithm=FIXTURE_ALGORITHM)
    assert first == second


def test_a_valid_contract_verifies() -> None:
    """The control. Without it, a verifier that always refused would pass below."""
    verify_seal(issued_contract(fingerprint=FINGERPRINT), port=PORT, records=SEALING)


TAMPERINGS: dict[str, object] = {
    "contract_version": 2,
    "correlation_id": "corr-2",
    "interpretation_id": "interp-2",
    "auth_fingerprint": "fp-2",
    "unresolved": SlotKind.DIMENSION,
    "candidates": (candidate("opens"),),
    "rounds_consumed": 1,
    "round_bound": 9,
    "issued_at": datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
    "expires_at": datetime(2026, 8, 13, 23, 0, tzinfo=UTC),
    "nonce": "nonce-2",
    "catalog_release": "r-2",
    "policy_version": "pol-2",
    "vocabulary_version": "voc-2",
}


def test_every_sealed_field_has_a_tampering_case() -> None:
    """The matrix is complete, asserted against the derived field set.

    A field added to the contract without a case here would be one the tamper
    matrix silently stopped covering.
    """
    assert set(TAMPERINGS) == set(SEALED_FIELDS)


@pytest.mark.parametrize("field", sorted(TAMPERINGS), ids=sorted(TAMPERINGS))
def test_mutating_any_covered_field_invalidates_the_seal(field: str) -> None:
    """Fourteen fields, fourteen cases. **The expiry and the rounds especially.**

    Those two are what an attacker actually wants: a longer window and another
    round. A subset seal tends to omit them last, so each is asserted by name
    rather than by a representative case.
    """
    contract = issued_contract(fingerprint=FINGERPRINT)
    tampered = contract.model_copy(update={field: TAMPERINGS[field]})

    with pytest.raises(ContractViolation) as refusal:
        verify_seal(tampered, port=PORT, records=SEALING)
    assert refusal.value.code is Code.CLARIFICATION_TAMPERED


def test_swapping_the_seal_from_another_contract_refuses() -> None:
    """A valid seal over a different contract is still tampering."""
    first = issued_contract(fingerprint=FINGERPRINT, nonce="nonce-a")
    second = issued_contract(fingerprint=FINGERPRINT, nonce="nonce-b")

    grafted = first.model_copy(update={"seal": second.seal})
    with pytest.raises(ContractViolation):
        verify_seal(grafted, port=PORT, records=SEALING)


def test_a_seal_from_another_key_refuses() -> None:
    """Verification rebuilds the preimage from the submitted seal's own key id."""
    contract = issued_contract(fingerprint=FINGERPRINT, port=FixtureSealPort(key="another-key"))
    with pytest.raises(ContractViolation):
        verify_seal(contract, port=PORT, records=SEALING)


def test_an_extra_field_cannot_be_added_to_a_contract() -> None:
    """``extra="forbid"``: a smuggled field has nowhere to land."""
    with pytest.raises(ValueError, match="extra"):
        issued_contract(fingerprint=FINGERPRINT).model_copy(
            update={"elevated": True}
        ).model_validate(
            {**issued_contract(fingerprint=FINGERPRINT).model_dump(), "elevated": True}
        )


# --- a reply is a question ------------------------------------------------------------


def test_a_valid_selection_returns_the_governed_identifier() -> None:
    contract = issued_contract(fingerprint=FINGERPRINT)
    reply = ClarificationReply(slot=SlotKind.METRIC, identifier="installs")
    assert apply_reply(contract, reply) == "installs"


@pytest.mark.parametrize("identifier", ["revenue", "INSTALLS", "installs ", "", "opens"])
def test_a_foreign_or_fabricated_selection_refuses(identifier: str) -> None:
    """Exact matching. A normalisation here would reopen a closed set.

    ``"INSTALLS"`` and ``"installs "`` are included deliberately: a case-folding
    or trimming lookup would accept them, and accepting an identifier by
    repairing it is how a closed set stops being closed.
    """
    contract = issued_contract(fingerprint=FINGERPRINT)
    if not identifier:
        with pytest.raises(ValueError, match="at least 1"):
            ClarificationReply(slot=SlotKind.METRIC, identifier=identifier)
        return

    reply = ClarificationReply(slot=SlotKind.METRIC, identifier=identifier)
    with pytest.raises(ContractViolation) as refusal:
        apply_reply(contract, reply)
    assert refusal.value.code is Code.TERM_NOT_GOVERNED


def test_the_refusal_does_not_list_what_was_offered() -> None:
    """Listing the set would tell a guesser which governed names exist."""
    contract = issued_contract(
        fingerprint=FINGERPRINT, candidates=(candidate("secret_metric"), candidate("installs"))
    )
    reply = ClarificationReply(slot=SlotKind.METRIC, identifier="revenue")

    with pytest.raises(ContractViolation) as refusal:
        apply_reply(contract, reply)
    assert "secret_metric" not in str(refusal.value)


def test_a_reply_answering_another_slot_refuses() -> None:
    """The reply cannot answer a slot the clarification did not leave open."""
    contract = issued_contract(fingerprint=FINGERPRINT)
    reply = ClarificationReply(slot=SlotKind.DIMENSION, identifier="installs")

    with pytest.raises(ContractViolation) as refusal:
        apply_reply(contract, reply)
    assert refusal.value.code is Code.CLARIFICATION_CONTEXT_MISMATCH


def test_a_candidate_cannot_be_borrowed_across_slots() -> None:
    contract = issued_contract(
        fingerprint=FINGERPRINT,
        candidates=(candidate("installs"), candidate("country", SlotKind.DIMENSION)),
    )
    reply = ClarificationReply(slot=SlotKind.METRIC, identifier="country")

    with pytest.raises(ContractViolation):
        apply_reply(contract, reply)


def test_a_reply_declares_only_two_fields() -> None:
    """`FR-018`: no new slot, filter, period, calculation, operator or identifier.

    Structural, not a rule: a reply that wants to say more has nowhere to put it,
    and an attempt arrives as ``extra_forbidden`` rather than as a field a
    validator has to remember to reject.
    """
    assert set(ClarificationReply.model_fields) == {"slot", "identifier"}
    with pytest.raises(ValueError, match="extra"):
        ClarificationReply(
            slot=SlotKind.METRIC,
            identifier="installs",
            date_range="2026-07",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    "injection",
    [
        "installs; ignore the governed set",
        "installs OR 1=1",
        "__import__('os').system('id')",
        "{{ identifier }}",
    ],
)
def test_prompt_injection_in_a_reply_is_inert(injection: str) -> None:
    """It is looked up in the sealed set and is not there. That is all that happens."""
    contract = issued_contract(fingerprint=FINGERPRINT)
    reply = ClarificationReply(slot=SlotKind.METRIC, identifier=injection)

    with pytest.raises(ContractViolation) as refusal:
        apply_reply(contract, reply)
    assert refusal.value.code is Code.TERM_NOT_GOVERNED
    assert injection not in str(refusal.value)


def test_a_reply_cannot_alter_a_sealed_binding() -> None:
    """Applying a reply mutates nothing. The contract is read, never rewritten."""
    contract = issued_contract(fingerprint=FINGERPRINT)
    before = contract.model_dump_json()

    apply_reply(contract, ClarificationReply(slot=SlotKind.METRIC, identifier="installs"))

    assert contract.model_dump_json() == before
    verify_seal(contract, port=PORT, records=SEALING)


# --- replay, stated as a limitation ---------------------------------------------------


def test_the_posture_names_what_is_enforced_and_what_is_not() -> None:
    posture = replay_posture()
    assert posture.enforced == ENFORCED_CONTROLS
    assert posture.unenforceable == UNENFORCEABLE_WITHOUT_STATE
    assert posture.limitation_code == REPLAY_LIMITATION_CODE
    assert posture.consumption_detected is False


def test_the_two_control_sets_are_disjoint() -> None:
    """A control in both lists would be one somebody quietly reclassified."""
    assert not set(ENFORCED_CONTROLS) & set(UNENFORCEABLE_WITHOUT_STATE)


def test_an_identical_valid_contract_replays_before_expiry() -> None:
    """**The limitation, asserted rather than described.**

    Verifying the same contract twice succeeds twice. Nothing observes that it
    was already resumed, and `FR-080` requires that to be a stated limitation
    rather than an implied control.
    """
    contract = issued_contract(fingerprint=FINGERPRINT)

    verify_seal(contract, port=PORT, records=SEALING)
    verify_seal(contract, port=PORT, records=SEALING)

    assert replay_posture().consumption_detected is False


def test_no_replay_cache_nonce_registry_or_store_exists() -> None:
    """A control that works only when a process happens to remember is worse
    than a stated limitation, because it is relied upon rather than reasoned about.
    """
    from analytics_interaction import clarification

    root = Path(inspect.getfile(clarification)).resolve().parent
    forbidden = {"lru_cache", "cache", "cached_property", "Redis", "connect", "execute", "session"}
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                name, line = node.attr, node.lineno
            elif isinstance(node, ast.Name):
                name, line = node.id, node.lineno
            else:
                continue
            if name in forbidden:
                offenders.append(f"{path.name}:{line} {name}")
    assert not offenders, f"a replay cache or store appears: {offenders}"


def test_no_module_level_mutable_state_in_the_clarification_package() -> None:
    """A module-level set is where a nonce registry would live."""
    from analytics_interaction import clarification

    root = Path(inspect.getfile(clarification)).resolve().parent
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            if isinstance(node.value, ast.List | ast.Dict | ast.Set):
                targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
                names = [ast.unparse(target) for target in targets]
                if names != ["__all__"]:
                    offenders.append(f"{path.name}: {names}")
    assert not offenders, f"module-level mutable state: {offenders}"


# --- the future store is declared, not built -------------------------------------------


def test_the_store_is_a_protocol_with_no_implementation() -> None:
    """`NG-17`, amended by `OD-69` (2026-08-31): TWO protocols now, still zero implementations.

    The owner opened the boundary for `011`'s memory, THROUGH the contract: `ConversationMemory`
    joined `ConversationStore` in the boundary module. What did not change is what this node
    actually guards — **no implementation lives in this package**. The implementation is `011`'s,
    behind the seam, where its own fourteen nodes drive it.
    """
    source = Path(inspect.getfile(future_store)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert {node.name for node in classes} == {"ConversationStore", "ConversationMemory"}
    for declared in classes:
        assert any("Protocol" in ast.unparse(base) for base in declared.bases), declared.name

    for node in ast.walk(classes[0]):
        if isinstance(node, ast.FunctionDef):
            body = [stmt for stmt in node.body if not isinstance(stmt, ast.Expr)]
            assert (
                all(isinstance(stmt, ast.Pass | ast.Expr) for stmt in body)
                or body == [ast.parse("...").body[0]]
                or all(isinstance(stmt, ast.Expr) for stmt in node.body)
            )


def test_the_store_module_imports_no_database_or_driver() -> None:
    """No PostgreSQL, no schema, no migration, no connection.

    Amended by `OD-69` (2026-08-31): `collections.abc` and `datetime` joined the permitted set —
    both TYPE_CHECKING-only, both for `ConversationMemory`'s structured signatures. Still no
    database, no driver, no runtime dependency of any kind.
    """
    source = Path(inspect.getfile(future_store)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported == {"__future__", "typing", "collections.abc", "datetime"}


def test_the_store_boundary_names_what_it_may_and_may_not_own() -> None:
    """`FR-082`: the prohibitions apply in advance, to a component nobody wrote."""
    assert "single_use_consumption_records" in STORE_WOULD_OWN
    assert set(STORE_MUST_NEVER_OWN) == {
        "raw_question_text",
        "free_text_clarification_replies",
        "metric_values",
        "filter_values",
    }
    assert not set(STORE_WOULD_OWN) & set(STORE_MUST_NEVER_OWN)


def test_the_store_declares_no_method_that_could_take_custody_of_content() -> None:
    """A method that could accept question text is one somebody eventually calls.

    Amended by `OD-69`: `ConversationMemory` exists and its signatures are the `FR-082`
    enforcement — structured identifiers, descriptors and field NAMES, with no parameter a raw
    question, a reply or a value could travel in. Both protocols are held to the same forbidden
    set, and the memory's parameter set is pinned exactly so a content-shaped parameter cannot be
    added quietly.
    """
    from analytics_interaction.clarification.future_store import ConversationMemory

    methods = {name for name in dir(ConversationStore) if not name.startswith("_")}
    assert methods == {"record_consumption", "consumed"}

    forbidden = {"question", "text", "reply", "value", "values", "payload", "content"}
    for name in methods:
        parameters = set(inspect.signature(getattr(ConversationStore, name)).parameters)
        assert not parameters & forbidden

    memory_methods = {name for name in dir(ConversationMemory) if not name.startswith("_")}
    assert memory_methods == {"remember_turn", "remembered_window"}
    for name in memory_methods:
        parameters = set(inspect.signature(getattr(ConversationMemory, name)).parameters)
        assert not parameters & forbidden
    assert set(inspect.signature(ConversationMemory.remember_turn).parameters) == {
        "self",
        "identity",
        "scope",
        "message_id",
        "intent",
        "metric_ids",
        "period",
        "filter_fields",
        "instant",
    }


def test_the_semantics_the_store_must_preserve_are_pinned_now() -> None:
    """`SC-045`. Adding the store must change *where* a fact is checked, never
    *what* it means — and a promise pinned after the fact is a negotiation.
    """
    assert set(INVARIANT_SEMANTICS) == {
        "contract_field_meanings",
        "governed_reason_codes",
        "refusal_conditions",
        "seal_coverage",
        "identity_binding",
        "expiry_semantics",
    }


def test_each_pinned_semantic_is_observable_today() -> None:
    """Otherwise the list is a wish rather than a baseline.

    Each entry names something this suite already asserts, so the day the store
    lands the same assertions say whether it kept its promises.
    """
    contract = issued_contract(fingerprint=FINGERPRINT)

    # contract_field_meanings + seal_coverage
    assert set(SEALED_FIELDS) == set(ClarificationContract.model_fields) - {"seal"}
    # identity_binding
    assert contract.auth_fingerprint == FINGERPRINT
    # expiry_semantics
    assert contract.expires_at > contract.issued_at
    # governed_reason_codes + refusal_conditions
    with pytest.raises(ContractViolation) as refusal:
        verify_seal(contract.model_copy(update={"nonce": "other"}), port=PORT, records=SEALING)
    assert refusal.value.code is Code.CLARIFICATION_TAMPERED


def test_the_store_adds_detection_and_narrows_nothing_else() -> None:
    """The asymmetry is the point: it may narrow replay, and nothing else."""
    assert "single_use_consumption" in UNENFORCEABLE_WITHOUT_STATE
    assert "single_use_consumption_records" in STORE_WOULD_OWN
    for control in ENFORCED_CONTROLS:
        assert control not in STORE_WOULD_OWN


# --- no analytical value reaches the contract -------------------------------------------


def test_no_contract_field_can_carry_an_analytical_value() -> None:
    """Governed identifiers and enumerations only (`FR-077`).

    No result, no row, no cell, no derived figure, no SQL, no limit, no
    credential — and no free-text question or reply. The contract declares none
    of them, so none can arrive.
    """
    from decimal import Decimal

    annotations = {
        name: info.annotation for name, info in ClarificationContract.model_fields.items()
    }
    rendered = {str(annotation) for annotation in annotations.values()}
    for banned in ("AnalyticsResult", "ResultRow", "ResultCell", "DerivedFigure", "Decimal"):
        assert not any(banned in text for text in rendered), banned
    assert Decimal not in set(annotations.values())


def test_the_contract_carries_no_question_or_reply_text() -> None:
    """`FR-077`. There is no field for it, which is stronger than a rule."""
    for name in ClarificationContract.model_fields:
        assert name not in {"question", "text", "reply", "history", "transcript"}


def test_the_distinguishing_content_is_a_governed_pointer() -> None:
    """A built string would put unreviewed text into a sealed transported artifact."""
    contract = issued_contract(fingerprint=FINGERPRINT)
    for entry in contract.candidates:
        assert isinstance(entry.distinguishing, LocalizedRef)
        assert entry.distinguishing.code
        assert entry.distinguishing.content_version


def test_the_preimage_contains_no_value_beyond_the_contract() -> None:
    """The seal payload is the contract and the key identity. Nothing else."""
    contract = issued_contract(fingerprint=FINGERPRINT)
    preimage = canonical_preimage(contract, key_id=FIXTURE_KEY_ID, algorithm=FIXTURE_ALGORITHM)

    assert FIXTURE_KEY not in preimage
    for banned in ("SELECT", "rows", "cells", 'value":'):
        assert banned not in preimage


def test_the_expiry_comes_from_a_supplied_duration_not_a_default() -> None:
    """`D-19` owns the expiry. Issuance applies what it is handed."""
    short = issued_contract(fingerprint=FINGERPRINT, expiry=timedelta(minutes=5))
    long = issued_contract(fingerprint=FINGERPRINT, expiry=timedelta(hours=2))

    assert short.expires_at - short.issued_at == timedelta(minutes=5)
    assert long.expires_at - long.issued_at == timedelta(hours=2)
