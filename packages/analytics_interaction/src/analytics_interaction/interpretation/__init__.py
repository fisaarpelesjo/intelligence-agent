"""Slot resolution against the catalog's access-filtered discovery surface,
period resolution through governed expressions, and the optional narrowing-only
model port.

**Deterministic only, today and by design.** Every module here calls `001`'s
discovery surface or applies a `D-18` rule; none implements matching of its own.
No fuzzy comparison, no similarity threshold, no spell correction, no embedding,
no translation and no model call exists in this package — `001` owns the single
threshold in the stack and states why it is fixed.

`model_port.py` declares a provider-neutral ``Protocol`` and **no**
implementation. While `D-20` is undeclared the gate in `compliance/gates.py`
refuses before any provider is touched, so ambiguity clarifies or refuses
rather than waiting for a model that is not there.

Every catalog read requires an ``AuthorizedContext`` in the signature, so no
discovery can precede the step-2 preflight.
"""

from .basis import BASIS_FOR_DIMENSION_TYPE, basis_for_dimension_type, is_weaker_than
from .calculations import UnsupportedCalculation, refuse_decomposition, refuse_unsupported
from .model_port import (
    CandidateOption,
    CandidateSelection,
    CandidateSet,
    DelimitedQuestionData,
    InterpretationModelPort,
    narrow_candidates,
    validate_selection,
)
from .operators import GOVERNED_OPERATORS, arity_of, require_governed_operator
from .outcomes import LifecycleStanding, SlotOutcome, TermOutcome, classify, standing_of
from .period import (
    locate_expression,
    normalise_surface,
    resolve_explicit_period,
    resolve_expression,
    resolve_governed_period,
    resolve_period_in_question,
)
from .resolve_terms import (
    REPRESENTABLE_MATCH_KINDS,
    CatalogDiscovery,
    TermRequest,
    access_context_for,
    candidate_refs,
    discover,
    match_kind_for,
    ordered_candidates,
    resolve_term,
)
from .roles import RoleReading, RoleVerdict, resolve_role
from .slots import FILL_ORDER, SLOT_KINDS, fill_position, ordered_slots

__all__ = [
    "BASIS_FOR_DIMENSION_TYPE",
    "FILL_ORDER",
    "GOVERNED_OPERATORS",
    "REPRESENTABLE_MATCH_KINDS",
    "SLOT_KINDS",
    "CandidateOption",
    "CandidateSelection",
    "CandidateSet",
    "CatalogDiscovery",
    "DelimitedQuestionData",
    "InterpretationModelPort",
    "LifecycleStanding",
    "RoleReading",
    "RoleVerdict",
    "SlotOutcome",
    "TermOutcome",
    "TermRequest",
    "UnsupportedCalculation",
    "access_context_for",
    "arity_of",
    "basis_for_dimension_type",
    "candidate_refs",
    "classify",
    "discover",
    "fill_position",
    "is_weaker_than",
    "locate_expression",
    "match_kind_for",
    "narrow_candidates",
    "normalise_surface",
    "ordered_candidates",
    "ordered_slots",
    "refuse_decomposition",
    "refuse_unsupported",
    "require_governed_operator",
    "resolve_explicit_period",
    "resolve_expression",
    "resolve_governed_period",
    "resolve_period_in_question",
    "resolve_role",
    "resolve_term",
    "standing_of",
    "validate_selection",
]
