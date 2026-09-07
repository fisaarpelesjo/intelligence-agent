"""Channel identity and descriptor — T005 (FR-005, FR-097; SC-053).

``ChannelId`` is closed at four members. A fifth channel is added by declaring a
descriptor, a verification scheme, normalisation rules, a `D-28` capability entry,
a delivery adapter and a credential record — and **zero** changes to any upstream
contract or to the canonical channel contracts (`FR-088`, asserted by T129).

**``enabled`` is derived, never configured.** It reads from the readiness record,
so no configuration file, environment variable or deployment flag can enable a
channel whose credential record is undeclared (`FR-097`). A settable flag would
make the whole fail-closed posture a matter of deployment discipline; a derived one
cannot be set at all.

The descriptor names **which** governed policy applies, never the policy's values.
A transport bound, a capability or a degradation lives in `D-26` / `D-28`, and this
contract carries only the reference — so a descriptor cannot smuggle in a limit
nobody approved.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from ._base import ChannelModel

__all__ = ["ChannelDescriptor", "ChannelId", "CredentialRecord"]


class ChannelId(StrEnum):
    """The four channels this feature governs. Closed.

    WhatsApp, Slack and Telegram are absent from `docs/intelligence-agent.yaml`'s
    channel list in one direction or another; the divergence is recorded as
    `research.md` `BD-1` rather than reconciled by a silent edit.
    """

    WHATSAPP = "WHATSAPP"
    SLACK = "SLACK"
    TELEGRAM = "TELEGRAM"
    GENERIC_WEBHOOK = "GENERIC_WEBHOOK"


class CredentialRecord(StrEnum):
    """Which external dependency record gates a channel.

    Named as an enum rather than a free string so a descriptor cannot point at a
    record that does not exist, and so the readiness guard and the descriptor
    cannot drift apart about which lock applies to which channel.
    """

    D_22_WHATSAPP = "d_22"
    D_23_SLACK = "d_23"
    D_24_TELEGRAM = "d_24"
    D_25_GENERIC = "d_25"


class ChannelDescriptor(ChannelModel):
    """What a channel *is*, for governance purposes.

    Carries references, not values: which verification scheme, which `D-26`
    transport policy version, which `D-28` capability version, which credential
    record — and whether the channel is enabled, which is **supplied by the
    readiness guard** rather than authored here.
    """

    channel: ChannelId
    #: Names the ``VerificationScheme`` implementation. **Never inferred from a
    #: payload** — a payload naming its own scheme is authentication by suggestion
    #: (`contracts/inbound-conversion.md` §4). Phase B implements the schemes.
    verification_scheme: str = Field(min_length=1)
    #: The `D-26` instance version in force, or ``None`` while `D-26` is
    #: undeclared. ``None`` means every dependent operation refuses; it is not a
    #: default standing in for a missing policy.
    transport_policy_ref: str | None = None
    #: The `D-28` instance version in force, or ``None`` while it is undeclared.
    capability_ref: str | None = None
    credential_record: CredentialRecord
    #: Derived from the readiness record by `compliance.readiness`, never authored.
    #: Undeclared evidence ⇒ ``False``.
    enabled: bool = False
