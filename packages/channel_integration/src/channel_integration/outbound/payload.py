"""What the outbound boundary receives — Phase C, required by T071 (ADR 0026; FR-043 — FR-047).

`data-model.md` § 3 names the input `GovernedOutboundPayload`: *"exactly what the interaction
boundary produced, carried unaltered"*. This module states that shape as a **structural protocol**
rather than as a class, and the reason is the import boundary.

ADR 0026 decided that the port's answered outcome carries the `AnalyticsAnswer` **unaltered**
beside the **resolved** governed wording for every `LocalizedRef` the answer contains, with
resolution performed by `003` inside ADR 0017's new module. That concrete type therefore belongs
to `003`, and `004` must not declare it: a second declaration of an upstream contract is the
divergence the `Outcome` reconciliation already rejected once.

So what lives here is the *shape* `004` requires. `003`'s module satisfies it structurally,
pyright checks the satisfaction, and no upstream type is redeclared. A fixture double satisfies
the same shape, which is what lets Phase C be tested before the seam exists (`T118` builds the
seam, not this module).

**`004` resolves nothing.** :meth:`ResolvedWording.text_for` is a **lookup**, and a reference with
no entry returns ``None`` — at which point the caller withholds (ADR 0026 § Decision). There is no
fallback that renders the reference, resolves it, or omits the claim.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics_interaction.contracts.answer import AnalyticsAnswer
from analytics_interaction.contracts.clarification import ClarificationContract

__all__ = [
    "GovernedAnswerPayload",
    "GovernedClarificationPayload",
    "GovernedRefusalPayload",
    "ResolvedWording",
]


@runtime_checkable
class ResolvedWording(Protocol):
    """A lookup from a governed wording reference to the string `003` resolved for it."""

    #: Which governed content version produced these strings, so a rendering is attributable.
    content_version: str

    def text_for(self, code: str) -> str | None:
        """The resolved string for a reference's ``code``, or ``None``.

        ``None`` is a withhold condition, never a fallback: rendering the reference would deliver a
        pointer to a human, and resolving it here would make `004` a second wording authority.
        """
        ...


@runtime_checkable
class GovernedAnswerPayload(Protocol):
    """An answered outcome: the upstream answer, unaltered, plus its resolved wording."""

    answer: AnalyticsAnswer
    wording: ResolvedWording


@runtime_checkable
class GovernedClarificationPayload(Protocol):
    """A clarification outcome.

    The contract is transported **opaquely**: `004` reads no field of it except to carry it, and the
    candidate wording travels resolved beside it for presentation only (`FR-042`).
    """

    clarification: ClarificationContract
    wording: ResolvedWording


@runtime_checkable
class GovernedRefusalPayload(Protocol):
    """A refused outcome: exactly one upstream code and its stored wording, already resolved.

    ``code`` is typed as a string for the same reason the audit event's is: the four reason-code
    namespaces are disjoint by test, so one field carries any of them unambiguously, and a
    union would make every consumer switch on type before switching on value.
    """

    code: str
    message: str
