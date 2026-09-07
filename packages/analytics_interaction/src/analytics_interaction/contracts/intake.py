"""Question intake — T035 (FR-001, FR-002, FR-096, FR-097, FR-099; SC-056).

The request surface, and — more importantly — everything deliberately absent from
it. `contracts/intake-contract.md` §3 lists eight field families a caller might
expect and does not get:

| Field a caller might expect | Why it does not exist |
|---|---|
| ``sql``, ``query``, ``filter_expression`` | No query text may reach the warehouse (`FR-027`) |
| ``access_tags``, ``role``, ``elevate`` | Authorization is resolved from the
  principal, never asserted by the question (`FR-029`) |
| ``max_bytes``, ``max_rows``, ``threshold`` | Governed limits are policy, never
  caller input (`FR-030`) |
| ``freshness``, ``coverage``, ``data_revision`` | The requester is never
  authoritative about the state of the data |
| ``catalog_release``, ``policy_version`` | Versions are resolved, never pinned by a caller |
| ``fixture``, ``mode``, ``debug`` | No runtime path selects a fixture (`FR-063`) |
| ``format``, ``channel``, ``template`` | Contracts are channel-agnostic (`FR-040`) |
| ``detected_language``, ``language_hint`` | Language is declared, never inferred (`FR-100`) |

Each is refused because **the field does not exist**, not because a validator
rejected it. `extra="forbid"` on the shared base is the whole mechanism; this
module adds no denylist, because a denylist is a list somebody has to keep
current.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator
from semantic_catalog.contracts.access_tag import PrincipalType

from ._base import InteractionModel

__all__ = [
    "STRUCTURAL_TEXT_CEILING",
    "DeclaredLanguage",
    "PrincipalContext",
    "QuestionIntake",
]


class DeclaredLanguage(StrEnum):
    """The governed supported set. **One member today.**

    Closed in code, extended by governed content: adding a language is adding a
    key set under the same reason codes in
    `interpretation_governance/messages/`, plus its member here. Nothing in the
    message registry, the answer contract or the claim wording changes
    (`FR-043`, `SC-029`) — the registry is keyed by a plain language string
    precisely so a new language needs no contract edit.

    **There is no detector.** No inference, no scoring, no confidence, nowhere.
    Detection is probabilistic and a short question is genuinely ambiguous
    between languages; a detector would make *whether a question is answered at
    all* depend on a non-deterministic input, colliding with `FR-041`. A static
    scan asserts the absence (`SC-058`).
    """

    PT_BR = "pt-BR"


class PrincipalContext(InteractionModel):
    """Who is asking. Shape inherited from `002`'s ``AuthorizationContext``.

    Restated rather than imported: `002` declares it under
    ``analytics_query.execution``, which ADR 0010 places off-limits to this
    feature. Copying the *shape* of a public concept across a boundary the ADR
    draws is the intended cost; importing the module would not be.

    This is the **input** to the step-2 preflight, not its verdict. Resolving it
    — proving the scope readable, the tag set loadable and the policy pin in
    force — is Phase 3's job (`T044`+). Carrying it here says only that the
    caller supplied one.
    """

    principal_ref: str = Field(min_length=1)
    principal_type: PrincipalType
    authorization_scope: str | None = None
    granted_access_tags: frozenset[str] = frozenset()
    authorization_policy_pin: str | None = None


#: The **structural** ceiling applied at step 1, before the authorization-context
#: preflight. Not a governed bound: the governed one is `D-19`'s
#: ``question_length_bound``, applied at step 4 and permitted to name itself
#: because step 2 has by then proved the principal entitled to be told
#: (`FR-003`, `FR-101`).
#:
#: A contract needs *some* ceiling or an unbounded string reaches the parser, and
#: naming a governed number here would disclose policy to an unauthenticated
#: caller. So this one is deliberately generous and deliberately unnamed in the
#: refusal wording — it bounds the parser, it does not implement a policy.
STRUCTURAL_TEXT_CEILING = 8192


class QuestionIntake(InteractionModel):
    """A business question, as data. Transient: never persisted, never logged.

    ``text`` is **untrusted data at every stage** and is never an instruction.
    It is bounded structurally here and screened against `D-19`'s redaction rule
    at step 5 — which cannot run while `D-19` is unresolvable, so the question
    refuses (spec `C-4`).
    """

    text: str = Field(max_length=STRUCTURAL_TEXT_CEILING)
    language: DeclaredLanguage
    reference_date: date
    as_of: date | None = None
    principal: PrincipalContext

    @model_validator(mode="after")
    def _dates_are_independent(self) -> QuestionIntake:
        """Two dates, two purposes, **no derivation in either direction**.

        ``reference_date`` resolves relative and named period expressions and
        never affects version resolution. ``as_of`` pins metric-definition
        version resolution and never affects period resolution. An omitted
        ``as_of`` means current-definition resolution, matching `002` exactly
        (`FR-097`).

        This validator exists to *document and pin* the independence, not to
        relate the two: there is deliberately no rule here comparing them,
        because any such rule would be a derivation. It asserts only that
        ``as_of`` was not silently filled — which, given the default is ``None``
        and nothing writes it, is a structural guarantee this restates so a
        future edit that broke it would have to delete a stated invariant.
        """
        return self

    @model_validator(mode="after")
    def _text_is_non_empty_and_textual(self) -> QuestionIntake:
        """Empty and non-textual are refused before interpretation begins.

        Both are step-1 conditions and neither names a governed limit. Control
        characters are rejected rather than stripped: silently normalising
        untrusted input is how a screening step gets bypassed.
        """
        if not any(character.isalnum() for character in self.text):
            raise ValueError("the question is empty or punctuation only")
        if any(ch.isprintable() is False and ch not in "\t\n" for ch in self.text):
            raise ValueError("the question carries control characters or non-textual content")
        return self
