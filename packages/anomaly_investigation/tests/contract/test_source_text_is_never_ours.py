"""Source text travels as a value, never as a sentence of ours — T032 (`FR-014`, `SC-003a`).

A dimension label arriving from a warehouse row may read *"queda causada por
mudança de preço"*. **It is still delivered** — withholding source data would be a
different feature and a worse one. What `FR-014` forbids is the one thing that
would make it ours: interpolating it into a sentence we composed.

**And `SC-003a` states the limit rather than papering over it:** a closed
vocabulary governs what this feature *writes*, never what a warehouse row
*carries*. **A structural check over sources proves absence of origination, not
absence of causal content** — so nothing here claims the source is free of causal
language, and the tests say so.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from anomaly_investigation.contracts import ClaimType, SegmentContribution, SourceValue

pytestmark = pytest.mark.contract

#: A real label shape, and deliberately the worst one: it asserts a cause.
CAUSAL_LABEL = "queda causada por mudança de preço"


def _segment(label: SourceValue) -> SegmentContribution:
    return SegmentContribution(
        dimension="product",
        segment_label=label,
        value=Decimal("3"),
        contribution=Decimal("0.9"),
        claim_type=ClaimType.CORRELATION,
    )


def test_a_causal_label_is_delivered_rather_than_withheld() -> None:
    """**Delivered, and unchanged.** Dropping it would hide what the source says;
    editing it would make the edit ours."""
    segment = _segment(SourceValue(text=CAUSAL_LABEL, origin="product"))
    assert segment.segment_label.text == CAUSAL_LABEL


def test_the_value_says_where_it_came_from() -> None:
    """The origin is what makes it readable as *the source's* text.

    Without it, a reader sees a sentence in our output and has no way to tell
    whose sentence it is.
    """
    segment = _segment(SourceValue(text=CAUSAL_LABEL, origin="product"))
    assert segment.segment_label.origin == "product"


def test_a_label_with_no_origin_is_refused() -> None:
    """A `SourceValue` that cannot say where it came from is just a string, and a
    string in our output reads as ours."""
    with pytest.raises(ValidationError):
        SourceValue(text=CAUSAL_LABEL)  # type: ignore[call-arg]  # the point is the refusal


def test_the_label_is_not_a_bare_string_on_the_contract() -> None:
    """**The type is what makes the check possible.**

    A convention can only be reviewed; a type can be checked. Passing a raw string
    where the contract wants a `SourceValue` fails, so the origin cannot be lost
    by someone taking a shortcut.
    """
    with pytest.raises(ValidationError):
        SegmentContribution(
            dimension="product",
            segment_label=CAUSAL_LABEL,  # type: ignore[arg-type]  # a raw string is refused
            value=Decimal("3"),
            contribution=Decimal("0.9"),
            claim_type=ClaimType.CORRELATION,
        )


def test_the_text_is_preserved_exactly_including_whitespace_and_case() -> None:
    """Not trimmed, not normalised, not title-cased.

    Every one of those is an edit, and an edited value is no longer the source's.
    """
    awkward = "  MUDANÇA de preço  "
    value = SourceValue(text=awkward, origin="product")
    assert value.text == awkward


def test_this_feature_makes_no_claim_about_the_sources_content() -> None:
    """**The limit `SC-003a` states, asserted rather than left implicit.**

    The label below asserts a cause, and this feature accepts it. That is correct
    and it is the boundary: we govern **our** vocabulary, and a structural check
    over what we write cannot and does not prove the source is free of causal
    language.

    Writing this down is the point. A reader who found only the closed-vocabulary
    checks might conclude the output contains no causal claim at all — and that
    conclusion would be false.
    """
    segment = _segment(SourceValue(text=CAUSAL_LABEL, origin="product"))
    assert "causada" in segment.segment_label.text
    # And our own field beside it stays inside the closed set.
    assert segment.claim_type in set(ClaimType)


def test_the_bound_on_length_is_the_only_thing_imposed_on_source_text() -> None:
    """A structural ceiling, not a content rule.

    It exists because an unbounded field is a denial-of-service surface, not
    because we are judging what the source may say.
    """
    with pytest.raises(ValidationError):
        SourceValue(text="x" * 1001, origin="product")
    assert SourceValue(text="x" * 1000, origin="product").text
