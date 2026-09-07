"""What a resolution actually proved — T074 (FR-005, FR-011; SC-001).

``ResolutionBasis`` is load-bearing, not decorative. `002`'s
`analytics-query-contract.md` §4.4.1 establishes that three of `001`'s six
dimensions declare ``permitted_values: open``, so a ``country`` or
``app_version`` term can be validated for governed **type and shape** only —
there is no set to test membership against.

| Basis | Proves | Example |
|---|---|---|
| ``ENUMERATED_MEMBERSHIP`` | the value **is in** the governed closed
  list | ``platform = android`` |
| ``OPEN_TEXT_SHAPE`` | the value is *shaped* like one; nothing about existence | ``country = BR`` |
| ``GOVERNED_EXPRESSION`` | a `D-18` expression governed the resolution | a period expression |

An open-text resolution proves **strictly less** than an enumerated one, and must
never be presented with the same standing (`R-5`). A country term that is merely
shape-valid has not been shown to exist in the data, and an answer implying it
has would be confidently wrong in the way `001`'s `BO-4` exists to prevent.

So the basis travels **with** every resolution rather than being recomputed at
presentation time. Recomputing would mean deciding twice, and the second decision
would have lost the dimension's declaration.

This module maps a dimension's governed type to the basis its values can carry.
It authors no dimension type and no permitted-value list — both are `001`
content, read through `002`'s closed ``DimensionType`` vocabulary.
"""

from __future__ import annotations

from analytics_query.contracts.operators import DimensionType

from ..contracts._base import ContractViolation
from ..contracts.intent import ResolutionBasis
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "BASIS_FOR_DIMENSION_TYPE",
    "basis_for_dimension_type",
    "is_weaker_than",
]

#: Which basis a value resolved against each governed dimension type can carry.
#:
#: ``TEMPORAL_DATE`` is deliberately absent. `002` §4.3.1 establishes that the
#: date dimension is **not filterable at all** — ``date_range`` is the sole
#: temporal bound — so there is no such thing as a resolved date *value*, and
#: giving it a basis would imply one exists.
BASIS_FOR_DIMENSION_TYPE: dict[DimensionType, ResolutionBasis] = {
    DimensionType.ENUMERATED_TEXT: ResolutionBasis.ENUMERATED_MEMBERSHIP,
    DimensionType.OPEN_TEXT: ResolutionBasis.OPEN_TEXT_SHAPE,
}

#: Ordered weakest-first. Used only to compare *standing*, never to pick between
#: candidates — a stronger basis does not make a term more likely to be what the
#: user meant, it makes the claim about it stronger.
_STRENGTH: tuple[ResolutionBasis, ...] = (
    ResolutionBasis.OPEN_TEXT_SHAPE,
    ResolutionBasis.ENUMERATED_MEMBERSHIP,
    ResolutionBasis.GOVERNED_EXPRESSION,
)


def basis_for_dimension_type(dimension_type: DimensionType) -> ResolutionBasis:
    """The basis a value of this dimension type can be resolved on.

    ``TEMPORAL_DATE`` refuses rather than returning a basis. A date is a valid
    breakdown and an invalid filter, and this function is asked only about
    filter values — answering would manufacture a resolution the request
    contract cannot express.
    """
    try:
        return BASIS_FOR_DIMENSION_TYPE[dimension_type]
    except KeyError as exc:
        raise ContractViolation(
            InterpretationReasonCode.TERM_NOT_GOVERNED,
            "the date dimension is not filterable; the governed date range is the "
            "sole temporal bound",
        ) from exc


def is_weaker_than(basis: ResolutionBasis, other: ResolutionBasis) -> bool:
    """Whether ``basis`` proves less than ``other``.

    Exists so a presenter can refuse to give an open-text resolution enumerated
    standing without re-deriving the ordering from a comparison somewhere else.
    """
    return _STRENGTH.index(basis) < _STRENGTH.index(other)
