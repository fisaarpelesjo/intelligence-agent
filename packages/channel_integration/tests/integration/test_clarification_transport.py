"""T133 — a clarification, transported in both directions and answered in neither (`SC-049`).

`FR-042`, `FR-075` to `FR-078`. The property under test is a **transport** property: what `003`'s
port returned arrives on `result.upstream` byte-identically, and no part of `004` reads, answers,
completes, pre-fills or resolves any part of it.

## What `004` actually does with a clarification, measured rather than assumed

The task text can be read as though a clarification were rendered and sent back. It is not, and the
difference matters enough to state before anything is asserted. Measured 2026-08-19:

* `outbound/render.py` exposes `render_answer(payload: GovernedAnswerPayload, ...)`, and there is
  **no clarification renderer anywhere in `src/`**. `roundtrip.handle` says so in its own docstring
  and behaves accordingly;
* `outbound/payload.py` declares the `GovernedClarificationPayload` *shape*, and that name occurs
  in exactly one module — the one that declares it. Nothing consumes it;
* so `handle` carries the object on `result.upstream`, delivers nothing, and counts one ask. The
  stage trail ends at `SUBMITTED`: `RENDERED` never fires, because rendering is never attempted;
* `ChannelReasonCode` has no clarification member at all. `004` owns no vocabulary for the concept,
  which is the strongest available form of "it decides nothing about one".

The assertions below are therefore about the transport, and everything else is asserted **as an
absence** rather than papered over with a renderer this feature was never authorized to write.

## "In both directions" — the inbound direction does not exist, and the absence is asserted

The inbound half of a clarification round trip is the question that *follows* one, carrying the
contract back so `003` can resume. `004` has no surface for that. Three measurements, in the order
a message would meet them:

* `inbound.envelope.WIRE_FIELDS` is a closed set, and it intersects the contract's fifteen fields in
  exactly one: `correlation_id` — the envelope's own identifier for the audit trail, which carries
  no contract and resumes nothing;
* a payload carrying any other key is refused, before identity, so the trail is empty, the port is
  never reached and nothing is transmitted. That is driven below;
* the intake `004` submits declares five fields — `text`, `language`, `reference_date`, `as_of`,
  `principal` — so even a contract that somehow arrived would have nowhere to go.

Closing that gap is a governed decision about where a resumption surface lives, and inventing one
here so a round-trip test could be symmetric would be this file authoring the feature it exists to
measure. What is asserted is what is true.

## Never answered, completed, pre-filled or resolved — asserted structurally, not by inspection

A test that drove one clarification and observed nothing being answered would prove one path is
clean. `SC-049` is a claim about the whole feature, so the claim is checked the way it is stated:
every module under `src/` is parsed and every attribute read is collected, and none of them may name
a field of `ClarificationContract`, `CandidateRef` or `Seal`.

Some of those names are excluded, because attribute-name matching cannot know what the receiver is
and `004` uses them for objects of its own — `correlation_id` on the envelope, `policy_version` on
the transport bounds, and so on. The exclusion is not a free pass: the set of names that actually
collide is **measured** in the same node and required to be exactly the recorded ones, so a new
collision has to be justified rather than absorbed.

## Building a real contract, and the one name that is not on the allowlist

`ClarificationContract`, `CandidateRef`, `SlotKind` and `LocalizedRef` are all on the reading list
`tests/contract/test_import_allowlist.py` enforces. **`Seal` is not.** So the seal is passed as a
plain mapping through `model_validate` and `003`'s own model validates it — the same move
`fixture_principal_context` records for `PrincipalType`, and the reason no `Seal` import appears
below. `D-21` is undeclared, so no real seal exists to construct in any case: every string here is a
fixture string and it secures nothing.

The contract is built in this file rather than in `tests/fixtures/`, because the fixture modules
carry no declared home for one and a new fixture name would have to clear
`tests/contract/test_fixture_containment.py` to serve a single caller.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from analytics_interaction.contracts import LocalizedRef
from analytics_interaction.contracts.clarification import CandidateRef, ClarificationContract
from analytics_interaction.contracts.intent import SlotKind

from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.inbound.envelope import WIRE_FIELDS
from channel_integration.roundtrip import RoundTripResult, handle
from tests.fixtures.channels import (
    AT,
    FIXTURE_BOUNDS,
    FIXTURE_MATERIAL,
    RecordingAuditSink,
    RecordingDeliveryPort,
    assert_the_production_resolver_still_refuses,
    descriptor_for,
    fixture_capabilities,
    signed_request,
    wire_payload,
)
from tests.fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import RecordingInteraction, recording_interaction
from tests.fixtures.payloads import payload_for

pytestmark = pytest.mark.integration

CHANNEL = ChannelId.SLACK

#: The fields the contract declares. Written out rather than imported, because a field-set constant
#: would be a twenty-second upstream name and `T119` says plainly that a twenty-second name is a new
#: decision. Held to the model by the first node below.
_CONTRACT_FIELDS: frozenset[str] = frozenset(
    {
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
        "seal",
    }
)

_CANDIDATE_FIELDS: frozenset[str] = frozenset({"identifier", "slot", "distinguishing"})

_SEAL_FIELDS: frozenset[str] = frozenset({"key_id", "algorithm", "value"})

#: The names that appear both in the union above and in `src/` as attribute reads — every one of
#: them on an object `004` owns. Each carries what `004` uses it for, so an exclusion is a statement
#: somebody has to write rather than a name somebody can add.
_NAMES_004_OWNS: dict[str, str] = {
    "correlation_id": "the envelope's own correlation identifier, threaded through the trail",
    "policy_version": "the transport bounds' governed policy pin",
    "expires_at": "the idempotency record's window end",
    "identifier": "the readiness record's capability identifier",
    "value": "every enum member's `.value`, in every module of the package",
}

_ALL_CLARIFICATION_FIELDS = _CONTRACT_FIELDS | _CANDIDATE_FIELDS | _SEAL_FIELDS

_FIELDS_004_MUST_NOT_READ = _ALL_CLARIFICATION_FIELDS - frozenset(_NAMES_004_OWNS)

#: Derived from the class rather than spelled, so a rename upstream cannot leave the scan below
#: quietly searching for a name that no longer exists.
_CONTRACT_NAME = ClarificationContract.__name__


def _clarification_contract(nonce: str = "fixture-nonce-1") -> ClarificationContract:
    """One genuinely valid contract. **TEST-ONLY, and it seals nothing.**

    ``nonce`` is a parameter so a second, deliberately different contract can be built for the
    anti-vacuity node without any other field moving.

    Built through ``model_validate`` with the seal as a **mapping**: `Seal` is not on the import
    allowlist, and `003`'s own model is where the seal's shape belongs anyway. `D-21` is undeclared,
    so no real seal exists to construct — these are fixture strings and they secure nothing.
    """
    return ClarificationContract.model_validate(
        {
            "contract_version": 1,
            "correlation_id": "fixture-correlation-1",
            "interpretation_id": "fixture-interpretation-1",
            "auth_fingerprint": "fixture-auth-fingerprint-1",
            "unresolved": SlotKind.METRIC,
            "candidates": (
                CandidateRef(
                    identifier="fixture-candidate-a",
                    slot=SlotKind.METRIC,
                    distinguishing=LocalizedRef(
                        code="candidate.a",
                        language="pt-BR",
                        content_version="fixture-vocabulary-1",
                    ),
                ),
            ),
            "rounds_consumed": 0,
            "round_bound": 2,
            "issued_at": datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
            "expires_at": datetime(2026, 8, 17, 12, 10, tzinfo=UTC),
            "nonce": nonce,
            "catalog_release": "fixture-catalog-release-1",
            "policy_version": "fixture-policy-1",
            "vocabulary_version": "fixture-vocabulary-1",
            "seal": {
                "key_id": "fixture-key-1",
                "algorithm": "fixture-seal-algorithm",
                "value": "fixture-seal-value",
            },
        }
    )


def _run(
    outcome: object, payload: dict[str, object] | None = None
) -> tuple[RoundTripResult, RecordingInteraction, RecordingDeliveryPort, RecordingAuditSink]:
    """Drive the whole path once with ``outcome`` waiting at the port."""
    double = recording_interaction(outcome)
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink()
    result = handle(
        signed_request(CHANNEL, payload),
        descriptor=descriptor_for(CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=FIXTURE_BOUNDS,
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=CHANNEL)),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=payload_for("all four claim classes").wording,
        port=double,
        capabilities=fixture_capabilities,
        delivery=transport,
        sink=trail,
    )
    return result, double, transport, trail


def _src_modules() -> list[Path]:
    """Every module under `src/channel_integration`, located from the composed path itself."""
    root = Path(handle.__code__.co_filename).parent
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _label(source: Path) -> str:
    """A short, stable name for a module, for failure messages."""
    return f"{source.parent.name}/{source.name}"


def _attributes_read_in(tree: ast.AST) -> set[str]:
    """Every attribute name read anywhere in ``tree``."""
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def _names_the_contract(func: ast.expr) -> bool:
    """True when ``func`` is the contract itself or one of its class-level constructors."""
    if isinstance(func, ast.Name):
        return func.id == _CONTRACT_NAME
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id == _CONTRACT_NAME
    return False


def test_the_field_sets_are_the_contracts_own_rather_than_a_list_restated_here() -> None:
    """The three literal sets above are held to the model, so a renamed field fails here first.

    They are written out rather than read from `ClarificationContract.model_fields` because that
    import would be a twenty-second upstream name and this file may not take that decision. Holding
    them to a contract this file actually builds is the same guarantee without the import.
    """
    contract = _clarification_contract()

    assert frozenset(contract.model_dump()) == _CONTRACT_FIELDS
    assert len(contract.candidates) == 1
    assert frozenset(contract.candidates[0].model_dump()) == _CANDIDATE_FIELDS
    assert frozenset(contract.seal.model_dump()) == _SEAL_FIELDS


def test_a_clarification_arrives_on_upstream_byte_identically_and_nothing_is_delivered() -> None:
    """`SC-049`, `FR-042`. The transport property, asserted three ways over one carried object.

    Identity first — the object on `result.upstream` must be the very object the port returned, not
    a reconstruction that happens to look like one. Then value and serialisation, both against a
    **separately constructed** contract rather than against the carried one, so the comparison would
    still mean something on the day `handle` starts copying: an identity check alone would fail
    loudly, and a self-comparison would pass silently.

    And nothing else happens. No presentation, no delivery outcome, no send, no refusal, and a stage
    trail that ends at `SUBMITTED` — `RENDERED` never fires, because rendering is never attempted.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    contract = _clarification_contract()
    reference = _clarification_contract()
    assert reference is not contract, "the two must be distinct objects for the comparison to bite"
    serialised = reference.model_dump_json()

    result, double, transport, trail = _run(contract)

    assert result.upstream is contract, "the contract was copied or rebuilt on the way out"
    carried = result.upstream
    assert isinstance(carried, ClarificationContract)
    assert carried == reference
    assert carried.model_dump_json() == serialised
    for field in sorted(_CONTRACT_FIELDS):
        assert getattr(carried, field) == getattr(reference, field), field

    assert result.asks == 1
    assert double.calls == 1
    assert result.refusal is None
    assert result.presentation is None
    assert result.delivery is None
    assert transport.sends == 0
    assert transport.calls == []
    assert result.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
    )
    assert trail.stages == result.stages


def test_the_comparison_would_notice_a_single_changed_field() -> None:
    """Anti-vacuity for the node above, which passes on an object nothing touched.

    One field of one contract is moved, and every instrument used above has to see it: equality, the
    serialised form, and the field-by-field walk — which must name exactly the field that moved and
    no other. Then the altered contract is carried through the same path, and what comes back must
    differ from the reference. Without this, "byte-identical" would be a claim about a comparison
    that could not fail.
    """
    reference = _clarification_contract()
    altered = _clarification_contract(nonce="fixture-nonce-2")

    assert altered != reference
    assert altered.model_dump_json() != reference.model_dump_json()
    differing = [
        field
        for field in sorted(_CONTRACT_FIELDS)
        if getattr(altered, field) != getattr(reference, field)
    ]
    assert differing == ["nonce"], differing

    assert_the_production_resolver_still_refuses(CHANNEL)
    result, _, _, _ = _run(altered)
    carried = result.upstream
    assert isinstance(carried, ClarificationContract)
    assert carried.model_dump_json() != reference.model_dump_json()


def test_no_module_under_src_reads_an_answer_bearing_field_of_a_clarification() -> None:
    """Answered, completed, pre-filled, resolved — none of the four happen here, structurally.

    Reading `candidates` would be pre-filling. Reading `unresolved`, `slot` or `distinguishing`
    would be answering. Reading `rounds_consumed` or `round_bound` would be completing. Reading
    `interpretation_id`, `auth_fingerprint`, `nonce` or `seal` would be resuming — and every one of
    those is `003`'s decision, taken with state `004` does not hold.

    The scan reads **attribute access**, parsed with `ast`, because a field cannot be read without
    being named. It cannot know the receiver's type, so the names `004` legitimately uses for
    its own
    objects are excluded — and the exclusion is not a free pass: the set of names that
    actually collide is measured here and asserted to be exactly the recorded ones, so a new one
    fails
    rather than being absorbed.
    """
    for name, why in sorted(_NAMES_004_OWNS.items()):
        assert len(why) > 20, f"{name} is excluded with a thin reason: {why!r}"

    offenders: list[str] = []
    seen: set[str] = set()
    for source in _src_modules():
        attributes = _attributes_read_in(ast.parse(source.read_text(encoding="utf-8")))
        seen |= attributes
        offenders.extend(
            f"{_label(source)}: .{name}" for name in sorted(attributes & _FIELDS_004_MUST_NOT_READ)
        )

    assert seen, "no attribute access was found anywhere in src, so this gate proves nothing"
    assert _FIELDS_004_MUST_NOT_READ, "the excluded set swallowed every field there was to check"
    assert not offenders, (
        f"a module reads a clarification field it must only transport: {offenders}. Answering, "
        "completing, pre-filling and resuming are `003`'s, and `004` holds none of the state they "
        "need"
    )

    collisions = _ALL_CLARIFICATION_FIELDS & seen
    assert collisions == frozenset(_NAMES_004_OWNS), (
        f"the names that collide with `004`'s own vocabulary changed: {sorted(collisions)}. Each "
        f"exclusion is recorded with what `004` uses it for in `_NAMES_004_OWNS`, and a new one is "
        "a name to justify rather than to add"
    )


def test_the_attribute_scanner_sees_a_read_when_there_is_one() -> None:
    """Anti-vacuity for the scan above, which passes over a package that reads nothing.

    A collector that silently returned an empty set would make the offender list empty for the wrong
    reason. So it is pointed at source that does exactly what `src` must never do.
    """
    probe = ast.parse("def resume(contract):\n    return contract.candidates, contract.seal\n")
    assert _attributes_read_in(probe) & _FIELDS_004_MUST_NOT_READ == {"candidates", "seal"}


def test_the_feature_constructs_no_clarification_contract_anywhere() -> None:
    """`004` transports a clarification; it never issues one — and issuance needs `D-21`.

    Both the direct call and the class-level constructors are looked for, because `model_validate`
    and `model_construct` build one just as surely as the name does — and `model_construct` would
    build one *without* validation, which is how an unsealed contract would come into existence.
    """
    constructions: list[str] = []
    for source in _src_modules():
        tree = ast.parse(source.read_text(encoding="utf-8"))
        constructions.extend(
            f"{_label(source)}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _names_the_contract(node.func)
        )

    assert not constructions, (
        f"a module constructs a clarification contract: {constructions}. Issuance is `003`'s and "
        "needs the `D-21` key material that is undeclared, so a contract built here would be one "
        "whose rounds, expiry and principal binding are editable by whoever holds it"
    )


def test_the_feature_declares_a_clarification_shape_and_consumes_it_nowhere() -> None:
    """The measured reason there is no rendering assertion in this file.

    `outbound/payload.py` declares `GovernedClarificationPayload` — the shape a clarification
    outcome would arrive in — and measured 2026-08-19 that name occurs in exactly one module: the
    one that declares it. No renderer takes it, no function returns it, and `render_answer` is typed
    against `GovernedAnswerPayload` alone.

    `ChannelReasonCode` is checked from the same direction. Not one of its members names a
    clarification, which is the strongest available statement that `004` takes no position on one: a
    feature with no vocabulary for a concept cannot classify, refuse or resolve it.
    """
    shape = "GovernedClarificationPayload"
    referencing = [
        _label(source) for source in _src_modules() if shape in source.read_text(encoding="utf-8")
    ]
    assert referencing == ["outbound/payload.py"], (
        f"{shape} is now named by {referencing}. If something consumes it, `004` has grown a "
        "clarification path and this file is measuring a different system"
    )

    named = [code.value for code in ChannelReasonCode if "CLARIF" in code.value.upper()]
    assert not named, f"`004` has grown a clarification vocabulary: {named}"


def test_there_is_no_inbound_surface_that_carries_a_clarification_back() -> None:
    """The other direction, asserted as the absence it is rather than invented to be symmetric.

    The inbound half of a clarification round trip is the question that **follows** one, carrying
    the contract back so `003` can resume. Measured 2026-08-19, `004` has no such surface, and the
    absence is structural at three levels:

    * `inbound.envelope.WIRE_FIELDS` is a closed set, and it intersects the contract's fifteen in
      exactly one — `correlation_id`, which is the envelope's own identifier for the audit trail and
      carries no contract;
    * the intake `004` actually submits declares five fields, none of which could hold one, so
      `intake_from_envelope` would have nowhere to put a contract even if one arrived;
    * a payload that tries anyway is **refused**, before identity, so the trail is empty, the
      port is never reached and nothing is transmitted.

    Closing that gap is a governed decision about where a resumption surface lives. Inventing one
    here so a round-trip test could be symmetric would be this file authoring the feature it exists
    to measure.
    """
    contract = _clarification_contract()
    shared = WIRE_FIELDS & _CONTRACT_FIELDS
    assert shared == frozenset({"correlation_id"}), (
        f"the inbound wire shape now shares {sorted(shared)} with the clarification contract, so "
        "there may be a resumption surface this file does not know about"
    )

    assert_the_production_resolver_still_refuses(CHANNEL)
    _, double, _, _ = _run(contract)
    submitted = frozenset(double.intakes[0].model_dump())
    assert submitted == frozenset({"text", "language", "reference_date", "as_of", "principal"})
    assert not submitted & _CONTRACT_FIELDS

    refused, silent, transport, trail = _run(
        contract, wire_payload(clarification=contract.model_dump_json())
    )
    assert refused.refusal is not None
    assert refused.refusal.code is ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN
    assert refused.stages == ()
    assert trail.events == []
    assert refused.asks == 0
    assert silent.calls == 0
    assert transport.sends == 0
