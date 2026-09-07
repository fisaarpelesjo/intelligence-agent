"""Refusal assembly — T132 (FR-021, FR-022, FR-024, FR-058, FR-059; SC-015, SC-016).

`FR-058` and `FR-059` are this module's because both are *passthroughs*: an unpublished
source and an unanswerable retention question are upstream verdicts, and this module's
job is to carry them with their own code and wording rather than to judge either. There
is deliberately no local code for staleness or retention — see `refuse_upstream`.

**Upstream code and message passed through unmodified. No upstream refusal is
restated.**

When `001` or `002` refuses, that refusal is the answer. This layer carries the
code and the pt-BR wording verbatim and adds nothing — because restating an
upstream refusal in this feature's vocabulary would let a consumer tell *which
layer* refused from message style, and because a paraphrase of a governed
sentence is a sentence nobody governed.

A refusal this feature originates carries an ``InterpretationReasonCode`` and a
``LocalizedRef`` into its own registry. The two shapes are distinguishable by
type, which is what keeps "we refused" and "the catalog refused" from blurring.

## Exactly one code

Not a list, not a primary-plus-details. A refusal naming two reasons invites the
reader to fix one and retry, and the second was equally disqualifying. The
contract carries one code and the type does not admit a second.

## The refusal discloses nothing

Its detail names no candidate, no count, no identifier, no limit, no policy
value, no scope, no tag and no warehouse fact. Specifically:

* **inaccessible and nonexistent are symmetric.** A term the principal may not
  see refuses identically to one that does not exist — otherwise "you may not see
  this" tells an unauthorized caller the term exists, and repeated across a
  vocabulary that maps the catalog from outside;
* **nothing is echoed.** Not a malformed language value, not injected text, not a
  question span. `FR-045` forbids repeating the content back even to say it was
  refused;
* **no analytical value.** No result, row, cell, partial ``DerivedFigure``,
  partial provenance or partially collected caveat. A refusal is not a place to
  put the half of an answer that worked.

## A narrower alternative is disclosure only

`FR-024` permits stating that a narrower request *would* be answerable. It is
never submitted, never executed and never answered — offering it as a fait
accompli would answer a question the caller did not ask, under an authorization
they were not asked to confirm.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from ..contracts._base import ContractViolation, InteractionModel, LocalizedRef, build
from ..contracts.intent import ResolvedIntent
from ..contracts.reason_codes import InterpretationReasonCode, outcome_for

if TYPE_CHECKING:  # pragma: no cover - typing only
    from analytics_query.contracts.reason_codes import AnalyticsReasonCode
    from semantic_catalog.contracts.reason_codes import ReasonCode

__all__ = [
    "GovernedRefusal",
    "NarrowerAlternative",
    "refuse_locally",
    "refuse_upstream",
]


class NarrowerAlternative(InteractionModel):
    """A request that would have been answerable. **Disclosure, never a payload.**

    Carries governed identifiers and a pointer into governed wording — no result,
    no value, and no constructed request. Naming what would work is disclosure;
    running it is answering a question nobody asked.
    """

    metrics: tuple[str, ...] = Field(min_length=1)
    sources: tuple[str, ...] = ()
    detail: LocalizedRef


class GovernedRefusal(InteractionModel):
    """One governed refusal. **Exactly one code, and it names where it came from.**

    ``upstream_code`` and ``upstream_message`` are set together or not at all: a
    refusal that came from `001` or `002` carries both verbatim, and one this
    feature originated carries neither. ``message`` is this layer's governed
    pointer and is present only on a local refusal, so the two never both speak.

    There is **no channel field**, no format and no template — a refusal is a
    structured contract exactly as an answer is.
    """

    code: InterpretationReasonCode | None = None
    message: LocalizedRef | None = None
    upstream_code: str | None = None
    upstream_message: str | None = None
    interpreted: ResolvedIntent | None = None
    alternative: NarrowerAlternative | None = None

    @model_validator(mode="after")
    def _exactly_one_origin_speaks(self) -> GovernedRefusal:
        """Local or upstream, never both and never neither.

        Both would let a consumer read this layer's wording as the governed
        reason; neither would be a refusal that names nothing, which `SC-004`'s
        no-generic-refusals rule forbids.
        """
        local = self.code is not None
        upstream = self.upstream_code is not None

        if local == upstream:
            raise ValueError(
                "a refusal carries either this feature's governed code or an upstream one, "
                "never both and never neither"
            )
        if local and self.message is None:
            raise ValueError("a local refusal carries its governed wording pointer")
        if upstream and not self.upstream_message:
            raise ValueError("an upstream refusal carries the upstream wording verbatim")
        if local and (self.upstream_message is not None):
            raise ValueError("a local refusal restates no upstream message")
        return self

    @model_validator(mode="after")
    def _a_refusal_is_not_permissive(self) -> GovernedRefusal:
        """A local refusal's code must actually be a refusal.

        ``QUESTION_ANSWERED`` and ``QUESTION_ANSWERED_WITH_CAVEAT`` are permitted
        outcomes; putting one on a refusal would produce a response that says it
        refused and codes as success.

        Both of them. The check compared against ``"ALLOW"`` alone, which let
        ``QUESTION_ANSWERED_WITH_CAVEAT`` — outcome ``ALLOW_WITH_CAVEAT`` — through:
        a refusal codeable as a caveated answer, which is the more dangerous of the
        two because a consumer reading the outcome would surface the caveats of an
        answer that does not exist.

        Expressed as "the outcome must be ``DENY``" rather than as a list of
        permitted outcomes to exclude. An outcome added to the enum later is then
        forbidden on a refusal by default, instead of being permitted until somebody
        notices the denylist is short — which is exactly how this defect arose.
        """
        if self.code is not None and outcome_for(self.code).value != "DENY":
            raise ValueError(f"{self.code.value} is a permitted outcome, not a refusal")
        return self


def refuse_upstream(
    code: ReasonCode | AnalyticsReasonCode,
    message: str,
    *,
    interpreted: ResolvedIntent | None = None,
    alternative: NarrowerAlternative | None = None,
) -> GovernedRefusal:
    """Carry an upstream refusal through, **unmodified**.

    The code is stringified rather than mapped onto this feature's namespace, and
    the message travels byte-for-byte. Translating the code would tell the caller
    that the interaction layer refused when the catalog did; re-wording the
    message would replace a governed sentence with one nobody approved.

    An empty message refuses to build: an upstream refusal with no wording is one
    the caller cannot read, and substituting local wording for it would be the
    restatement this function exists to prevent.
    """
    if not message.strip():
        raise ContractViolation(
            InterpretationReasonCode.INTAKE_MALFORMED,
            "an upstream refusal carries its own wording; none was supplied",
        )

    return build(
        GovernedRefusal,
        upstream_code=str(code),
        upstream_message=message,
        interpreted=interpreted,
        alternative=alternative,
    )


def refuse_locally(
    code: InterpretationReasonCode,
    *,
    language: str,
    content_version: str,
    interpreted: ResolvedIntent | None = None,
    alternative: NarrowerAlternative | None = None,
) -> GovernedRefusal:
    """A refusal this feature originated, worded from its own governed registry.

    The wording is a **pointer**, resolved at render time. Nothing is formatted
    here and no value is interpolated, so a refusal cannot echo a malformed
    language value, an injected span or a hidden identifier — there is no
    parameter through which one could arrive.

    ``interpreted`` is optional because a refusal before interpretation has no
    intent to disclose. `FR-042` requires it on responses that *have* one, and an
    absent field is honest where a zero-filled one would not be.
    """
    return build(
        GovernedRefusal,
        code=code,
        message=LocalizedRef(code=code.value, language=language, content_version=content_version),
        interpreted=interpreted,
        alternative=alternative,
    )
