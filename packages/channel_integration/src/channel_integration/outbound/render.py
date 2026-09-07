"""Rendering — T071 (ADR 0022; FR-043 to FR-052; SC-015 to SC-022).

```
render_for_channel(payload, channel) -> RenderedPresentation | ChannelRefusal
```

Pure, total, deterministic. No clock, no network, no model, no ambient state, no I/O.

**No arithmetic and no string generation exist in this module.** A structural claim, asserted by
`T090`'s scan rather than promised here: no addition over numbers, no formatting of a value, no
rounding, no unit conversion. Every value reaches the output the way it arrived — ``str`` over the
``Decimal`` `002` produced — because a number this feature formatted is a number this feature could
format wrongly.

**Every governed string is copied, never composed.** The renderer's whole vocabulary is: the
resolved strings the payload carries, the labels the `D-28` matrix declares, and the structural
separators the matrix permits. It has no sentence of its own, so a greeting, an apology, a
suggestion, an explanation or a bridging clause has nowhere to come from (`FR-046`, `SC-018`).

**The four claim classes stay distinguishable to a reader**, by governed label from the matrix —
never by emoji, colour or position, because position is not a label and an emoji is not governed
content (`FR-048`, `SC-022`). A matrix that labels only some of the four cannot keep the rest
distinguishable, so a partial label set withholds.

**A missing resolved string withholds** (ADR 0026). The renderer does not resolve a reference,
does not render one, and does not drop the claim it belongs to.

While `D-28` is undeclared the capability matrix does not resolve, so every call refuses for every
channel and every payload. That is the shipped behaviour and the lock, not a gap.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

from analytics_interaction.contracts.answer import AnalyticsAnswer, AnswerClaim, ClaimClass

from ..contracts._base import ChannelViolation
from ..contracts.descriptor import ChannelId
from ..contracts.presentation import Degradation, RenderedPresentation
from ..contracts.refusal import ChannelRefusal
from ..governance.capabilities import resolve_capability_matrix
from ..governance.resolve import ContentUnresolvable
from .continuation import fragments_for
from .payload import GovernedAnswerPayload, ResolvedWording
from .withhold import NotRepresentable, withheld

__all__ = ["CLAIM_CLASS_LABEL_KEYS", "render_answer", "render_for_channel", "subject_is_internal"]

#: Which matrix key carries the governed pt-BR label for each claim class. The mapping lives
#: here; the **labels** are `D-28` content, never authored in this repository.
#: `F99`. The list bullet the owner approved, and the character is a decision he made rather than a
#: default: "-" is the only one that renders identically in Telegram, WhatsApp, Slack and an
#: arbitrary webhook consumer. A Unicode bullet was not measured across the four and is not used.
#:
#: It lives here rather than in `preserve.py` because it is a rendering decision, and because
#: `preserve.py` already imports from this module -- the other direction would be circular.
BULLET_PREFIX: Final = "- "

#: Bound so the joins below read as structure rather than as an escape.
NEWLINE: Final = chr(10)

CLAIM_CLASS_LABEL_KEYS: Mapping[ClaimClass, str] = {
    ClaimClass.FACTUAL_RESULT: "label_factual_result",
    ClaimClass.CALCULATED_COMPARISON: "label_calculated_comparison",
    ClaimClass.INTERPRETATION: "label_interpretation",
    ClaimClass.LIMITATION: "label_limitation",
}


def claim_labels(capability: Mapping[str, Any]) -> Mapping[ClaimClass, str]:
    """The governed label for each of the four classes, or refuse.

    All four are required together. A matrix that labels three cannot keep the fourth
    distinguishable, and a reader who cannot tell an interpretation from a finding is the failure
    `SC-022` exists to prevent.
    """
    labels: object = capability.get("claim_class_labels")
    if not isinstance(labels, Mapping):
        raise NotRepresentable("the capability entry declares no claim_class_labels mapping")
    declared = cast("Mapping[str, object]", labels)
    resolved: dict[ClaimClass, str] = {}
    for claim_class, key in CLAIM_CLASS_LABEL_KEYS.items():
        label = declared.get(key)
        if not isinstance(label, str) or not label.strip():
            raise NotRepresentable(f"no governed label for claim class {claim_class.value}")
        resolved[claim_class] = label
    return resolved


def value_text(claim: AnswerClaim) -> str | None:
    """A claim's value as text, or ``None`` when it carries none.

    ``str`` over the ``Decimal``, and nothing else: no rounding, no separator, no locale, no
    conversion. The unit is appended verbatim when declared, because a number without its unit is a
    different fact.
    """
    if claim.value is None:
        return None
    rendered = str(claim.value)
    return rendered if claim.unit is None else f"{rendered} {claim.unit}"


def subject_is_internal(claim: AnswerClaim, metrics: Sequence[str]) -> bool:
    """Whether ``claim.subject`` is the metric's internal identifier rather than something to read.

    **`F97`, and the reason it is a predicate over data rather than a rule of thumb.** The subject
    is authorised to be a metric id, a dimension or a row label
    (`assert_claims_are_authorised`), and those are not the same kind of thing to a reader.
    Measured on two real answers:

    * without a dimension the subject falls back to the metric id, and `summary_new_trials` reached
      the owner on **every** label line -- four times in one fragment;
    * with a dimension the subject IS the row label, and dropping it delivered two claims reading
      ``resultado medido: / instalacoes / 18432 instalacoes`` with nothing saying which was Android
      and which was iOS. That is worse than the leak it would have fixed, and the owner's approved
      shape shows those labels explicitly.

    So the answer's own ``interpreted.metrics`` decides. Not a heuristic on the string, not a
    prefix match, not a guess about which names look internal: the same list the intent resolved.
    """
    return claim.subject in tuple(metrics)


def claim_block(
    claim: AnswerClaim,
    labels: Mapping[ClaimClass, str],
    wording: ResolvedWording,
    metrics: Sequence[str],
) -> tuple[str, tuple[str, ...]]:
    """One claim as one governed bullet line, plus the governed strings it carries.

    The strings are returned separately so the preservation gate can byte-compare them rather than
    parsing them back out of a rendered body.

    **`metrics` has no default, and `F98` is why.** There is one caller today, so a default would be
    unreachable and look harmless. It would not be: a future caller taking the default would render
    every subject while `payload_governed_strings` -- reading the real list from the payload --
    omitted the internal ones. That is renderer and gate disagreeing, which is precisely the failure
    the single shared predicate exists to prevent, and it would surface as every answer withheld
    rather than as a wrong argument. Required, so the mistake cannot be made quietly.
    """
    text = wording.text_for(claim.message.code)
    if text is None:
        # ADR 0026: absence is a withhold, never a fallback that renders the reference.
        raise NotRepresentable("the payload carries a wording reference with no resolved string")

    # `F97`. See `subject_is_internal`. When the subject is the metric's own identifier it is the
    # leak and it goes; when it is a row label it is the only thing telling the reader which figure
    # is which, and it stays.
    #
    # It leaves `governed` in the same edit whenever it leaves the body, and it has to: the
    # preservation gate byte-compares every governed string against the delivered bytes, so a
    # subject vouched for but not rendered would withhold the answer. `payload_governed_strings`
    # applies the SAME predicate, which is why the predicate is a function and not two conditions.
    #
    # What this does NOT do: `assert_claims_are_authorised` is untouched. It guards `claim.subject`
    # against fabrication and has never governed display, so the subject is still required to be a
    # metric, a dimension or a row label -- an internal one simply stops being shown.
    # `F99`. One claim is now ONE line, opened by the bullet, and the class label is no longer
    # here: `render_answer` writes it once for the whole group. Three lines per claim with the
    # label repeated above every figure was the shape the owner objected to.
    #
    # The pieces are joined with ": " and nothing else. This renderer may emit the payload's
    # governed strings, the matrix labels, `PERMITTED_SEPARATORS` and the bullet -- an em-dash or
    # a mid-line hyphen as a joiner would be content nobody authorised, which is exactly what
    # the gate is built to notice.
    if subject_is_internal(claim, metrics):
        governed: list[str] = [text]
        pieces: list[str] = [text]
    else:
        governed = [claim.subject, text]
        pieces = [claim.subject, text]
    rendered_value = value_text(claim)
    if rendered_value is not None:
        governed.append(rendered_value)
        pieces.append(rendered_value)
    # An f-string rather than `+`: `T-` scans this module for `BinOp` and refuses every one,
    # because a scan that tried to tell concatenation from arithmetic would need types. A
    # renderer that never writes `+` cannot be argued with, so it does not.
    joined = ": ".join(pieces)
    return f"{BULLET_PREFIX}{joined}", tuple(governed)


def caveat_block(answer: AnalyticsAnswer) -> tuple[str, tuple[str, ...]]:
    """The caveat block, which travels in **every** fragment (`T073`).

    Caveats already carry resolved wording upstream — ``message_pt_br`` is the one governed
    string in the answer that is not a reference — so nothing is looked up here.
    """
    strings = tuple(caveat.message_pt_br for caveat in answer.caveats.caveats)
    return "\n".join(strings), strings


def render_answer(
    payload: GovernedAnswerPayload,
    channel: ChannelId,
    capability: Mapping[str, Any],
) -> RenderedPresentation:
    """Render an answered outcome, or raise a withhold condition.

    Raises rather than returning a refusal so the single collapse point stays in
    :func:`render_for_channel`, and every caller of this function is inside that collapse.
    """
    answer = payload.answer
    labels = claim_labels(capability)

    blocks: list[str] = []
    governed: list[str] = []
    # `F97`. The metrics the intent resolved, so `claim_block` can tell an internal identifier from
    # a row label. Read from the answer rather than passed in by a caller: a renderer that accepted
    # this list from outside could be told the wrong one and would suppress a real row label.
    metrics = tuple(answer.interpreted.metrics)

    # `F99`. One block per CLASS, not per claim: the governed label opens the group and every
    # claim of that class follows as a bullet under it. `SC-022` holds exactly as before -- the
    # label is present and governed -- while a reader stops meeting it above every figure.
    #
    # Grouped by CONSECUTIVE run rather than by a fixed class order. The order of an answer's
    # claims is `003`'s decision; re-ordering them here would make this layer decide what a
    # reader meets first, which is not its call. Two claims of one class that `003` did not put
    # together stay apart, and each run gets its own label.
    grouped: list[tuple[ClaimClass, list[str]]] = []
    for claim in answer.claims:
        line, strings = claim_block(claim, labels, payload.wording, metrics)
        governed.extend(strings)
        if grouped and grouped[-1][0] == claim.claim_class:
            grouped[-1][1].append(line)
        else:
            grouped.append((claim.claim_class, [line]))
    for claim_class, lines in grouped:
        blocks.append(NEWLINE.join([f"{labels[claim_class]}:", *lines]))

    caveat_body, caveat_strings = caveat_block(answer)
    governed.extend(caveat_strings)

    if len(caveat_strings) != answer.caveats.total:
        # FR-047: the payload's declared count disagrees with what it carries. Rendering a subset is
        # the failure the count exists to make detectable, so this withholds rather than proceeding.
        raise NotRepresentable("the payload's declared caveat count does not match its caveats")

    fragments = fragments_for(blocks, capability, repeated_suffix=caveat_body)
    degradations: tuple[Degradation, ...] = ()
    return RenderedPresentation(
        channel=channel,
        fragments=fragments,
        governed_strings=tuple(governed),
        caveat_count=answer.caveats.total,
        degradations=degradations,
        language=answer.language.value,
    )


def render_for_channel(
    payload: GovernedAnswerPayload,
    channel: ChannelId,
) -> RenderedPresentation | ChannelRefusal:
    """The total operation: a presentation, or the governed refusal that withholds.

    The capability matrix resolves **here**, so the `D-28` lock applies on every path into rendering
    and cannot be bypassed by a caller that already holds a matrix mapping.
    """
    try:
        capability = resolve_capability_matrix(channel)
        return render_answer(payload, channel, capability)
    except ContentUnresolvable as unresolvable:
        return withheld(ChannelViolation(unresolvable.code, unresolvable.detail))
    except ChannelViolation as violation:
        return withheld(violation)
