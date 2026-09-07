"""Nothing the upstream boundary withheld is released — T132 [US7].

`FR-049`, `FR-050`, `FR-083`; `SC-041`.

`SC-041` has two halves and the second is the one that is usually skipped: 100% of upstream
withholdings result in no delivery, **and** zero upstream synchronous fail-closed audit boundaries
are weakened. This file drives both through `channel_integration.roundtrip.handle`, because a
withholding that propagates correctly through `render_answer` and then leaks through the
composition would satisfy every module-level test in the suite.

## Two shapes of "withheld upstream" that the corpus carries

* **an unresolved wording reference** — `003` produced a `LocalizedRef` for which no resolved string
  exists. ADR 0026 makes that a withhold, never a fallback that renders the reference. The corpus
  entry `"an unresolved wording reference"` is exactly this case.
* **a withheld claim** — a claim carrying no value because the cell was suppressed upstream. `003`'s
  `AnswerClaim` makes this structural: a non-numeric class cannot carry a value at all. The corpus
  entry `"a suppressed cell"` is this case.

## `FR-083`, and the one place the rule cannot hold

"Do not release what cannot be recorded" is exercised with `RecordingAuditSink(refuse_from=N)`
rather than with a mode, so the failure is a real emission failure at a chosen point.

* refusing an early event — the exception escapes, the port is never reached, the transport is never
  touched, and no `RoundTripResult` is returned at all. That is the rule holding.
* refusing the **last** event — measured 2026-08-19: the provider was already asked. `handle` calls
  `deliver_once` and *then* records `DELIVERED`, so the record that fails is the record of a send
  that has happened. The exception still escapes, so nothing acknowledges it and no caller receives
  a result — but the answer is out. The ordering is inherent: an attempt cannot record its own
  outcome before it has one, and making delivery atomic with its record needs a transactional
  outbox, which belongs to a feature that originates messages rather than to this one.

In every case the exception escapes rather than being swallowed. A caught `AuditEmissionFailed`
would let a delivery proceed against a trail that never took it, which is the failure `FR-083`
exists to name — and the structural node at the end asserts that `roundtrip.py` handles exactly two
exception types, neither of which can absorb it.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from channel_integration import roundtrip as roundtrip_module
from channel_integration.audit.emit import AuditEmissionFailed
from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.messages.registry import message_for
from channel_integration.outbound.preserve import payload_governed_strings, strip_structure
from channel_integration.outbound.render import claim_labels
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
)
from tests.fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import recording_interaction
from tests.fixtures.payloads import FIXTURE_CAPABILITY, FixturePayload, payload_for

pytestmark = pytest.mark.integration

CHANNEL = ChannelId.SLACK

_COMPOSITION_SOURCE = inspect.getsource(roundtrip_module)


def _drive(
    *,
    payload: FixturePayload,
    delivery: RecordingDeliveryPort | None = None,
    sink: RecordingAuditSink | None = None,
) -> tuple[RoundTripResult, RecordingDeliveryPort, RecordingAuditSink]:
    """One message through the composition, answered with ``payload``.

    The payload is passed whole rather than by corpus name so a constructed one would travel the
    identical path as a corpus one, with no branch anywhere that could treat it differently.
    """
    transport = delivery if delivery is not None else RecordingDeliveryPort()
    trail = sink if sink is not None else RecordingAuditSink()
    result = handle(
        signed_request(CHANNEL),
        descriptor=descriptor_for(CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=FIXTURE_BOUNDS,
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=payload.wording,
        port=recording_interaction(payload.answer),
        capabilities=fixture_capabilities,
        delivery=transport,
        sink=trail,
    )
    return result, transport, trail


def _residue(delivered: str, payload: FixturePayload) -> str:
    """What survives in ``delivered`` after every authorised string is removed.

    The authorised vocabulary is exactly three things: the governed strings the payload carries, the
    governed labels the `D-28` matrix declares, and the permitted separators. Anything left is a
    sentence `004` wrote. Stripped longest-first for the reason `preserve.py` records — removing
    ``"numero 1"`` before ``"numero 12"`` strands a ``"2"`` and reports it as invented content.

    Run over the bytes the **transport received**, not over the presentation the renderer returned,
    which is what makes this different from `tests/contract/test_no_added_content.py`.
    """
    labels = tuple(claim_labels(FIXTURE_CAPABILITY).values())
    surviving = delivered
    authorised = {*payload_governed_strings(payload), *labels}
    for string in sorted(authorised, key=len, reverse=True):
        surviving = surviving.replace(string, "")
    return strip_structure(surviving)


# --------------------------------------------------------------------------- #
# Upstream withholdings                                                        #
# --------------------------------------------------------------------------- #


def test_an_unresolved_wording_reference_is_withheld_and_reaches_no_transport() -> None:
    """`FR-049`, ADR 0026, at the composed seam. Withheld means the provider is never asked.

    The interesting half is not that rendering refused — the outbound tests prove that. It is that
    the composition turns the refusal into a governed one at the stage it happened, delivers
    nothing, offers nothing, and still records the submission that genuinely occurred. A withhold
    that lost the `SUBMITTED` event would hide that a question was asked upstream.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, transport, trail = _drive(payload=payload_for("an unresolved wording reference"))

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.stage is ChannelStage.RENDERED
    assert result.presentation is None
    assert result.delivery is None
    assert transport.calls == [], "a fragment was offered for a payload that could not be carried"
    assert trail.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
        ChannelStage.RENDERED,
    )
    assert result.asks == 1


def test_a_withheld_claim_releases_no_value_and_no_sentence_explaining_its_absence() -> None:
    """`FR-050`: the suppressed cell arrives with no number, and no commentary.

    Two absences, and the second is the one this file exists for. The claim genuinely carries no
    value — `003` makes that structural — so there is nothing for `004` to release. The temptation
    is the sentence that follows: "this figure was withheld". The residue check proves no such
    sentence exists, because every character delivered is a governed string, a governed label or a
    permitted separator.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    payload = payload_for("a suppressed cell")
    assert any(claim.value is None for claim in payload.answer.claims), (
        "the corpus entry no longer withholds a value"
    )

    result, transport, _ = _drive(payload=payload)
    assert result.delivery is DeliveryOutcome.DELIVERED
    delivered = "\n\n".join(transport.calls[0][1])

    left = _residue(delivered, payload)
    assert left == "", f"004 added text of its own to a withheld claim: {left!r}"
    for invented in ("suprimido por", "não disponível", "indisponível", "erro", "desculpe"):
        assert invented.lower() not in delivered.lower(), f"{invented!r} was generated locally"


def test_nothing_withheld_is_ever_acknowledged_as_delivered() -> None:
    """The "acknowledged" clause of `FR-083`, asserted on the withholding shape.

    A withhold produces no delivery outcome at all — not `WITHHELD`, not a downgraded `DELIVERED`,
    nothing — so there is no state from which an acknowledgement could be derived. The absence of an
    outcome is the honest report rather than a missing one.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, transport, trail = _drive(payload=payload_for("an unresolved wording reference"))

    assert result.delivery is None
    assert transport.sends == 0
    recorded = {event.code for event in trail.events}
    assert ChannelReasonCode.CHANNEL_RESPONSE_DELIVERED.value not in recorded


# --------------------------------------------------------------------------- #
# No generated text anywhere on the withholding path                           #
# --------------------------------------------------------------------------- #


def test_the_withhold_refusal_is_a_governed_lookup_rather_than_an_explanation() -> None:
    """`FR-045`: what the sender reads is stored wording selected by code, byte for byte.

    Compared against `message_for(code)` rather than against a literal, so this asserts the
    *mechanism* — the text came out of the registry keyed by the refusal's own code — instead of
    asserting that somebody typed the same sentence twice. Repeated to prove stability, because a
    registry that composed its answer could return two different strings for one code.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, _, _ = _drive(payload=payload_for("an unresolved wording reference"))

    assert isinstance(result.refusal, ChannelRefusal)
    governed = message_for(result.refusal.code)
    assert result.refusal.sender_text() == governed
    assert result.refusal.message_pt_br == governed
    assert message_for(result.refusal.code) == governed, "the registry is not stable across calls"
    assert governed.strip(), "a withheld response still needs governed wording"


def test_the_composition_constructs_no_sender_facing_string_of_its_own() -> None:
    """Structural: `roundtrip.py` has no way to author what a sender reads.

    Every refusal it produces goes through `refusal_from_violation`, which resolves the wording from
    the governed registry by code. The module never calls `ChannelRefusal` directly and never
    assigns `message_pt_br`, so there is no expression in it that could put a locally written
    sentence in front of a sender. Parsed rather than grepped, so a name inside a docstring is not a
    finding and a genuine call cannot hide behind formatting.
    """
    tree = ast.parse(_COMPOSITION_SOURCE)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "refusal_from_violation" in called, "the composition no longer builds governed refusals"
    assert "ChannelRefusal" not in called, "the composition constructs a refusal directly"
    assert "message_pt_br" not in _COMPOSITION_SOURCE
    assert "message_for" not in _COMPOSITION_SOURCE, (
        "the composition looks up wording itself, so the single collapse point has moved"
    )


# --------------------------------------------------------------------------- #
# `FR-083` — what cannot be recorded is not released                           #
# --------------------------------------------------------------------------- #


def test_a_failed_audit_record_stops_delivery_and_the_exception_escapes() -> None:
    """`FR-083` holding, at the last point where holding it is possible.

    The sink refuses the fifth event, `RENDERED`, which is emitted before `deliver_once` is reached.
    Three things must all be true: `AuditEmissionFailed` escapes rather than being collapsed into an
    outcome, the transport is never asked for anything, and no `RoundTripResult` is produced — a
    caller that received a result would have something that looks like an answer to act on.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink(refuse_from=4)

    with pytest.raises(AuditEmissionFailed):
        _drive(payload=payload_for("all four claim classes"), delivery=transport, sink=trail)

    assert transport.sends == 0, "a response was released against a record that did not take it"
    assert transport.calls == []
    assert trail.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
    )


def test_an_earlier_audit_failure_stops_the_path_before_anything_downstream() -> None:
    """The same rule, at the first stage, where the cost of proceeding would be an upstream ask.

    Driven separately because "does not deliver" and "does not proceed at all" are different
    guarantees and a single refusal point cannot show both.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink(refuse_from=1)

    with pytest.raises(AuditEmissionFailed):
        _drive(payload=payload_for("all four claim classes"), delivery=transport, sink=trail)

    assert trail.stages == (ChannelStage.RECEIVED,)
    assert transport.sends == 0


def test_the_delivered_stage_is_recorded_after_the_send_so_that_failure_cannot_withhold() -> None:
    """The measured limit of `FR-083`, stated instead of being quietly avoided.

    With the sink refusing the sixth event, the send has already happened: `handle` calls
    `deliver_once` and records `DELIVERED` with the outcome that attempt produced. So the record
    that fails is the record of something irreversible.

    What still holds is everything that can: the exception escapes, no caller receives a result, and
    nothing acknowledges the delivery — an operator reading the trail sees a message that reached
    `RENDERED` and no further, which is a true statement about the record if not about the provider.
    What does not hold is "nothing was released". The ordering is inherent rather than careless: an
    attempt cannot record its own outcome before it has one, and closing the gap needs delivery to
    be atomic with its record — the transactional outbox, which belongs to a feature that originates
    messages and is not this one.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink(refuse_from=5)

    with pytest.raises(AuditEmissionFailed):
        _drive(payload=payload_for("all four claim classes"), delivery=transport, sink=trail)

    assert transport.sends == 1, (
        "the send no longer precedes its own record, so FR-083 now holds at DELIVERED too — "
        "delete this node and assert the stronger property"
    )
    assert trail.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
        ChannelStage.RENDERED,
    )
    assert ChannelStage.DELIVERED not in trail.stages, "the refused event was recorded anyway"


def test_the_emission_failure_is_never_caught_on_the_composed_path() -> None:
    """Structural: a future `except` around delivery would silently reverse every node above.

    `AuditEmissionFailed` must appear in no handler in `roundtrip.py`. A bare `except Exception`
    around the delivery block would catch it just as effectively, so both shapes are checked: the
    handled exception types are read from the parsed module and neither the audit failure nor a
    catch-all may be among them.
    """
    tree = ast.parse(_COMPOSITION_SOURCE)
    handled: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            handled.add("bare except")
            continue
        for name in ast.walk(node.type):
            if isinstance(name, ast.Name):
                handled.add(name.id)

    assert "AuditEmissionFailed" not in handled, "the composition swallows a failed record"
    assert "bare except" not in handled
    assert "Exception" not in handled, "a catch-all would absorb AuditEmissionFailed too"
    assert "BaseException" not in handled
    assert handled == {"ChannelViolation", "ContentUnresolvable"}, (
        f"the composition now handles {sorted(handled)}; check that none of them can mask a "
        "failed audit record"
    )


# --------------------------------------------------------------------------- #
# Anti-vacuity                                                                 #
# --------------------------------------------------------------------------- #


def test_the_residue_instrument_can_report_a_failure() -> None:
    """Anti-vacuity for the detector that carries the withheld-claim node.

    `_residue` returning an empty string is the pass condition there, and a stripper that removed
    everything would return empty for any input at all. So it is shown catching a planted apology,
    and shown *not* catching the governed strings that are supposed to survive stripping.
    """
    payload = payload_for("a suppressed cell")

    invented = "Desculpe, este valor nao pode ser mostrado."
    assert _residue(invented, payload) != "", "the residue check cannot detect generated prose"
    assert "Desculpe" in _residue(invented, payload)

    authorised = "\n".join(payload_governed_strings(payload))
    assert _residue(authorised, payload) == "", (
        "the residue check reports authorised governed strings as invented content"
    )
