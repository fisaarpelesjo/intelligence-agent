"""The raw inbound request — T006 (FR-004, FR-016, FR-107; SC-007, SC-061).

What the transport received, unaltered. Constructed by the platform's listener
(`D-30`, ADR 0020) and handed to the conversion operation Phase B implements.

**``body`` is bytes, never a parsed object.** A signature is computed over bytes,
and verifying a re-serialised parse verifies something the sender did not sign.
Carrying the parsed form here would make that mistake available.

**``received_at`` is supplied, never read from a clock.** The replay tolerance is
evaluated against an instant passed in, which is what makes conversion pure,
reproducible across processes, and testable without freezing time (`R-5`).

**Deliberately absent, and the absence is the mechanism** (`FR-107`):

* ``verified``, ``authenticated``, ``trusted`` — a transport cannot assert
  authenticity. There is no field to set.
* ``principal``, ``tenant``, ``access_tags``, ``scope``, ``role`` — identity is
  resolved from a governed binding, never asserted.
* ``language``, ``detected_language`` — declared in the payload, never detected and
  never taken from a channel locale.
* ``parsed``, ``json``, ``event`` — verification is over bytes; a parsed form would
  let the verified and the processed value diverge.
* ``mode``, ``fixture``, ``debug`` — no runtime path selects a fixture.

Transient by construction: never persisted, never logged, never audited, never a
cache key (`FR-078`).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from ._base import ChannelModel, ChannelViolation
from .descriptor import ChannelId
from .reason_codes import ChannelReasonCode

__all__ = ["RawChannelRequest"]


class RawChannelRequest(ChannelModel):
    """One inbound payload as the provider delivered it."""

    channel: ChannelId
    #: The exact bytes received. Verification runs over these and nothing else.
    body: bytes
    #: Header **names** are consumed by verification; header **values** reach no
    #: log, trace, audit event or refusal (`FR-070`). Stored as an immutable tuple
    #: of pairs rather than a dict so the model stays hashable and frozen in
    #: substance as well as in configuration.
    headers: tuple[tuple[str, str], ...] = ()
    #: Supplied by the caller. Never a clock read (`FR-006`, `R-5`).
    received_at: datetime = Field()

    @field_validator("headers")
    @classmethod
    def _reject_duplicate_header_names(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        """A repeated header name is refused rather than resolved.

        Providers differ on whether the first or the last occurrence wins, and a
        signature header appearing twice is a request whose authenticity depends on
        which one a parser happened to pick. Refusing removes the ambiguity
        instead of choosing a side.
        """
        seen = {name.lower() for name, _ in value}
        if len(seen) != len(value):
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
                "a header name appears more than once",
            )
        return value
