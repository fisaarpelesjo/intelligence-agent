"""Resolved transport bounds as a value object — Phase B (FR-053; SC-027).

`T018` reads the `D-26` document and refuses when it declares no instance. This module
turns a resolved instance into the frozen value object the inbound and outbound paths take
as a **parameter**, which is what keeps `convert` pure: the bounds arrive as data, not as a
lookup performed mid-conversion.

**Nothing here has a default.** Every field is required, and the only way to obtain an
instance is from an approved `D-26` entry or from a test fixture. While `D-26` is
undeclared, :func:`resolve_bounds` refuses with
``CHANNEL_TRANSPORT_POLICY_UNRESOLVABLE`` — which is the shipped state, and the reason no
message reaches step 4 in production today.

A separate module rather than an addition to `T018`'s loader, so the completed task's file
stays as it was reviewed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import Field

from ..contracts._base import ChannelModel
from ..contracts.descriptor import ChannelId
from .resolve import effective_instance, read_instances
from .transport_policy import (
    CODE,
    TRANSPORT_POLICY_FILE,
    TRANSPORT_POLICY_KIND,
    TRANSPORT_POLICY_REQUIRED_FIELDS,
    resolve_transport_policy,
)

__all__ = ["TransportBounds", "resolve_bounds"]


class TransportBounds(ChannelModel):
    """The seven governed values, resolved, for one channel.

    Frozen and closed: a caller cannot widen a bound at the point of use, and a bound
    cannot be absent — a partially resolved policy is not usable and does not resolve at
    all (`contracts/delivery-and-idempotency.md` §2).
    """

    channel: ChannelId
    #: How far a signed timestamp may be from the evaluation instant.
    replay_tolerance_seconds: int = Field(ge=0)
    #: The governed inbound size bound. Distinct from the **structural** ceiling in
    #: `inbound.parse`, which is a contract limit and names no governed number.
    maximum_inbound_bytes: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    retry_attempts: int = Field(ge=0)
    retry_backoff_seconds: int = Field(ge=0)
    rate_limit_per_minute: int = Field(gt=0)
    idempotency_window_seconds: int = Field(gt=0)
    continuation_mechanism: str = Field(min_length=1)
    #: The `D-26` instance version these bounds came from, so a refusal or an audit event
    #: is attributable to a governance state rather than to "the policy, at some point".
    policy_version: str = Field(min_length=1)


def resolve_bounds(channel: ChannelId) -> TransportBounds:
    """The effective bounds for ``channel``, or refuse.

    Raises :class:`~channel_integration.governance.resolve.ContentUnresolvable` carrying
    ``CHANNEL_TRANSPORT_POLICY_UNRESOLVABLE`` while `D-26` declares no instance. No value is
    inferred, defaulted or carried forward.
    """
    entry = resolve_transport_policy(channel)
    retry = cast("Mapping[str, Any]", entry["retry_bounds"])
    rate = cast("Mapping[str, Any]", entry["rate_limit"])
    # The instance version lives on the instance, not on the per-channel entry, so it is
    # read through the same public loader rather than by widening `T018`'s return type.
    instance = effective_instance(
        read_instances(TRANSPORT_POLICY_FILE, TRANSPORT_POLICY_KIND, CODE),
        TRANSPORT_POLICY_REQUIRED_FIELDS,
        CODE,
        TRANSPORT_POLICY_FILE,
    )
    return TransportBounds(
        channel=channel,
        replay_tolerance_seconds=int(entry["replay_tolerance_seconds"]),
        maximum_inbound_bytes=int(entry["maximum_inbound_bytes"]),
        timeout_seconds=int(entry["timeout_seconds"]),
        retry_attempts=int(retry["attempts"]),
        retry_backoff_seconds=int(retry["backoff_seconds"]),
        rate_limit_per_minute=int(rate["per_minute"]),
        idempotency_window_seconds=int(entry["idempotency_window_seconds"]),
        continuation_mechanism=str(entry["continuation_mechanism"]),
        policy_version=str(instance["version"]),
    )
