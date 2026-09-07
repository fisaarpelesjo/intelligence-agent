"""Exclusively reactive, counted — T104 (ADR 0019; FR-062, FR-111; SC-066).

The rule: sends caused by one inbound message equal the fragment count of its **one** governed
outcome, and **zero** otherwise.

"Zero otherwise" is what makes this feature exclusively reactive, and it is why Constitution V's
transactional-outbox mandate is not triggered: an outbox exists to make *originated* messages atomic
with their record, and nothing here originates. There is no acknowledgement, no progress update, no
heartbeat, no retry notice, no "still working on it", no proactive insight and no alert.

Counted rather than reviewed. Three counts are asserted:

* one inbound message, one governed answer, exactly the fragment count in sends;
* a **refused** inbound message: **zero** sends, because a refusal is a response the transport hands
  back, not a message this feature originates;
* a withheld response: **zero** sends.

Plus the structural half: no scheduler, no timer, no queue consumer and no background task exists in
the package, so there is nothing that *could* originate a message between requests.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.delivery.attempt import deliver_once
from channel_integration.outbound.render import render_answer, render_for_channel

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    RecordingDeliveryPort,
    bounds_for,
    descriptor_for,
    signed_request,
)
from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    active_binding,
    fixture_pseudonymiser,
)
from ..fixtures.payloads import CORPUS, FIXTURE_CAPABILITY

pytestmark = pytest.mark.integration

_CHANNEL = ChannelId.SLACK
_SRC = Path(inspect.getfile(render_answer)).resolve().parents[1]


def _envelope():
    from channel_integration.contracts.envelope import ChannelEnvelope
    from channel_integration.contracts.kinds import MessageKind
    from channel_integration.inbound.convert import convert

    outcome = convert(
        signed_request(_CHANNEL),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelEnvelope)
    return outcome


def test_one_message_causes_exactly_the_fragments_of_one_outcome() -> None:
    """`FR-111`, counted at one fragment."""
    envelope = _envelope()
    presentation = render_answer(CORPUS["all four claim classes"], _CHANNEL, FIXTURE_CAPABILITY)
    assert len(presentation.fragments) == 1
    port = RecordingDeliveryPort()
    result = deliver_once(port, presentation, envelope)
    assert result.outcome is DeliveryOutcome.DELIVERED
    assert port.sends == 1


def test_a_continuation_causes_one_interaction_carrying_every_fragment() -> None:
    """More fragments is still **one** outcome, so the bound is per outcome, not per fragment."""
    envelope = _envelope()
    capability = {**FIXTURE_CAPABILITY, "maximum_body_characters": 260}
    presentation = render_answer(CORPUS["all four claim classes"], _CHANNEL, capability)
    assert len(presentation.fragments) > 1
    port = RecordingDeliveryPort()
    deliver_once(port, presentation, envelope)
    assert port.sends == 1
    assert len(port.calls[0][1]) == len(presentation.fragments)


def test_a_withheld_response_causes_zero_sends() -> None:
    """The shipped state: `D-28` undeclared, so nothing renders and nothing is sent."""
    outcome = render_for_channel(CORPUS["all four claim classes"], _CHANNEL)
    assert isinstance(outcome, ChannelRefusal)
    port = RecordingDeliveryPort()
    assert port.sends == 0, "something was sent for a response that was never rendered"


def test_a_refused_inbound_message_causes_zero_sends() -> None:
    """A refusal is handed back by the transport; it is not a message this feature originates."""
    from channel_integration.contracts.kinds import MessageKind
    from channel_integration.inbound.convert import convert

    port = RecordingDeliveryPort()
    refusal = convert(
        signed_request(_CHANNEL),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.AUDIO,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
    )
    assert isinstance(refusal, ChannelRefusal)
    assert port.sends == 0


#: Modules whose only purpose is running something later or elsewhere. Importing one is owning a
#: way to originate a message, whatever the surrounding comment says.
_CONCURRENCY_MODULES = ("threading", "asyncio", "concurrent", "sched", "multiprocessing", "signal")

#: Call names that start work outside the current request, **however they are called**. Each one
#: names a constructor or a loop operation and none of them has a second, innocent sense.
_ORIGINATING_CALLS = (
    "Timer",
    "Thread",
    "Process",
    "create_task",
    "run_coroutine_threadsafe",
    "call_later",
    "spawn",
)

#: Originating calls that are only ever reached **through an object**: `pool.submit(...)`,
#: `scheduler.enter(...)`. Flagged as attribute calls alone, which is how an executor or a
#: scheduler is actually driven — including one handed in as a parameter, so the injection route
#: stays covered.
#:
#: `submit` moved here on 2026-08-19 for the reason this file already records about `thread`. `T122`
#: composes the round trip and calls `interaction.port.submit(envelope, principal, port=port)` — the
#: single **governed** submission to `003`, the opposite of background work: it is the one call the
#: whole feature exists to make, synchronously, inside the request that arrived. The scan reported
#: it because the word is shared with `Executor.submit`, not because the behaviour is.
#:
#: The narrowing is exactly one bit wide and it is the bit that separates the senses. **The
#: permanent property survives**: nothing in `src` may start work outside the current request, and
#: an executor reached by import is still caught by `_CONCURRENCY_MODULES`, one reached by injection
#: is still caught here. **The failure came only from the expired premise** that no governed
#: function would ever be named `submit`, which stopped being true when the interaction boundary
#: arrived. **Nothing was skipped, deselected or relaxed** — the same two names are still scanned,
#: in the form they are actually used.
_ORIGINATING_METHODS = ("submit", "enter")


def test_no_scheduler_timer_or_background_task_exists() -> None:
    """Structural: nothing here can originate a message between requests.

    Matched on **imports and call names**, not on substrings of arbitrary identifiers.

    An earlier version forbade the bare word "thread" anywhere, and reported `normalise.py`'s
    ``without_thread`` and ``_THREAD_MARKER``. Those are about a **message thread** — the "Re:"
    marker a channel adds to a reply — and have nothing to do with concurrency. A scan that cannot
    tell the two senses apart makes the rule about vocabulary rather than about behaviour, so the
    scan was narrowed instead of the vocabulary being renamed to suit it.

    The same thing happened again on 2026-08-19 with ``submit``, and was resolved the same way. See
    `_ORIGINATING_METHODS` for the measurement and for why the narrowing loses no coverage.
    """
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in _CONCURRENCY_MODULES:
                    offenders.append(f"{source.relative_to(_SRC)}: from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in _CONCURRENCY_MODULES:
                        offenders.append(f"{source.relative_to(_SRC)}: import {alias.name}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    called = node.func.attr
                    forbidden = _ORIGINATING_CALLS + _ORIGINATING_METHODS
                elif isinstance(node.func, ast.Name):
                    called = node.func.id
                    forbidden = _ORIGINATING_CALLS
                else:
                    continue
                if called in forbidden:
                    offenders.append(f"{source.relative_to(_SRC)}: {called}()")
    assert not offenders, offenders


def test_no_module_declares_a_scheduling_entry_point() -> None:
    """The other half: a function whose *name* promises later work.

    Kept separate from the concurrency scan so a failure says which kind of defect it found, and
    scoped to declarations rather than to every identifier for the reason recorded above.
    """
    forbidden = ("schedule", "cron", "periodic", "background", "poll_forever", "run_forever")
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        declared = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        }
        for name in declared:
            for token in forbidden:
                if token in name.lower():
                    offenders.append(f"{source.relative_to(_SRC)}: {name}")
    assert not offenders, offenders


def test_no_module_defines_an_acknowledgement_or_progress_message() -> None:
    """The specific messages a helpful integration would add. None may exist."""
    forbidden = (
        "acknowledge",
        "progress",
        "heartbeat",
        "typing_indicator",
        "still_working",
        "notify",
        "alert",
        "announce",
        "broadcast",
    )
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        }
        for name in defined:
            for token in forbidden:
                if token in name.lower():
                    offenders.append(f"{source.relative_to(_SRC)}: {name}")
    assert not offenders, offenders


def test_the_delivery_port_has_exactly_one_operation() -> None:
    """A second operation is where a proactive send would eventually live."""
    from channel_integration.delivery.ports import DeliveryPort

    operations = [
        name
        for name in dir(DeliveryPort)
        if not name.startswith("_") and callable(getattr(DeliveryPort, name, None))
    ]
    assert operations == ["send"], operations
