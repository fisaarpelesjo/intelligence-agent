"""One `ask` per inbound message, and none after a refusal — T134 [P] (`SC-048`; FR-104, FR-106).

Two questions, measured two different ways.

**How many times was the port reached?** Counted at both ends. `RoundTripResult.asks` is the
composition's own count and `RecordingInteraction.calls` is the double's, derived from the list of
intakes it actually received. Every node below asserts both, and asserts they agree: two independent
counters that disagree is precisely the defect a single counter cannot report, and `roundtrip.py`
says plainly that `asks` is "counted rather than asserted, because `T134` reads a number".

**Could a second ask exist at all?** That is not a count, it is a shape, so it is asserted
structurally with `ast` over `src/**/*.py`: which modules reach a submission, whether any loop or
retry encloses one, and whether one inbound message can become more than one intake.

## What this file measures that `test_single_interpretation_path.py` does not

`T115` asserts that `004` declares no interpretation ordering, names no two pipeline steps and
imports neither `ask` nor `STEP_ORDER`. That is about `003`'s sixteen steps and is not repeated
here. This file asks the narrower, local question: given that the one authorized surface is
`InteractionPort.ask`, is it reached once per message, from exactly two modules, with nothing
around it that could reach it twice.

`test_round_trip.py::test_the_composed_path_is_the_only_one_that_reaches_the_port` is also nearby
and is also not duplicated: it matches the **text** `"submit("` and finds two files, one of which
qualifies because it *defines* `submit`. This file parses **calls**, so `interaction/port.py`
qualifies for a different reason — its `port.ask(...)` — and `roundtrip.py` for its `submit(...)`.
Same two modules, two different measurements, and the parsed one is what a loop analysis needs.

## Four things measured while writing this that the task text does not anticipate

1. **The submission is inside a `try`.** `roundtrip.py` wraps `submit(...)` in
   `except ChannelViolation`. A `try` is not a retry, and the difference is asserted rather than
   assumed: the handler records `SUBMITTED`, returns a `RoundTripResult`, and contains no second
   submission anywhere in its subtree.
2. **There is exactly one retry loop in the package, and it is nowhere near the port.**
   `delivery/retry.py::deliver_with_retry` loops over `deliver_once`. ADR 0021 is explicit that a
   retry re-sends the same payload and never re-invokes the port, and `T097` counts that from the
   delivery side. Here the same fact is asserted structurally, and that loop doubles as the positive
   control that makes the loop scan non-vacuous — a scan that found no loops at all would pass for
   the wrong reason.
3. **The "no port" refusal has no second counter, and that is the point.** `submit` refuses on
   `port is None` *before* building the intake, so on that path there is no port object to count
   calls on. The honest instrument is a double that served one earlier message and is asserted to
   stay at exactly one across the portless run — a count of one, never two.
4. **`asks` is one, not zero, when rendering withholds.** The question *was* submitted; it is the
   response that could not be governed. So `calls == 1` on the withheld paths is the assertion, and
   `calls == 0` is reserved for the paths where the port was genuinely never reached.

Every node injecting `fixture_capabilities` calls `assert_the_production_resolver_still_refuses`
inside `_run` — `D-28` is undeclared and the shipped round trip stops at `RENDERED`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.governance.capabilities import resolve_capability_matrix
from channel_integration.interaction.port import submit
from channel_integration.roundtrip import CapabilityResolver, RoundTripResult, handle
from tests.fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    RecordingAuditSink,
    RecordingDeliveryPort,
    assert_the_production_resolver_still_refuses,
    bounds_for,
    descriptor_for,
    fixture_capabilities,
    signed_request,
    wire_payload,
)
from tests.fixtures.identity import (
    FIXTURE_EXTERNAL,
    FIXTURE_PRINCIPAL,
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import RecordingInteraction, recording_interaction
from tests.fixtures.payloads import CORPUS, payload_for

pytestmark = pytest.mark.integration

_CHANNEL = ChannelId.SLACK

#: The corpus entry that renders. Named rather than discovered: `T093` and
#: `tests/contract/test_preservation.py` already fix which entry withholds, and re-deriving the
#: split here would make this file depend on a rendering property it is not measuring.
_ANSWERED = "all four claim classes"

#: The question every fixture request carries, read from the fixture so the copying assertion below
#: compares the intake against what the sender actually wrote rather than against a restatement.
_QUESTION = str(wire_payload()["text"])

_SRC = Path(inspect.getfile(handle)).resolve().parent

#: The two names a submission is reached through, as **calls**. `submit` is called by name from the
#: composition; `ask` is only ever reached through the port object. Both forms are scanned, so an
#: executor-style `something.submit(...)` would be caught here even though nothing uses it today.
_SUBMISSION_NAMES = frozenset({"ask", "submit"})

#: Where a submission call may appear. `interaction/port.py` because it calls `port.ask(...)`;
#: `roundtrip.py` because it calls `submit(...)`. A third module is a second interpretation path.
_MEASURED_MODULES = ("interaction/port.py", "roundtrip.py")

#: Node types that could make one call site run more than once.
_LOOPS = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _run(
    *,
    channel: ChannelId = _CHANNEL,
    payload_name: str = _ANSWERED,
    port: RecordingInteraction | None,
    kind: MessageKind = MessageKind.TEXT,
    capabilities: CapabilityResolver = fixture_capabilities,
    delivery: RecordingDeliveryPort | None = None,
    sink: RecordingAuditSink | None = None,
) -> RoundTripResult:
    """One whole round trip, with the port a parameter so a path with none can be driven too.

    ``assert_the_production_resolver_still_refuses`` runs on every call rather than per node: the
    nodes below vary the payload, the channel and the capability resolver, and a helper that checked
    only sometimes would let a fixture rendering pass unremarked on the paths it did not cover.
    """
    assert_the_production_resolver_still_refuses(channel)
    fixture = CORPUS[payload_name]
    return handle(
        signed_request(channel),
        descriptor=descriptor_for(channel),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(channel),
        kind=kind,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=channel)),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=fixture.wording,
        port=port,
        capabilities=capabilities,
        delivery=delivery if delivery is not None else RecordingDeliveryPort(),
        sink=sink if sink is not None else RecordingAuditSink(),
    )


def _sources() -> list[Path]:
    return sorted(path for path in _SRC.rglob("*.py") if "__pycache__" not in path.parts)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _is_submission(node: ast.AST) -> bool:
    """True for a call that reaches the interaction boundary, in either form it can take."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id in _SUBMISSION_NAMES
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in _SUBMISSION_NAMES
    return False


def _submissions_in(node: ast.AST) -> list[ast.Call]:
    return [
        child for child in ast.walk(node) if isinstance(child, ast.Call) and _is_submission(child)
    ]


def _submission_sites() -> dict[str, list[int]]:
    """Every submission call under `src`, as ``module -> line numbers``."""
    sites: dict[str, list[int]] = {}
    for path in _sources():
        found = _submissions_in(_tree(path))
        if found:
            sites[path.relative_to(_SRC).as_posix()] = sorted(call.lineno for call in found)
    return sites


def _parents(tree: ast.Module) -> dict[ast.AST, ast.AST]:
    mapping: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            mapping[child] = node
    return mapping


def _ancestors(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[ast.AST]:
    chain: list[ast.AST] = []
    current = parents.get(node)
    while current is not None:
        chain.append(current)
        current = parents.get(current)
    return chain


def test_one_inbound_message_is_exactly_one_ask_on_both_counters() -> None:
    """The base case, measured twice. The composition says one; the double, independently, says one.

    `result.asks` is written by `roundtrip.py` and `double.calls` is `len(double.intakes)` — derived
    from the record rather than incremented alongside it, so the two cannot drift together. Their
    agreement is asserted explicitly, because "both happen to read one" and "one call happened" are
    the same statement only when the two are independent.
    """
    double = recording_interaction(payload_for(_ANSWERED).answer)
    result = _run(port=double)

    assert result.refusal is None, result.refusal
    assert result.delivery is DeliveryOutcome.DELIVERED
    assert result.asks == 1
    assert double.calls == 1
    assert len(double.intakes) == 1
    assert result.asks == double.calls, "the composition and the port disagree about the call count"


def test_the_two_counters_agree_on_every_payload_and_every_channel() -> None:
    """One ask per message holds across the whole corpus and all four channels, never two.

    Driven over the corpus rather than over one entry because the entries differ in what happens
    **after** the submission — some of them withhold at `RENDERED` — and "one ask" must be
    insensitive to that. A count that changed with the payload would mean the outcome was steering
    the number of questions asked.

    The delivered/withheld split is asserted too, so this loop cannot pass by rendering nothing at
    all and calling every path equivalent.
    """
    delivered = 0
    withheld = 0
    for channel in ChannelId:
        for name in sorted(CORPUS):
            double = recording_interaction(CORPUS[name].answer)
            result = _run(channel=channel, payload_name=name, port=double)
            assert result.asks == 1, (channel, name)
            assert double.calls == 1, (channel, name)
            assert result.asks == double.calls, (channel, name)
            if result.refusal is None:
                delivered += 1
            else:
                assert result.refusal.stage is ChannelStage.RENDERED, (channel, name)
                withheld += 1

    assert delivered > 0, "nothing rendered, so this loop measured only the refusal path"
    assert withheld > 0, "nothing withheld, so the withheld half of the split is untested"


def test_a_refusal_before_identity_reaches_the_port_zero_times() -> None:
    """The first "zero after a refusal": the port was never reached, so nothing was recorded.

    A non-textual kind refuses at step 4, well before an envelope exists. Both counters read zero
    and the double's intake list is empty — the assertion a count alone could not make, because an
    empty list is the evidence that no intake was ever constructed, let alone submitted.
    """
    double = recording_interaction(payload_for(_ANSWERED).answer)
    result = _run(port=double, kind=MessageKind.AUDIO)

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.code is ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED
    assert result.stages == ()
    assert result.asks == 0
    assert double.calls == 0
    assert double.intakes == []
    assert result.asks == double.calls


def test_the_portless_refusal_asks_nobody_and_leaves_an_earlier_count_untouched() -> None:
    """The second "zero after a refusal", and the one with no counter of its own.

    Production constructs no port (`FR-104`), so this is a shipped path — and a path with no port
    has nothing to count calls on. The instrument is therefore the double that served the *previous*
    message in this same node: it must still read one afterwards, never two.

    That also asserts the property the boundary refusal was designed for. `submit` checks
    ``port is None`` **before** building the intake, so a caller with no port learns nothing about
    whether its envelope would have converted, and no leftover collaborator is touched on the way
    out.
    """
    double = recording_interaction(payload_for(_ANSWERED).answer)
    first = _run(port=double)
    assert first.asks == 1
    assert double.calls == 1

    portless = _run(port=None)

    assert isinstance(portless.refusal, ChannelRefusal)
    assert portless.refusal.code is ChannelReasonCode.INTERACTION_BOUNDARY_UNAVAILABLE
    assert portless.refusal.stage is ChannelStage.SUBMITTED
    assert portless.asks == 0
    assert double.calls == 1, "the portless message reached a port it was never given"
    assert len(double.intakes) == 1


def test_a_withheld_rendering_shows_one_ask_and_never_two() -> None:
    """The third refusal path: the failure came *after* the port, so the count is one, not zero.

    Driven with production's own capability resolver, which refuses for every channel while `D-28`
    is undeclared. The question was submitted and the response could not be governed — a distinction
    the count makes visible, and the reason "zero after a refusal" cannot be asserted uniformly
    across all three refusal shapes.

    The second and stronger half: no compensating re-ask follows the withholding. The double stays
    at exactly one, and its single stored intake is the one submitted before the rendering failed.
    """
    double = recording_interaction(payload_for(_ANSWERED).answer)
    transport = RecordingDeliveryPort()
    result = _run(port=double, capabilities=resolve_capability_matrix, delivery=transport)

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.stage is ChannelStage.RENDERED
    assert result.asks == 1
    assert double.calls == 1, "the withheld rendering caused a second question to be asked"
    assert result.asks == double.calls
    assert transport.sends == 0
    assert result.stages[-1] is ChannelStage.RENDERED


def test_the_submitted_intake_is_the_envelope_copied_not_reworded() -> None:
    """`FR-106`: what reached `003` is what the sender wrote, carried through unchanged.

    One ask is worth little if the one question asked is not the question that arrived. So the chain
    is asserted end to end — wire payload text, envelope text, intake text — and the two dates and
    the absent as-of pin are compared field by field: filling `as_of` from `reference_date` would
    silently pin every question to the day it was asked, which `intake_from_envelope` records as the
    reason it defaults nothing.

    The principal is compared rather than assumed: `intake_from_envelope` refuses when the supplied
    authorization context names a different principal than the envelope, and asserting agreement
    here is what stops that guard from being satisfied vacuously.
    """
    double = recording_interaction(payload_for(_ANSWERED).answer)
    result = _run(port=double)

    assert isinstance(result.envelope, ChannelEnvelope)
    envelope = result.envelope
    intake = double.intakes[0]

    assert envelope.text == _QUESTION, "step 6 altered the question before it left this feature"
    assert intake.text == envelope.text
    assert intake.text == _QUESTION
    assert str(intake.language) == str(envelope.language)
    assert intake.reference_date == envelope.reference_date
    assert intake.as_of is None
    assert envelope.as_of is None
    assert str(intake.principal.principal_ref) == str(envelope.principal_ref)
    assert str(intake.principal.principal_ref) == str(FIXTURE_PRINCIPAL)


def test_the_adapter_copies_the_envelope_and_rewrites_nothing() -> None:
    """The same property as a shape, so it holds for questions no fixture happens to carry.

    The behavioural assertion above covers one payload. This one parses `intake_from_envelope` and
    requires that the only envelope attributes it reads are the ones it copies, and that its body
    contains no f-string, no concatenation and no call to a string-rewriting method. A rewording
    would have to appear as one of those, and a corpus can only ever show that it did not happen for
    the strings that were tried.
    """
    tree = _tree(_SRC / "interaction" / "port.py")
    adapters = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "intake_from_envelope"
    ]
    assert len(adapters) == 1, "intake_from_envelope is no longer a single function"
    adapter = adapters[0]

    read = {
        node.attr
        for node in ast.walk(adapter)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "envelope"
    }
    assert read == {"text", "language", "reference_date", "as_of", "principal_ref"}, sorted(read)

    assert not [node for node in ast.walk(adapter) if isinstance(node, ast.JoinedStr)], (
        "the adapter builds an f-string, which is how a question gets reworded"
    )
    rewriters = {"replace", "strip", "lower", "upper", "format", "join", "translate", "encode"}
    offenders = sorted(
        node.func.attr
        for node in ast.walk(adapter)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in rewriters
    )
    assert not offenders, f"the adapter rewrites what it carries: {offenders}"


def test_the_submission_is_reached_from_exactly_the_two_modules_measured_here() -> None:
    """`SC-048` structurally: two call sites, one each, and both are the ones counted above.

    Parsed as calls rather than matched as text. A text scan counts `def submit(` and would report
    `interaction/port.py` for defining the function; this reports it for calling `port.ask(...)`,
    which is the only place in the package where the boundary is actually crossed.

    A third module here would be a second path to the boundary, and no upstream gate could see it.
    """
    sites = _submission_sites()
    assert sorted(sites) == sorted(_MEASURED_MODULES), sites
    assert [len(sites[name]) for name in _MEASURED_MODULES] == [1, 1], sites


def test_no_loop_or_retry_encloses_the_submission() -> None:
    """No `for`, `while` or comprehension anywhere in `src` contains a submission call.

    Asserted over every loop in the package rather than by walking up from the two call sites, so a
    submission added inside some future loop elsewhere is caught by the same rule.

    The one `try` that *does* enclose a submission is examined separately below, because a try is
    not a retry and conflating the two would make this scan report a defect where the code is right.
    """
    offenders: list[str] = []
    loops = 0
    for path in _sources():
        for node in ast.walk(_tree(path)):
            if not isinstance(node, _LOOPS):
                continue
            loops += 1
            offenders.extend(
                f"{path.relative_to(_SRC).as_posix()}:{call.lineno}"
                for call in _submissions_in(node)
            )
    assert loops > 0, "no loop exists in src at all, so this scan proves nothing"
    assert not offenders, f"a loop encloses a submission: {offenders}"


def test_the_try_around_the_submission_catches_and_returns_rather_than_retrying() -> None:
    """The measured nuance: `roundtrip.py` wraps `submit(...)` in `except ChannelViolation`.

    That is a governed outcome being recorded, not an attempt being repeated. Asserted as such:
    the enclosing handlers, `else` and `finally` bodies contain no further submission, so the only
    way out of the failure is the `RoundTripResult` the handler returns.
    """
    tree = _tree(_SRC / "roundtrip.py")
    parents = _parents(tree)
    calls = _submissions_in(tree)
    assert len(calls) == 1, [call.lineno for call in calls]

    enclosing = [node for node in _ancestors(calls[0], parents) if isinstance(node, ast.Try)]
    assert len(enclosing) == 1, "the submission's enclosing try structure changed shape"
    for branch in (*enclosing[0].handlers, *enclosing[0].orelse, *enclosing[0].finalbody):
        assert not _submissions_in(branch), "the handler submits again, which makes the try a retry"


def test_the_one_retry_loop_in_the_package_re_sends_and_never_re_asks() -> None:
    """ADR 0021 as a shape, and the positive control the loop scan needs.

    `delivery/retry.py::deliver_with_retry` is the only place in this feature that repeats anything.
    It loops over `deliver_once`, re-sending the same presentation, and contains no submission. Both
    halves are asserted: without the first, a scan that found no loop at all would pass for the
    wrong reason; without the second, the rule is untested where it is most likely to be broken.
    """
    tree = _tree(_SRC / "delivery" / "retry.py")
    loops = [node for node in ast.walk(tree) if isinstance(node, _LOOPS)]
    assert loops, "deliver_with_retry no longer loops, so ADR 0021's bounded retry moved"

    resends = 0
    for loop in loops:
        assert not _submissions_in(loop), "the retry loop reaches the interaction boundary"
        resends += len(
            [
                node
                for node in ast.walk(loop)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "deliver_once"
            ]
        )
    assert resends >= 1, f"the retry loop re-sends {resends} times, so it re-sends nothing"


def test_no_module_splits_one_inbound_message_into_several_intakes() -> None:
    """One message, one intake. Splitting is how a widened question would be smuggled through.

    Three facts, each of which a splitting implementation would have to break: `QuestionIntake` is
    reached in exactly one place, that construction is not inside a loop or a comprehension, and no
    annotation anywhere in `src` subscripts `QuestionIntake` — no `tuple[QuestionIntake, ...]`, no
    `list[QuestionIntake]`, nothing that could carry more than one.
    """
    constructions: list[str] = []
    plural: list[str] = []
    for path in _sources():
        tree = _tree(path)
        parents = _parents(tree)
        module = path.relative_to(_SRC).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                built = (isinstance(func, ast.Name) and func.id == "QuestionIntake") or (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "QuestionIntake"
                )
                if built:
                    constructions.append(f"{module}:{node.lineno}")
                    enclosing = _ancestors(node, parents)
                    assert not [one for one in enclosing if isinstance(one, _LOOPS)], (
                        f"{module}:{node.lineno} builds an intake inside a loop"
                    )
            elif isinstance(node, ast.Subscript):
                named = [
                    child
                    for child in ast.walk(node)
                    if isinstance(child, ast.Name) and child.id == "QuestionIntake"
                ]
                if named:
                    plural.append(f"{module}:{node.lineno}")

    assert len(constructions) == 1, constructions
    assert constructions[0].startswith("interaction/port.py:"), constructions
    assert not plural, f"a collection of intakes is expressible at {plural}"


def test_no_gate_to_shop_exists_on_the_boundary_or_around_it() -> None:
    """`FR-104`: one operation, one signature, and no entry point named for a second attempt.

    Three surfaces where a widening, narrowing or gate-shopping path would have to appear. The port
    protocol may declare only `ask` — a second operation is where a "narrow this question" call
    would eventually live. `submit` may take only the envelope, the principal and the port — a
    selector parameter is how a caller would choose a different route. And no function or class
    anywhere in `src` may be named for re-asking, splitting or fanning out.
    """
    tree = _tree(_SRC / "interaction" / "port.py")
    protocols = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "InteractionPort"
    ]
    assert len(protocols) == 1
    operations = sorted(
        node.name
        for node in protocols[0].body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and not node.name.startswith("_")
    )
    assert operations == ["ask"], operations

    assert list(inspect.signature(submit).parameters) == ["envelope", "principal", "port"], (
        "submit grew a parameter, and a parameter is how a second path gets selected"
    )

    forbidden = (
        "reask",
        "re_ask",
        "ask_again",
        "resubmit",
        "widen",
        "narrow",
        "split",
        "fanout",
        "fan_out",
        "escalate",
    )
    offenders: list[str] = []
    for path in _sources():
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            lowered = node.name.lower()
            offenders.extend(
                f"{path.relative_to(_SRC).as_posix()}: {node.name}"
                for token in forbidden
                if token in lowered
            )
    assert not offenders, offenders


def test_the_instruments_can_fail() -> None:
    """Anti-vacuity for both halves, because both are assertions about numbers that could be zero.

    The counted half: a fresh double reads zero, so every `calls == 0` above is a measurement that
    the run left unchanged rather than a constant. Driving one message moves it to one, and driving
    a second, independent message on a second double moves that one to one too — so "one" is a
    property of one message rather than a ceiling the double happens to impose.

    The structural half: the parser must actually find the submission calls. A scan that silently
    returned nothing would make every "no offenders" assertion above pass over an empty set, so the
    call sites are required to be non-empty and to sit on the lines the module scan reported.
    """
    fresh = recording_interaction(payload_for(_ANSWERED).answer)
    assert fresh.calls == 0
    assert fresh.intakes == []

    first = _run(port=fresh)
    assert first.asks == 1
    assert fresh.calls == 1

    second_double = recording_interaction(payload_for(_ANSWERED).answer)
    second = _run(port=second_double)
    assert second.asks == 1
    assert second_double.calls == 1
    assert fresh.calls == 1, "the second message was counted against the first double"

    sites = _submission_sites()
    assert sites, "the parser found no submission at all, so every scan above is vacuous"
    assert sum(len(lines) for lines in sites.values()) == 2, sites
    for module in _MEASURED_MODULES:
        assert sites[module], module
