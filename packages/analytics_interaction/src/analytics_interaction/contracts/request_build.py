"""Deterministic ``AnalyticsQuery`` construction — T090 (FR-026, FR-027; SC-005).

    The same resolved intent under the same versions yields a byte-identical
    request. — `tasks.md` T090

**Six fields, and `002` owns all of them.** This module builds `002`'s public
``AnalyticsQuery`` and constructs nothing of its own:

| `003` intent | `002` request |
|---|---|
| ``metrics`` | ``metrics`` |
| ``dimensions`` | ``dimensions`` |
| ``sources`` | ``sources`` |
| ``filters`` | ``filters`` |
| ``period.start`` / ``period.end`` | ``date_range`` |
| ``as_of`` | ``as_of`` |

**No query text of any kind.** No SQL, no fragment, no predicate, no plan, no
warehouse-specific field. There is no path from question text to query text
because there is no field that could hold one — `002` compiles the request, and
compiling is `002`'s alone (ADR 0010).

**The period is the date range, and only the date range.** `002` §4.3.1
establishes that the date dimension is **not filterable**: ``date_range`` is the
sole temporal bound. Building a date filter would be expressing the period twice,
in one place `002` accepts and one it rejects.

**`BD-1`: no ``comparison``, ``order_by`` or ``limit``.** `002` deliberately
excludes them, so a request naming one is rejected as an unknown field. This
module does not name them — the refusal is that the fields do not exist, not that
a rule remembered to omit them.

**Nothing is defaulted.** Not a dimension, not a source, not a filter, not a
date, not an ``as_of``, not a policy value. `002` declares four of its six fields
optional with empty-tuple defaults, and an absent collection is passed as absent
rather than as an invented one — `FR-030` forbids this feature setting,
overriding, weakening or suggesting any governed value.

**``as_of`` receives the caller's pin and nothing else.** Never
``reference_date``. The two answer different questions, and a derivation would
pin every question to the day it asked about rather than to the definitions in
force. An omitted pin stays omitted, which `002` reads as current-definition
resolution.

**This module executes nothing.** It builds a request. `001`'s catalog evaluation
and `002`'s authorization preflight remain mandatory and happen later, through
the ADR 0010 entry point — which is not called here.
"""

from __future__ import annotations

from analytics_query.contracts.request import AnalyticsQuery, DateRange

from ..authorization.context_preflight import AuthorizedContext
from ..contracts._base import ContractViolation
from ..contracts.intent import ResolvedIntent
from ..contracts.reason_codes import InterpretationReasonCode
from ..identity.authorization_fingerprint import derive_authorization_fingerprint

__all__ = ["REQUEST_FIELDS", "build_analytics_query"]

#: The six public fields `002` accepts. Named so a field added upstream is a
#: visible change here rather than a silent omission, and so the `BD-1`
#: exclusions are checkable against something.
REQUEST_FIELDS: tuple[str, ...] = (
    "metrics",
    "dimensions",
    "sources",
    "filters",
    "date_range",
    "as_of",
)


def build_analytics_query(
    intent: ResolvedIntent,
    *,
    authorized: AuthorizedContext,
    auth_fingerprint: str,
) -> AnalyticsQuery:
    """Build the governed request from a resolved intent, or refuse.

    ``authorized`` and ``auth_fingerprint`` are required for the same reason
    they are on intent assembly: a request must not be constructible from terms
    resolved under a different authorization context, and the ordering must be a
    property of the signature rather than a rule somebody remembers. A mismatch
    refuses **before** any request exists, so the counted no-construction test
    has something true to observe.

    Deterministic: every field comes from ``intent``, whose collections were
    already ordered at assembly. No clock, no randomness, no mutable state and no
    default — the same intent always produces the same request, byte for byte.

    A period is required. `002`'s ``date_range`` is required, so an intent
    without one could not become a request; refusing here names the reason while
    a caller can still act on it.
    """
    if auth_fingerprint != derive_authorization_fingerprint(authorized):
        raise ContractViolation(
            InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE,
            "the intent was resolved under a different authorization context",
        )

    if intent.period is None:
        raise ContractViolation(
            InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED,
            "a governed request requires a resolved period",
        )

    if not intent.metrics:
        raise ContractViolation(
            InterpretationReasonCode.QUESTION_NOT_ANALYTICAL,
            "a governed request requires at least one governed metric",
        )

    return AnalyticsQuery(
        metrics=intent.metrics,
        dimensions=intent.dimensions,
        sources=intent.sources,
        filters=intent.filters,
        date_range=DateRange(start=intent.period.start, end=intent.period.end),
        # The caller's pin, verbatim, including `None`. Never `reference_date`.
        as_of=intent.as_of,
    )
