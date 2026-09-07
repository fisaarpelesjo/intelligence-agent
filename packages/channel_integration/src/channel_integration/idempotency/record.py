"""The idempotency record — T082 (ADR 0021; FR-066; SC-030).

``(channel, message_id) -> (tenant, principal_ref, outcome_class, first_seen_at, expires_at)``.

**What it carries is the whole design.** A pseudonymous principal reference, a provider message key,
an outcome class and two instants. That is enough to recognise a redelivery and report what happened
the first time.

**What it cannot carry** is the point: there is **no field** for question text, answer content, a
value, a filter value, provenance, a caveat or personal data. Not an optional one, not a debug one.
`T099` scans the serialised record for all of it, and the scan can only pass because the fields do
not exist — a record with a spare string field would eventually hold a question.

``outcome_class`` is the **class** of what happened, not the response. Knowing that the first
delivery was withheld is operationally necessary; carrying the withheld answer would defeat the
reason it was withheld.

The two instants are **passed in**, never read from a clock (`R-5`). A window boundary is then
testable at exactly the second it flips, and two processes cannot disagree about whether a record
expired.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ..contracts._base import ChannelModel, MessageKey, PrincipalRef, TenantId
from ..contracts.delivery import DeliveryOutcome
from ..contracts.descriptor import ChannelId

__all__ = ["ChannelIdempotencyRecord", "IdempotencyKey", "key_for"]


class IdempotencyKey(ChannelModel):
    """The key a redelivery is recognised by: the channel and the provider's message id.

    The provider's id rather than a hash of the payload, because the same question asked twice on
    purpose is two messages, and a payload hash would suppress the second one.
    """

    channel: ChannelId
    message_id: MessageKey


def key_for(channel: ChannelId, message_id: MessageKey) -> IdempotencyKey:
    """The key for one inbound message."""
    return IdempotencyKey(channel=channel, message_id=message_id)


class ChannelIdempotencyRecord(ChannelModel):
    """What one seen message left behind. In memory, process-local, window-bounded."""

    key: IdempotencyKey
    tenant: TenantId
    #: Pseudonymous. Never a phone number, member id, chat id, handle, display name or email.
    principal_ref: PrincipalRef
    #: The **class** of what happened, never the response itself.
    outcome_class: DeliveryOutcome
    #: Both instants are supplied by the caller. No clock is read here (`R-5`).
    first_seen_at: datetime
    expires_at: datetime
    #: Which `D-26` version fixed the window this record lives inside, so an expiry is attributable.
    policy_version: str = Field(min_length=1)

    # Deliberately absent, and the absence is the mechanism (`FR-066`): no `question`, `text`,
    # `answer`, `body`, `value`, `filter_value`, `provenance`, `caveat`, `payload`, `email`,
    # `phone`, `handle` or `display_name`. `extra="forbid"` means a caller cannot add one either.

    def has_expired(self, at: datetime) -> bool:
        """Is this record outside its governed window at ``at``?

        Takes the instant rather than reading one, for the same reason the fields do.
        """
        return at >= self.expires_at
