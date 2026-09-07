"""The delivery port — T076 (ADR 0020; FR-053, FR-061; SC-033).

One operation, one return type, and three prohibitions that are the whole contract:

* it **never raises a provider exception** — a transport failure is an outcome, not an escape;
* it **never returns a provider object** — no response, session, client or model crosses back;
* it **never forwards provider error text** — a provider's own message is uncontrolled content and
  `FR-061` keeps it out of every record and every response.

An adapter that cannot honour the three has failed the contract, and `T103`'s import gate proves the
core cannot reach a provider SDK to break them accidentally.

The port takes a :class:`RenderedPresentation` and a :class:`ChannelDestination`, and nothing else.
In particular it takes no credential: material is resolved **inside** the adapter through the
injected `SecretResolver`, at the moment of use, and never returned to the core (`FR-071`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts.delivery import ChannelDestination, DeliveryOutcome
from ..contracts.presentation import RenderedPresentation

__all__ = ["DeliveryPort", "FragmentReceipt"]


class FragmentReceipt:
    """What an adapter reports about one fragment. Carries no provider artifact.

    ``accepted`` is the provider's answer reduced to a fact the core may hold. ``indeterminate``
    means the send timed out after the provider may have accepted — the honest third state, kept
    distinct from ``accepted=False`` because the two license different next steps.
    """

    __slots__ = ("accepted", "indeterminate", "index")

    def __init__(self, index: int, accepted: bool, indeterminate: bool = False) -> None:
        if accepted and indeterminate:
            raise ValueError("a fragment cannot be both accepted and indeterminate")
        self.index = index
        self.accepted = accepted
        self.indeterminate = indeterminate

    def __repr__(self) -> str:  # pragma: no cover - failure readability
        return (
            f"FragmentReceipt(index={self.index}, accepted={self.accepted}, "
            f"indeterminate={self.indeterminate})"
        )


@runtime_checkable
class DeliveryPort(Protocol):
    """Sends one rendered presentation to one destination, and reports an outcome."""

    def send(
        self,
        presentation: RenderedPresentation,
        destination: ChannelDestination,
    ) -> tuple[DeliveryOutcome, tuple[FragmentReceipt, ...]]:
        """Send every fragment in order, returning the outcome and one receipt per fragment.

        The receipts exist so a partial acceptance is **visible** rather than averaged into a single
        boolean: fragment three failing after one and two were accepted is a different situation
        from nothing being sent, and `T096` asserts the difference.
        """
        ...
