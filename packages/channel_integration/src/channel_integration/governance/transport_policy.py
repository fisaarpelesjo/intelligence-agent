"""Governed channel transport policy — T018 (`D-26`; FR-053, FR-103; SC-027).

Seven values per channel: replay tolerance, maximum inbound payload size, timeout,
retry bounds and backoff, rate limits, idempotency window, continuation mechanism.

**One reason code for all seven**, deliberately: no configuration may run with a rate
limit but no replay tolerance. A policy carrying some of them is not partially usable —
it does not resolve (`contracts/delivery-and-idempotency.md` §2).

**No value is authored here.** `D-26` owns them, it is undeclared, and while it is
undeclared every dependent operation refuses. This module declares the *shape* the
approved instance must have and the loader that reads it. Inventing a timeout or a
window would be inventing a governance decision, and a plausible default is the most
dangerous kind (`FR-053`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ..contracts.descriptor import ChannelId
from ..contracts.reason_codes import ChannelReasonCode
from .resolve import ContentUnresolvable, effective_instance, read_instances

__all__ = [
    "TRANSPORT_POLICY_FILE",
    "TRANSPORT_POLICY_KIND",
    "TRANSPORT_POLICY_REQUIRED_FIELDS",
    "TRANSPORT_POLICY_REQUIRED_PER_CHANNEL",
    "resolve_transport_policy",
]

TRANSPORT_POLICY_FILE = "transport-policy.yaml"
TRANSPORT_POLICY_KIND = "channel_transport_policy"
CODE = ChannelReasonCode.CHANNEL_TRANSPORT_POLICY_UNRESOLVABLE

#: Instance-level fields. ``channels`` carries one entry per governed channel.
TRANSPORT_POLICY_REQUIRED_FIELDS: tuple[str, ...] = (
    "version",
    "effective_from",
    "approval",
    "channels",
)

#: The seven values, per channel. All seven together or the policy does not resolve.
TRANSPORT_POLICY_REQUIRED_PER_CHANNEL: tuple[str, ...] = (
    "replay_tolerance_seconds",
    "maximum_inbound_bytes",
    "timeout_seconds",
    "retry_bounds",
    "rate_limit",
    "idempotency_window_seconds",
    "continuation_mechanism",
)


def resolve_transport_policy(channel: ChannelId) -> Mapping[str, Any]:
    """The effective policy for ``channel``, or refuse.

    Raises :class:`ContentUnresolvable` carrying
    ``CHANNEL_TRANSPORT_POLICY_UNRESOLVABLE`` while `D-26` declares no instance, which
    is the shipped state. A caller's contract is to refuse with that code, never to
    proceed with an assumed bound.
    """
    instances = read_instances(TRANSPORT_POLICY_FILE, TRANSPORT_POLICY_KIND, CODE)
    instance = effective_instance(
        instances, TRANSPORT_POLICY_REQUIRED_FIELDS, CODE, TRANSPORT_POLICY_FILE
    )
    channels: object = instance["channels"]
    if not isinstance(channels, Mapping):
        raise ContentUnresolvable(CODE, "`channels` is not a mapping")
    entry: object = cast(Mapping[str, Any], channels).get(channel.value)
    if not isinstance(entry, Mapping):
        raise ContentUnresolvable(CODE, f"no policy entry for channel {channel.value}")
    missing = [field for field in TRANSPORT_POLICY_REQUIRED_PER_CHANNEL if field not in entry]
    if missing:
        raise ContentUnresolvable(
            CODE, f"{channel.value} policy is missing {', '.join(sorted(missing))}"
        )
    return cast(Mapping[str, Any], entry)
