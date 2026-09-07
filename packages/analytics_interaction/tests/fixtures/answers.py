"""Phase 12 test support: **fixture-only** governed claim wording.

`D-18`'s ``claim-classes.yaml`` ships with zero wordings, so **every answer
refuses today** and an assembly suite has nothing to exercise unless it supplies
its own. This is it, and it is marked at every level: the module says so, the
version string says so, and the marker is asserted to appear in no `src/` module.

**Nothing here is a proposal.** The labels and disclosure sentences below are
placeholder text carrying the fixture marker — not suggested pt-BR wording for
what a claim class should be called. That decision is `D-18` content and this
feature invents none of it. The `D-18` refusal is asserted separately against the
**real** governed file, which is the only claim about production content anything
in Phase 12 makes.

TEST-ONLY. Never readiness evidence, never governed content.
"""

from __future__ import annotations

from datetime import date

from analytics_interaction.contracts._base import LocalizedRef
from analytics_interaction.contracts.answer import ClaimClass
from analytics_interaction.governance.schemas import (
    ClaimClassContent,
    ClaimClassWording,
    ContentApproval,
)

__all__ = [
    "FIXTURE_MARKER",
    "WORDING_VERSION",
    "claim_wording",
    "ref",
]

#: Stamped into every synthetic value here, and asserted absent from `src/`.
FIXTURE_MARKER = "fixture-only-not-governed-wording"
WORDING_VERSION = f"{FIXTURE_MARKER}-v1"


def claim_wording(
    *,
    classes: tuple[ClaimClass, ...] = tuple(ClaimClass),
    version: str = WORDING_VERSION,
    effective_from: date = date(2026, 1, 1),
    effective_to: date | None = None,
) -> tuple[ClaimClassContent, ...]:
    """One fixture-only `D-18` claim-class wording instance.

    ``classes`` defaults to all four because ``resolve_claim_classes`` requires
    the effective content to cover every contract-declared class — an instance
    covering three is *incomplete*, not partially usable, and passing a shorter
    tuple is how a test exercises that.

    Returns a tuple so a test can pass zero (the shipped state), one (usable) or
    two overlapping (ambiguous, refuses) without a helper for each.
    """
    return (
        ClaimClassContent(
            version=version,
            effective_from=effective_from,
            effective_to=effective_to,
            approval=ContentApproval(
                approver_role="fixture",
                evidence_ref=FIXTURE_MARKER,
                approved_on=date(2026, 1, 1),
            ),
            classes=tuple(
                ClaimClassWording(
                    claim_class=claim_class,
                    label=f"{FIXTURE_MARKER}-label-{claim_class.value}",
                    disclosure=f"{FIXTURE_MARKER}-disclosure-{claim_class.value}",
                )
                for claim_class in classes
            ),
        ),
    )


def ref(code: str, *, content_version: str = WORDING_VERSION) -> LocalizedRef:
    """A governed pointer. **Never a built sentence.**

    Every user-facing string on the answer path is one of these, so a fixture
    that produced prose would be modelling a shape the contract forbids.
    """
    return LocalizedRef(code=code, language="pt-BR", content_version=content_version)
