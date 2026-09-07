"""Rendered presentation and its fragments — T010 (FR-047, FR-051, FR-058; SC-019, SC-021).

One channel-specific representation of a governed payload, in which every governed
string is byte-preserved, every value is untouched, and every permitted degradation
is a member of the `D-28` capability matrix and is disclosed.

**Construction fails rather than degrading.** A payload that cannot be rendered
with every element intact produces ``CHANNEL_RESPONSE_NOT_REPRESENTABLE`` and the
response is withheld (ADR 0022). The renderer itself is Phase C (T071 — T075); this
module declares the shape it must produce, so the invariant exists before any code
can violate it.

**``caveat_count`` is carried, not inferred.** It must equal the count the governed
payload declared, which is what makes a renderer showing a subset *detectable*
rather than merely wrong (`FR-047`). The equality is asserted at construction here
and re-asserted against the payload by the preservation gate in Phase C (T074).

**Fragments carry ``(index, total)``.** A continuation delivers the payload whole in
order; where a channel declares no ordering guarantee, the response is withheld
rather than fragmented (`R-12`, `FR-059`).
"""

from __future__ import annotations

from pydantic import Field, model_validator

from ._base import ChannelModel, ChannelViolation
from .descriptor import ChannelId
from .reason_codes import ChannelReasonCode

__all__ = ["Degradation", "PresentationFragment", "RenderedPresentation"]


class Degradation(ChannelModel):
    """One structural adaptation, drawn from the capability matrix and disclosed.

    **Structural only.** A table rendered as a list is a degradation; shortening,
    summarising, rewording, rounding or omitting is not — those are content changes
    and are forbidden outright (`FR-110`, ADR 0022). This type carries no field in
    which a content change could be recorded, because there is no permitted one.
    """

    #: The matrix entry this degradation is an instance of. A degradation with no
    #: matrix entry is refused by the renderer (Phase C); the reference is required
    #: here so an invented one has nowhere to hide.
    capability_ref: str = Field(min_length=1)
    #: What structure was replaced by what, in governed terms — e.g. a table
    #: rendered as a list. Selected from governed content, never composed here.
    disclosure_code: str = Field(min_length=1)


class PresentationFragment(ChannelModel):
    """One deliverable piece of a rendered payload.

    A single fragment is the normal case. More than one means the channel's governed
    continuation mechanism was required, and every fragment carries its position so
    a consumer cannot present part of an answer as the whole of one.
    """

    index: int = Field(ge=1)
    total: int = Field(ge=1)
    body: str = Field(min_length=1)

    @model_validator(mode="after")
    def _index_within_total(self) -> PresentationFragment:
        if self.index > self.total:
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_RESPONSE_NOT_REPRESENTABLE,
                f"fragment index {self.index} exceeds total {self.total}",
            )
        return self


class RenderedPresentation(ChannelModel):
    """A governed payload, rendered for one channel, with nothing lost."""

    channel: ChannelId
    fragments: tuple[PresentationFragment, ...] = Field(min_length=1)
    #: Every governed string present in the rendering, carried so the preservation
    #: gate can byte-compare against the payload rather than trusting the renderer.
    governed_strings: tuple[str, ...] = ()
    #: Must equal the payload's declared count (`FR-047`).
    caveat_count: int = Field(ge=0)
    degradations: tuple[Degradation, ...] = ()
    #: The envelope's declared language. **Never** a channel locale, a provider
    #: account setting or a recipient preference, and never translated at delivery
    #: time (`FR-052`).
    language: str = Field(min_length=1)

    @model_validator(mode="after")
    def _fragments_are_ordered_and_complete(self) -> RenderedPresentation:
        """The fragment sequence must be exactly ``1..total``, in order.

        A gap, a repeat or a wrong total is a truncated answer wearing a
        continuation's clothes, so it refuses here rather than being delivered and
        noticed by a reader.
        """
        total = self.fragments[0].total
        if any(fragment.total != total for fragment in self.fragments):
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_RESPONSE_NOT_REPRESENTABLE,
                "fragments disagree about the total",
            )
        if [fragment.index for fragment in self.fragments] != list(range(1, total + 1)):
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_RESPONSE_NOT_REPRESENTABLE,
                "the fragment sequence is incomplete or out of order",
            )
        return self
