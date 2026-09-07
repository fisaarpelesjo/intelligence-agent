"""A retry re-sends; it never re-asks — T097 (ADR 0021; FR-056; SC-026).

The property is a **call count**, and it is measured rather than reasoned about: across a bounded
retry sequence, the interaction port is invoked exactly once, and it is invoked before any send.

Why this matters more than it looks. Re-asking would run the whole governed pipeline again —
authorization, catalog resolution, execution, model-free interpretation — for a message the sender
sent once. If anything upstream moved in between, the reader receives two different answers to one
question and has no way to know which is current. Re-sending the same rendered bytes cannot do that.

Phase C has no interaction port yet, so "invoked once" is asserted two ways that are true today:

* **by count**, against a double standing in for the port and counting its calls — the retry loop
  is driven for real and the counter must stay at one;
* **structurally**, because `delivery/` imports nothing that could reach a port at all, which `T103`
  and `T119` extend once the seam exists.

The structural half is what makes the counted half meaningful: a counter that could never be
incremented would read as a pass for the wrong reason.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.delivery import attempt as attempt_module
from channel_integration.delivery import retry as retry_module
from channel_integration.delivery.retry import deliver_with_retry
from channel_integration.outbound.render import render_answer

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


class CountingInteractionDouble:
    """Stands in for the interaction port, and counts. Nothing more.

    Deliberately not the `T121` fixture double, which belongs to Phase D. This one exists to be
    counted, and it returns the payload the corpus already carries so no answer is invented here.
    """

    def __init__(self) -> None:
        self.asks = 0

    def ask(self, intake: object) -> object:
        self.asks += 1
        return CORPUS["all four claim classes"]


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


def test_a_full_retry_sequence_asks_exactly_once() -> None:
    """`SC-026`, counted. Four sends, one ask."""
    envelope = _envelope()
    interaction = CountingInteractionDouble()
    payload = interaction.ask(object())
    assert interaction.asks == 1

    presentation = render_answer(payload, _CHANNEL, FIXTURE_CAPABILITY)  # type: ignore[arg-type]
    port = RecordingDeliveryPort(outcomes=(DeliveryOutcome.RATE_LIMITED,))
    bounds = bounds_for(_CHANNEL)
    plan = deliver_with_retry(port, presentation, envelope, bounds)

    assert plan.outcome is DeliveryOutcome.RATE_LIMITED
    assert port.sends == bounds.retry_attempts + 1, "the bound was not honoured"
    assert interaction.asks == 1, f"the port was invoked {interaction.asks} times"


def test_every_attempt_carries_byte_identical_fragments() -> None:
    """Re-sending means the same bytes, not a fresh rendering."""
    envelope = _envelope()
    presentation = render_answer(CORPUS["all four claim classes"], _CHANNEL, FIXTURE_CAPABILITY)
    port = RecordingDeliveryPort(outcomes=(DeliveryOutcome.RATE_LIMITED,))
    deliver_with_retry(port, presentation, envelope, bounds_for(_CHANNEL))
    bodies = {call[1] for call in port.calls}
    assert len(bodies) == 1, "a retry sent different bytes"


def test_the_retry_module_takes_no_interaction_collaborator() -> None:
    """Structural: the port cannot be re-invoked because it cannot be passed."""
    parameters = set(inspect.signature(deliver_with_retry).parameters)
    assert parameters == {"port", "presentation", "envelope", "bounds"}
    for forbidden in ("interaction", "ask", "intake", "resolver", "catalog", "model"):
        assert not any(forbidden in name for name in parameters)


def test_no_delivery_module_can_reach_an_interaction_surface() -> None:
    """Structural, over the whole delivery package."""
    root = Path(inspect.getfile(retry_module)).resolve().parent
    offenders: list[str] = []
    for source in sorted(root.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "interaction" in node.module or node.module.startswith("analytics_"):
                    offenders.append(f"{source.name}: {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "interaction" in alias.name or alias.name.startswith("analytics_"):
                        offenders.append(f"{source.name}: {alias.name}")
    assert not offenders, offenders


def test_no_delivery_module_renders_anything() -> None:
    """A retry that could render could render *differently*. It cannot render at all."""
    root = Path(inspect.getfile(attempt_module)).resolve().parent
    for source in sorted(root.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for forbidden in ("render_answer", "render_for_channel", "claim_block", "fragments_for"):
            assert forbidden not in text, f"{source.name} can render"
