"""The post-render preservation gate — T074 (ADR 0022; FR-043 to FR-048; SC-015 to SC-019).

Runs **after** rendering and **before** anything is sent. It re-validates the rendered output
against the payload and, on any divergence, emits ``CHANNEL_OUTBOUND_WITHHELD``. Nothing is sent.

Why a separate gate rather than care inside the renderer: from the outside, a correct renderer and
a subtly wrong one look the same. The gate is what makes the difference observable, and it is
written to **distrust** the renderer it follows — including the renderer's own claim about which
governed strings it carried.

Five checks, each closing a distinct way an answer changes on the way out:

1. **Every governed string the payload carries is present in the delivered bytes.** Channel syntax
   may
   surround content; it may not alter content. Absence is a removal.
2. **The renderer vouched for nothing extra.** A string in ``governed_strings`` that the payload
   never
   carried is content the renderer invented and then attested to.
3. **The caveat count matches, and every caveat appears in every fragment**, so no fragment stands
   alone as an uncaveated finding.
4. **The four claim classes remain distinguishable** by their governed labels in the delivered
   bytes. 5. **Nothing was added.** Strip every governed string, every governed label and the
   permitted
   separators; what survives is text nobody authorised — the differential half of `SC-018`.

The gate reads the payload directly. It does not accept a summary of the payload, because a
summary is the thing under test.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

from ..contracts.presentation import RenderedPresentation
from .payload import GovernedAnswerPayload
from .render import BULLET_PREFIX, CLAIM_CLASS_LABEL_KEYS, subject_is_internal, value_text
from .withhold import WithheldAfterRendering

__all__ = [
    "PreservationReport",
    "assert_preserved",
    "preservation_report",
    "strip_structure",
]

#: The separators the renderer is permitted to introduce. Closed, and small on purpose: every
#: addition here is a character the differential check stops noticing.
#:
#: **`F99` deliberately did NOT add "-" here**, and the measurement is the reason. The owner
#: approved a "-" bullet, and the obvious change was one character in this tuple. Measured on the
#: fixture
#: corpus, under three regimes, on the delivered body:
#:
#: ===================================  ======  ============  ==============
#: invented content                     today   "-" in here   bullet prefix
#: ===================================  ======  ============  ==============
#: a SIGN invented on a real figure     caught  **blind**     caught
#: a divider of nothing but dashes      caught  **blind**     caught
#: a hyphen inside invented prose       caught  caught        caught
#: ===================================  ======  ============  ==============
#:
#: The first row is the one that decides it. Stripping every "-" turns an invented ``-1234`` into
#: the governed ``1234`` and the gate sees nothing left over -- a fall rendered where a rise was
#: measured, invisible. And the approved format carries signed differences (``+6.867``), so a sign
#: is content here, not punctuation.
#:
#: So the bullet is stripped as a **prefix at the start of a line** instead, by `BULLET_PREFIX`, and
#: this tuple stays exactly as closed as it was.
PERMITTED_SEPARATORS: tuple[str, ...] = ("\n", ":", " ")

#: Matches the bullet **only** where the renderer is allowed to put one. The line anchor under
#: MULTILINE is doing the work: a "-" anywhere else in a line is still content nobody authorised.
_BULLET_AT_LINE_START = re.compile("^" + re.escape(BULLET_PREFIX), re.MULTILINE)


class PreservationReport:
    """What the gate found. Carries the divergences, not a boolean.

    A boolean would tell an operator that something changed and nothing about what, which turns a
    withheld response into an investigation.
    """

    __slots__ = ("added", "class_labels_missing", "divergences", "missing_strings")

    def __init__(
        self,
        missing_strings: tuple[str, ...],
        divergences: tuple[str, ...],
        class_labels_missing: tuple[str, ...],
        added: tuple[str, ...],
    ) -> None:
        self.missing_strings = missing_strings
        self.divergences = divergences
        self.class_labels_missing = class_labels_missing
        self.added = added

    @property
    def preserved(self) -> bool:
        return not (
            self.missing_strings or self.divergences or self.class_labels_missing or self.added
        )

    def __repr__(self) -> str:  # pragma: no cover - failure readability
        return (
            f"PreservationReport(missing={self.missing_strings!r}, "
            f"divergent={self.divergences!r}, labels_missing={self.class_labels_missing!r}, "
            f"added={self.added!r})"
        )


def strip_structure(text: str) -> str:
    """Remove everything the renderer is allowed to introduce, leaving only what it authored.

    The bullet first, then the separators. The order matters and is not cosmetic: once the
    separators are gone the line starts are gone with them, and every "-" in the text would
    look like a bullet -- which is precisely the permissiveness `F99` refused to buy.

    **This function exists because the rule was written down three times.** The gate had one
    copy and two integration tests had their own, and when `F99` taught the gate about the
    bullet the two copies kept asserting the older rule and failed. A property restated in
    three places is a property that can disagree with itself, so the callers share this.
    """
    without_bullets = _BULLET_AT_LINE_START.sub("", text)
    for separator in PERMITTED_SEPARATORS:
        without_bullets = without_bullets.replace(separator, "")
    return without_bullets


def payload_governed_strings(payload: GovernedAnswerPayload) -> tuple[str, ...]:
    """Every governed string the payload itself carries, read from the payload.

    Read from the payload rather than from the presentation, because comparing the renderer's list
    against the renderer's body would prove only that the renderer is self-consistent.
    """
    strings: list[str] = []
    # `F97`. The same list the renderer reads, for the same predicate. The gate distrusts the
    # renderer -- that is its whole point -- but "distrust" means deriving the expectation from the
    # payload independently, not applying a DIFFERENT rule: a gate that expected a string the
    # renderer correctly withheld would withhold every answer instead of catching anything.
    metrics = tuple(payload.answer.interpreted.metrics)
    for claim in payload.answer.claims:
        # An internal identifier is no longer rendered, so it is no longer expected in the bytes.
        # This narrows what the gate PROVES and the narrowing is stated rather than buried: the gate
        # no longer proves the delivered body names the metric, because the body no longer does.
        # That link is proved against the claim record instead, and if the record ever stops being
        # written, this file is not what will notice.
        if not subject_is_internal(claim, metrics):
            strings.append(claim.subject)
        text = payload.wording.text_for(claim.message.code)
        if text is not None:
            strings.append(text)
        rendered_value = value_text(claim)
        if rendered_value is not None:
            strings.append(rendered_value)
    strings.extend(caveat.message_pt_br for caveat in payload.answer.caveats.caveats)
    return tuple(strings)


def _declared_labels(capability: Mapping[str, Any]) -> Mapping[str, object]:
    labels: object = capability.get("claim_class_labels")
    if not isinstance(labels, Mapping):
        return {}
    return cast("Mapping[str, object]", labels)


def preservation_report(
    presentation: RenderedPresentation,
    payload: GovernedAnswerPayload,
    capability: Mapping[str, Any],
) -> PreservationReport:
    """Compare ``presentation`` against ``payload``. Reports; does not decide."""
    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments)
    expected = payload_governed_strings(payload)

    missing = tuple(string for string in expected if string not in delivered)
    divergences = [string for string in presentation.governed_strings if string not in expected]

    total = payload.answer.caveats.total
    caveats = tuple(caveat.message_pt_br for caveat in payload.answer.caveats.caveats)
    if presentation.caveat_count != total:
        divergences.append(f"caveat count {presentation.caveat_count} does not equal {total}")
    for fragment in presentation.fragments:
        for caveat in caveats:
            if caveat not in fragment.body:
                divergences.append(f"fragment {fragment.index}/{fragment.total} omits a caveat")

    declared_labels = _declared_labels(capability)
    labels_missing: list[str] = []
    for claim in payload.answer.claims:
        label = declared_labels.get(CLAIM_CLASS_LABEL_KEYS[claim.claim_class])
        if not isinstance(label, str) or label not in delivered:
            labels_missing.append(claim.claim_class.value)

    # Longest first. Stripping "numero 1" before "numero 12" leaves a stray "2" behind and reports
    # it as content nobody authorised — a false positive the fixture corpus caught, and the reason
    # the order is stated here rather than left to whatever order the payload happened to use.
    residue = delivered
    label_strings = [value for value in declared_labels.values() if isinstance(value, str)]
    for string in sorted({*expected, *label_strings}, key=len, reverse=True):
        residue = residue.replace(string, "")
    residue = strip_structure(residue)
    added = (residue,) if residue else ()

    return PreservationReport(
        missing, tuple(divergences), tuple(sorted(set(labels_missing))), added
    )


def assert_preserved(
    presentation: RenderedPresentation,
    payload: GovernedAnswerPayload,
    capability: Mapping[str, Any],
) -> RenderedPresentation:
    """``presentation`` unchanged when nothing diverged, or refuse.

    Returns the presentation rather than ``None`` so a caller cannot skip the gate and still hold
    something to send: what gets delivered is what this function returned.
    """
    report = preservation_report(presentation, payload, capability)
    if not report.preserved:
        raise WithheldAfterRendering(f"the rendered response diverged from the payload: {report!r}")
    return presentation
