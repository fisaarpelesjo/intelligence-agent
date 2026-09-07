"""T151 — per-channel simulators over recorded fixture payloads (`R-19`).

A simulator drives the **same** `convert` and the same rendering the production path drives, with
the same governed content, and differs in exactly one way: what it feeds them. It replays a recorded
fixture payload instead of a provider's delivery.

That single difference is the whole reason a simulator is not evidence. Nothing here contacts a
provider sandbox, opens a socket, reads a credential or resolves a real channel identity — so a
green simulation says the code path is coherent over the payloads someone recorded, and says nothing
at all about whether WhatsApp, Slack, Telegram or a generic webhook would behave that way.

## Why the fixtures live with the caller

This module takes the recorded payload as an **argument**. It does not import the test fixtures, and
`T148`'s containment scan is what keeps that honest: a `src/` module reaching into `tests/` would
make the shipped library depend on test data, and the first time someone packaged it the simulator
would either break or, worse, ship the fixtures.

So the CLI passes recorded payloads in from a file the steward names, and the contract tests pass
the corpus in directly. One code path, two callers, no fixture inside the library.

## Every report says what it is

Each result carries `limitation`, and the CLI refuses to emit a report without it (`FR-099`). The
field is not decoration: a simulator report pasted into a review without that sentence is a document
that looks like an integration test result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..contracts._base import ChannelViolation
from ..contracts.envelope import ChannelEnvelope
from ..contracts.kinds import MessageKind
from ..contracts.raw import RawChannelRequest
from ..contracts.refusal import ChannelRefusal
from ..governance.resolve import ContentUnresolvable
from ..inbound.convert import convert
from ..outbound.render import render_for_channel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime

    from ..contracts.descriptor import ChannelDescriptor
    from ..contracts.identity import ExternalIdentity
    from ..governance.bounds import TransportBounds
    from ..identity.pseudonymise import PseudonymPort
    from ..identity.resolve import ChannelIdentityResolver
    from ..inbound.schemes import VerificationMaterial
    from ..outbound.payload import GovernedAnswerPayload

__all__ = [
    "SIMULATION_LIMITATION",
    "SimulatedConversion",
    "SimulatedRendering",
    "simulate_conversion",
    "simulate_rendering",
]

#: The sentence every simulator report carries. One string, referenced everywhere, so a report
#: cannot carry a weaker version of it — and `T153` asserts every surface that reports carries this
#: exact text rather than a paraphrase a reader might discount.
SIMULATION_LIMITATION = (
    "Esta simulação usa payloads de fixture e não contata nenhum provedor. "
    "Ela não é evidência de comportamento em produção nem de prontidão de canal."
)


@dataclass(frozen=True, slots=True)
class SimulatedConversion:
    """What replaying one recorded request through `convert` produced."""

    channel: str
    outcome: ChannelEnvelope | ChannelRefusal
    limitation: str = SIMULATION_LIMITATION

    def report(self) -> dict[str, Any]:
        """The deterministic report shape. Carries the limitation, always."""
        refused = isinstance(self.outcome, ChannelRefusal)
        return {
            "channel": self.channel,
            "converted": not refused,
            "code": self.outcome.code.value if isinstance(self.outcome, ChannelRefusal) else None,
            "stage": self.outcome.stage.value if isinstance(self.outcome, ChannelRefusal) else None,
            "limitation": self.limitation,
        }


@dataclass(frozen=True, slots=True)
class SimulatedRendering:
    """What rendering one recorded payload for one channel produced."""

    channel: str
    fragments: int
    withheld: bool
    code: str | None
    limitation: str = SIMULATION_LIMITATION

    def report(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "fragments": self.fragments,
            "withheld": self.withheld,
            "code": self.code,
            "limitation": self.limitation,
        }


def simulate_conversion(
    recorded: RawChannelRequest,
    *,
    descriptor: ChannelDescriptor,
    material: VerificationMaterial | None,
    bounds: TransportBounds,
    kind: MessageKind,
    external: ExternalIdentity,
    resolver: ChannelIdentityResolver,
    pseudonymiser: PseudonymPort,
    at: datetime,
) -> SimulatedConversion:
    """Replay one recorded request through the production `convert`.

    Every collaborator is injected by the caller, exactly as the production path injects them. This
    function adds no default, no fallback and no leniency: a simulator that was more forgiving than
    production would report a success production would refuse.
    """
    outcome = convert(
        recorded,
        descriptor=descriptor,
        material=material,
        bounds=bounds,
        kind=kind,
        external=external,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=at,
    )
    return SimulatedConversion(channel=recorded.channel.value, outcome=outcome)


def simulate_rendering(
    payload: GovernedAnswerPayload,
    descriptor: ChannelDescriptor,
) -> SimulatedRendering:
    """Render one recorded payload for one channel, through the production entry point.

    Through `render_for_channel` rather than `render_answer`, deliberately. The capability matrix
    must resolve the way production resolves it, so while `D-28` is undeclared this reports
    **withheld** for every channel — which is the true answer and the one a steward needs to see. A
    simulator that injected a fixture matrix here would report renderings that cannot happen.
    """
    channel = descriptor.channel
    try:
        outcome = render_for_channel(payload, channel)
    except (ChannelViolation, ContentUnresolvable) as refusal:
        # `render_for_channel` collapses both into a refusal already; this catch exists so a future
        # change to that collapse cannot turn a simulator run into a traceback.
        return SimulatedRendering(
            channel=channel.value, fragments=0, withheld=True, code=refusal.code.value
        )
    if isinstance(outcome, ChannelRefusal):
        return SimulatedRendering(
            channel=channel.value, fragments=0, withheld=True, code=outcome.code.value
        )
    return SimulatedRendering(
        channel=channel.value,
        fragments=len(outcome.fragments),
        withheld=False,
        code=None,
    )
