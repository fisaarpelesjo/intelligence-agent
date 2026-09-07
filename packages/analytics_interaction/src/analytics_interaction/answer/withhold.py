"""All or withheld — T128 (FR-086; SC-048).

**An answer whose caveats cannot be carried in full is withheld, never trimmed.**

The alternative is the quiet one: drop the caveat whose wording was unavailable
and release the rest. The number arrives, the reader sees four qualifications
instead of five, and nothing anywhere says a fifth existed. That is a
confidently-wrong answer produced by a system behaving reasonably at every step.

So the rule is all-or-nothing, and it is checked here rather than at each caveat's
construction — because "can this answer be released" is a question about the
**set**, and a per-caveat check can only ever answer it one caveat at a time.

## What "in full" means

Three conditions, and each fails differently:

* **every required caveat is present, with its multiplicity.** The requirement is
  a **multiset**, not a set: if upstream stated one governed limitation twice,
  carrying it once is carrying one fewer than upstream stated. Comparing sets
  would call that complete, and the reader would see a single qualification where
  two were issued;
* **the count agrees.** ``CaveatSet`` already enforces ``total == len(caveats)``,
  so a set that disagrees with itself cannot be built; this re-checks it because
  a caller could construct the two halves separately;
* **no caveat is empty.** A caveat carrying no wording is one nobody can read,
  and releasing it would satisfy the count while disclosing nothing.

## Withholding is not refusing to answer

It is refusing to release *this* answer. The distinction matters for the reason
code: ``DISCLOSURE_WOULD_RECONSTRUCT`` would be wrong (nothing is being
reconstructed) and so would a tampering code (nobody tampered). The governed fact
is that required governed wording was unavailable, which is what
``INTERPRETATION_VOCABULARY_UNRESOLVABLE`` says.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

    from ..contracts.answer import CaveatOrigin, CaveatSet

__all__ = ["assert_caveats_are_releasable"]


def assert_caveats_are_releasable(
    caveats: CaveatSet, *, required: Iterable[tuple[str, CaveatOrigin]]
) -> None:
    """Refuse to release unless every required caveat is carried, in full.

    ``required`` is the ``(code, origin)`` **multiset** upstream stated. Counted,
    not set-compared, for two reasons that fail differently:

    * a caveat present on side A and missing on side B is a missing caveat — the
      reader would be told one side is qualified when both are;
    * a caveat stated **twice** by one origin and carried once is also a missing
      caveat. Multiplicity may represent two decisions, two evaluations or two
      pieces of evidence, and this layer cannot tell which — so it carries the
      count rather than interpreting it.

    ``Counter`` rather than a set on purpose. A set here is precisely how a
    repeated required caveat passes validation while only one occurrence reaches
    the reader.

    Nothing is trimmed, substituted or summarised on failure. The answer does not
    go out.
    """
    carried = Counter((str(caveat.code), caveat.origin) for caveat in caveats.caveats)
    wanted = Counter(required)
    missing = sorted(
        f"{code}:{origin.value}"
        for (code, origin), count in wanted.items()
        if carried[(code, origin)] < count
    )
    if missing:
        # The detail names no code and no origin. A refusal that listed them
        # would disclose which upstream limitations applied to an answer the
        # caller is not receiving — including, on a comparison, facts about a
        # side they may not have access to.
        raise ContractViolation(
            InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE,
            "a required governed caveat could not be carried; the answer is withheld in full",
        )

    if caveats.total != len(caveats.caveats):
        raise ContractViolation(
            InterpretationReasonCode.INTAKE_MALFORMED,
            "the caveat count disagrees with the caveats carried",
        )

    if any(not caveat.message_pt_br.strip() for caveat in caveats.caveats):
        raise ContractViolation(
            InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE,
            "a carried caveat has no governed wording; the answer is withheld in full",
        )
