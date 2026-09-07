"""Unsupported calculations refuse — T078 (FR-013, FR-014; SC-021).

Five kinds of calculation the governed vocabulary cannot express:

| Kind | Why it is not expressible |
|---|---|
| custom formula | Only `D-18`'s closed formula set is governed |
| forecast | Requires a model of the future; the catalog governs the past |
| causal attribution | Constitution II forbids causal claims outright |
| ratio of unrelated metrics | Two metrics with no declared relationship
  produce a number with no meaning |
| arbitrary re-aggregation | The metric's declared additivity says which aggregations are valid |

**And the decomposition case, which is the one that matters.** A user asking for
an unsupported figure can be told no. A user asking for the *governed steps that
would produce it* — metric A here, metric B there, "and I'll divide them" — is
asking the same question in pieces, and answering each piece is answering the
whole. `FR-013` requires the combination never to be produced, so this module
refuses the **plan**, not just the phrasing.

That is why ``refuse_decomposition`` exists separately from
``refuse_unsupported``: refusing the direct form is easy and refusing the
assembled form is the requirement. `T081` asserts the decomposition case
explicitly rather than inferring it from the direct one.

**Additivity refusals are upstream.** When a metric's declared additivity forbids
an aggregation, `001` already has a code for it and this module passes it through
verbatim rather than restating it in this layer's vocabulary (`FR-021`).
"""

from __future__ import annotations

from enum import StrEnum

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "UnsupportedCalculation",
    "refuse_decomposition",
    "refuse_unsupported",
]


class UnsupportedCalculation(StrEnum):
    """The kinds this layer refuses. Closed — an unrecognised kind is also refused.

    Named individually so a refusal can record *what* was asked for without
    quoting the question, and so `T081` can assert each separately rather than
    trusting one case to stand for five.
    """

    CUSTOM_FORMULA = "custom_formula"
    FORECAST = "forecast"
    CAUSAL_ATTRIBUTION = "causal_attribution"
    RATIO_OF_UNRELATED_METRICS = "ratio_of_unrelated_metrics"
    ARBITRARY_REAGGREGATION = "arbitrary_reaggregation"


def refuse_unsupported(kind: UnsupportedCalculation) -> ContractViolation:
    """The governed refusal for a directly-asked unsupported calculation.

    Returns rather than raises so a caller can attach it to the slot that
    produced it. The message names the *kind*, never the question — a refusal
    that quoted "faturamento dividido por instalações" would put the user's
    phrasing into whatever logged it.
    """
    return ContractViolation(
        InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
        f"the governed vocabulary cannot express a {kind.value}",
    )


def refuse_decomposition(kind: UnsupportedCalculation, *, governed_steps: int) -> ContractViolation:
    """The governed refusal for an unsupported calculation asked for in pieces.

    ``governed_steps`` is how many individually-governed steps the request
    decomposes into. It is recorded because two governed steps assembled into an
    ungoverned figure is a different fact from one ungoverned request, and a
    reviewer reading the audit trail should be able to tell them apart.

    The **same** code as the direct form, deliberately. A separate code would let
    a caller learn that decomposition was detected — and therefore that the
    boundary is worth probing — while telling them nothing they could act on.
    """
    return ContractViolation(
        InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
        f"the request decomposes into {governed_steps} governed steps whose "
        f"combination is a {kind.value}; governed steps are never combined into "
        "the unsupported figure",
    )
