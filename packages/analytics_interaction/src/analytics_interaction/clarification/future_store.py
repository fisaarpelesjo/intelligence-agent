"""The conversation store's boundary — declared here, implemented by `011` — T121 (FR-081/082).

## AMENDED by `OD-69`, 2026-08-31 — the owner opened the boundary, and the amendment is narrow

`NG-17` said the store stays out of this feature entirely, and the Protocol below said *no code
path accepts one*. Both were right for their day: the rule was written before any memory existed,
so that a prohibition would precede every implementation. The memory now exists — `011`'s
`conversation_context`, fourteen nodes, `FR-1106` enforcing in advance exactly what
`STORE_MUST_NEVER_OWN` names — and the owner chose, among three options with one recommended, to
amend the boundary rather than leave the memory unreachable.

**What the amendment IS**: `resume` may read and write `011`'s memory **through the contracts in
this module** — `ConversationMemory` below — never through a path of its own, and never carrying
what `FR-082` forbids (the structured-only signatures are the enforcement, not a comment).

**What it is NOT**: licence to persist anything else. Every other prohibition stands unamended: no
cache, no nonce registry beyond `ConversationStore`, no module-level state, no raw question text,
no free-text replies, no metric or filter values. The AST nodes that watched the old rule now watch
THIS rule.

**Nothing else of the store is built here.** No PostgreSQL, no schema, no migration, no
server-side accounting, no cache, no queue. `T121`'s own
evidence line requires a static test asserting this module contains declarations
and types only, and `NG-17` puts the store out of scope for this feature
entirely.

What *is* here is the boundary a later feature must cross, written down while the
reasons are still fresh.

## Why declare a boundary for something that does not exist

`FR-081` requires this contract to be versioned such that a governed conversation
store can assume ownership **without changing the semantic meaning of any
field**, the governed codes emitted, or the conditions under which a resumption
refuses. Adding the store must change *where* a fact is checked, never *what* it
means.

That is a property of today's design, not tomorrow's. If it is not pinned now, it
will be discovered to be false later — when the store is half-built and the
cheapest fix is to redefine a field.

## What the store would own, and what it must never own

| Would own | Must never own |
|---|---|
| Single-use consumption records | Raw question text |
| Server-side round accounting | Free-text clarification replies |
| Cross-turn correlation | Metric values |
| — | Filter values |

`FR-053` and `FR-055`'s prohibitions apply to it **in advance** (`FR-082`), so
the boundary constrains a component nobody has written. That ordering is
deliberate: a prohibition written after an implementation is a negotiation.

## What must not change when it arrives

:data:`INVARIANT_SEMANTICS` names them. The store may make
``single_use_consumption`` detectable — that is the one thing it adds — and it may
move round accounting server-side. It may not change what ``expires_at`` means,
which code a tampered contract produces, or whether a version mismatch refuses.

`T122` pins those semantics as a contract test, so the day the store lands the
suite says whether it kept its promises.

## The baseline deviation

`docs/intelligence-agent.yaml` declares
``agent.state_management.conversational_state: PostgreSQL``. This feature
deviates formally as ADR 0014's `BD-1`. The baseline is not wrong about the
eventual architecture — `FR-081` exists precisely so that store can arrive later.
It is wrong about *this feature*, and the deviation records the distinction
rather than letting a reader assume a PostgreSQL dependency exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping
    from datetime import datetime

__all__ = [
    "INVARIANT_SEMANTICS",
    "STORE_MUST_NEVER_OWN",
    "STORE_WOULD_OWN",
    "ConversationMemory",
    "ConversationStore",
]

#: What a governed conversation store would take ownership of. Declared so the
#: later feature inherits the list rather than deriving it from behaviour.
STORE_WOULD_OWN: tuple[str, ...] = (
    "single_use_consumption_records",
    "server_side_round_accounting",
    "cross_turn_correlation",
)

#: What it must never hold, whatever else it does. `FR-053` and `FR-055` applied
#: in advance to a component that does not exist (`FR-082`).
STORE_MUST_NEVER_OWN: tuple[str, ...] = (
    "raw_question_text",
    "free_text_clarification_replies",
    "metric_values",
    "filter_values",
)

#: The semantics the store may **not** change by arriving. `T122` asserts each
#: against today's behaviour, so the promise is checkable now and re-checkable
#: the day the store lands.
INVARIANT_SEMANTICS: tuple[str, ...] = (
    "contract_field_meanings",
    "governed_reason_codes",
    "refusal_conditions",
    "seal_coverage",
    "identity_binding",
    "expiry_semantics",
)


@runtime_checkable
class ConversationStore(Protocol):
    """The shape a governed conversation store would take. **Unimplemented.**

    A ``Protocol`` and nothing else: no class implements it, no module
    constructs one, and no code path accepts one. It exists so the later feature
    starts from a declared surface rather than from an invented one, and so the
    static test has something specific to assert the absence of.

    Two methods, and the asymmetry is the point. ``record_consumption`` is what
    the store *adds* — the single thing a stateless contract cannot do. ``consumed``
    is what it answers. Neither weakens any check this feature already performs:
    the store narrows replay, and narrows nothing else.

    Deliberately **not** declared: anything that would take custody of question
    text, reply text or values. A method that could accept one would be a method
    somebody eventually calls.
    """

    def record_consumption(self, nonce: str, *, correlation_id: str) -> None:
        """Record that a contract nonce was consumed. **The store's whole addition.**"""
        ...

    def consumed(self, nonce: str, *, correlation_id: str) -> bool:
        """Whether this nonce was already consumed.

        Returns a bool rather than raising, for the same reason the seal port
        does: the governed refusal and its reason code belong to this feature.
        """
        ...


@runtime_checkable
class ConversationMemory(Protocol):
    """The memory seam `OD-69` opened — structured turns only, three-state reads.

    Declared HERE because the amendment's whole rule is *through the contract, never a path of
    one's own*: a consumer in this package may hold a `ConversationMemory` and nothing else, and
    the signatures are the `FR-082` enforcement — there is no parameter a raw question, a free-text
    reply, a metric value or a filter value could travel in. `metric_ids` are catalog identifiers;
    `period` is a governed descriptor; `filter_fields` are field NAMES.

    `remembered_window` answers three states with primitives, so this module need import nothing of
    `011`: a tuple of mappings (the window, oldest first), an **empty tuple** (nothing remembered —
    safe to proceed context-free), or **`None`** (the store could not answer — the caller proceeds
    context-free AND SAYS SO, never treating it as a fresh conversation).
    """

    def remember_turn(
        self,
        *,
        identity: str,
        scope: str,
        message_id: str,
        intent: str,
        metric_ids: tuple[str, ...],
        period: str,
        filter_fields: tuple[str, ...],
        instant: datetime,
    ) -> bool:
        """Store one turn; ``False`` when the (identity, message id) pair already has one."""
        ...

    def remembered_window(
        self, identity: str, *, now: datetime
    ) -> tuple[Mapping[str, object], ...] | None:
        """The remembered window, ``()`` for nothing, ``None`` for could-not-read."""
        ...
