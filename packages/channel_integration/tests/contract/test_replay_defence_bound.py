"""Only a channel that can evaluate a replay window may be enabled — owner decision, 2026-08-18.

Revision note § 13 measured that the four provider schemes do not guarantee the same things. Slack
and the generic webhook sign a timestamp and bind the body, so a replay outside the governed
tolerance is refused at conversion. WhatsApp signs no timestamp; Telegram signs none and binds no
body. On those two, a captured request can be presented again and **conversion cannot tell** — the
remaining defence is duplicate suppression, which is process-local and claims nothing across
processes.

The owner decided, from the three options § 13 recorded: the declaration of `D-22` to `D-25` may
enable **only** the channels whose scheme evaluates an instant. WhatsApp and Telegram stay blocked
until a governed shared store for cross-process duplicate suppression exists.

This is that decision as a gate rather than as prose, which is what the owner required. A decision
recorded only in a document is a decision the next declaration can contradict without anything
failing.

## Where the permitted set comes from

Derived from each scheme's own `provides_signed_timestamp`, never from a list written here. Today
that derivation yields exactly Slack and the generic webhook, which is the owner's decision — and if
a scheme ever changed, the gate would follow the schemes rather than repeat a stale list.

One assertion below pins the derived set to the decision anyway. That is not redundancy: a scheme
gaining a signed timestamp would silently widen what may be enabled, and widening the permitted set
is exactly the change that needs an owner's word rather than a code change.

## What this gate does **not** do

It declares nothing, and it invents no shared-store record. There is no `D-33`; the gate names what
would have to exist and fails until it does, which is the honest way to hold a condition open.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from channel_integration.compliance.readiness import (
    capability_state,
    channel_enabled,
    may_receive_from,
)
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.inbound.verify import scheme_for

from ..fixtures.channels import descriptor_for

pytestmark = pytest.mark.contract

#: Which readiness record gates which channel. Read from the record names in the YAML rather than
#: guessed: `d_22` WhatsApp, `d_23` Slack, `d_24` Telegram, `d_25` the generic channel.
_RECORD_FOR_CHANNEL = {
    ChannelId.WHATSAPP: "d_22",
    ChannelId.SLACK: "d_23",
    ChannelId.TELEGRAM: "d_24",
    ChannelId.GENERIC_WEBHOOK: "d_25",
}

#: The owner's decision, 2026-08-18. Stated as data so the assertion below can compare it against
#: what the schemes derive, and so a change to it is a visible edit rather than a silent drift.
_DECISION_PERMITS = frozenset({ChannelId.SLACK, ChannelId.GENERIC_WEBHOOK})

#: What would have to exist before WhatsApp or Telegram may be enabled. Named, not created: this
#: repository authors no readiness record, and a record invented here would be the fabricated
#: evidence `FR-097` forbids.
_SHARED_STORE_REQUIREMENT = (
    "a governed external record for cross-process duplicate suppression, declared with real "
    "evidence "
    "by the owner. No such record exists today and none is created by this gate."
)


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


_READINESS = _repository_root() / "docs" / "readiness" / "multichannel-external-readiness.yaml"
_REVISION_NOTE = _repository_root() / "docs" / "release" / "multichannel-spec-revision-notes.md"


def _records() -> dict[str, dict[str, Any]]:
    document = cast("dict[str, Any]", yaml.safe_load(_READINESS.read_text(encoding="utf-8")))
    entries = cast("list[dict[str, Any]]", document["capabilities"])
    return {str(entry["id"]): entry for entry in entries}


def _permitted_by_scheme() -> frozenset[ChannelId]:
    """The channels whose scheme evaluates an instant, derived from the schemes themselves."""
    return frozenset(
        channel
        for channel in ChannelId
        if scheme_for(descriptor_for(channel)).provides_signed_timestamp
    )


def _shared_store_declared() -> bool:
    """Is any readiness record a declared cross-process duplicate-suppression store?

    Matched on the record's own text rather than on an id, because the id does not exist yet and
    hard-coding a future id would make this gate pass the moment somebody used that name for
    something else.
    """
    return any(
        _names_a_store(entry) and entry.get("declared") is True for entry in _records().values()
    )


def _names_a_store(entry: dict[str, Any]) -> bool:
    """Does this record read as a cross-process duplicate-suppression store?

    Read from the record's own text, and defined ONCE so the two nodes that ask it cannot
    drift apart -- the declared-store check and the not-invented check are the same question
    asked about different sets, not two questions.
    """
    text = " ".join(str(value) for value in entry.values()).lower()
    return "duplicate" in text and ("shared" in text or "cross-process" in text)


def test_the_readiness_file_declares_the_four_channel_records() -> None:
    """Without this, every assertion below could pass over a renamed or absent record."""
    records = _records()
    for channel, identifier in sorted(_RECORD_FOR_CHANNEL.items(), key=lambda pair: pair[1]):
        assert identifier in records, f"{identifier} gates {channel.value} and is missing"
        name = str(records[identifier]["name"]).lower()
        expected = {
            ChannelId.WHATSAPP: "whatsapp",
            ChannelId.SLACK: "slack",
            ChannelId.TELEGRAM: "telegram",
            ChannelId.GENERIC_WEBHOOK: "generic",
        }[channel]
        assert expected in name, f"{identifier} no longer names the {channel.value} channel"


def test_the_schemes_derive_exactly_the_channels_the_owner_permitted() -> None:
    """The derivation and the decision agree today, and a divergence needs a decision.

    If a scheme gained a signed timestamp, the derived set would widen and this fails — which is the
    point. Widening what may be enabled is the owner's call, and a passing test would let a library
    change make it silently.
    """
    derived = _permitted_by_scheme()
    assert derived == _DECISION_PERMITS, (
        f"the schemes now permit {sorted(channel.value for channel in derived)} while the owner's "
        f"decision permits {sorted(channel.value for channel in _DECISION_PERMITS)}. Re-derive the "
        "decision rather than editing this expectation"
    )


_BLOCKED_IN_ORDER: list[ChannelId] = [
    channel for channel in ChannelId if channel not in _DECISION_PERMITS
]


@pytest.mark.parametrize("channel", _BLOCKED_IN_ORDER, ids=str)
def test_a_channel_without_replay_defence_stays_blocked_until_a_shared_store_exists(
    channel: ChannelId,
) -> None:
    """The gate itself. Vacuous today, and it fires exactly when the omission would ship.

    `WhatsApp` and `Telegram` may be declared only alongside a governed shared store. Until that
    record exists and is declared, a declaration of their channel record is the state this fails on
    — before a message is ever accepted on a channel whose replays nobody can detect.
    """
    #: **This node measures the INBOUND key**, and that changed on 2026-08-28.
    #:
    #: It used to read `channel_enabled`, which was the whole switch — and the owner's `OD-20-A`
    #: split it, because *may a message arrive* and *may a message be sent* are two questions and
    #: only the first is about replay. A node left reading the credential half would have gone
    #: green because the property it measured stopped existing, which is `G-1`.
    #:
    #: **The decision of 2026-08-18 is unchanged and unweakened**: a channel whose scheme signs no
    #: instant may not RECEIVE until a governed shared store exists.
    assert may_receive_from(channel) is False, (
        f"{channel.value} may RECEIVE, and its scheme evaluates no replay window: "
        f"{scheme_for(descriptor_for(channel)).name} signs no timestamp, so a captured request "
        f"can be presented again and conversion cannot tell. The owner's decision of 2026-08-18 "
        f"permits this only alongside {_SHARED_STORE_REQUIREMENT} See § 13 of "
        "docs/release/multichannel-spec-revision-notes.md."
    )

    #: And the credential half is measured SEPARATELY, so the two cannot be confused again. A
    #: declared record must not open the inbound door on its own.
    record = _records()[_RECORD_FOR_CHANNEL[channel]]
    if record.get("declared") is True:
        assert _shared_store_declared() or not may_receive_from(channel), (
            f"{channel.value}'s record is declared and it may receive; the credential opened the "
            f"inbound door without the store the 2026-08-18 decision requires"
        )


#: Materialised outside the decorator with an explicit type. `parametrize` widens its argument to
#: `Sequence[object]`, so a `lambda` reading `.value` inside the call loses the element type and
#: `pyright` strict reports five errors on one line.
_PERMITTED_IN_ORDER: list[ChannelId] = sorted(_DECISION_PERMITS, key=str)


@pytest.mark.parametrize("channel", _PERMITTED_IN_ORDER, ids=str)
def test_a_channel_with_replay_defence_is_not_blocked_by_this_gate(channel: ChannelId) -> None:
    """The other direction, so this gate blocks two channels rather than all four.

    Slack and the generic webhook need no shared store for **this** reason: their schemes sign an
    instant, so a stale replay is refused at conversion. They remain gated by their own records,
    which is a different condition and not this one's business.
    """
    assert scheme_for(descriptor_for(channel)).provides_signed_timestamp is True
    #: Still disabled today, because their own records are undeclared. Asserted so nobody reads this
    #: test as "these two are enabled".
    assert channel_enabled(channel) is False
    assert may_receive_from(channel) is False
    assert capability_state(_RECORD_FOR_CHANNEL[channel]).value == "UNDECLARED"


def test_the_decision_is_recorded_where_a_reader_will_find_it() -> None:
    """The gate and the record must not drift apart.

    A failure message that cites § 13 is worth nothing if § 13 stops carrying the decision.
    """
    note = _REVISION_NOTE.read_text(encoding="utf-8")
    assert "## 13." in note
    for required in ("WhatsApp", "Telegram", "replay"):
        assert required in note, f"§ 13 no longer mentions {required}"


def test_no_shared_store_record_is_invented_by_this_repository() -> None:
    """The inverse obligation: recording the condition must not become authoring the record.

    ## The count was a proxy, and it was replaced on 2026-08-28

    It asserted **eleven** records. That number stood in for the property, and the property
    is *no shared-store record was invented here* -- so a twelfth record about something
    else entirely failed this node while inventing nothing, which is what happened the day
    `OD-17` ordered the production bar split out of `d_24` into a record of its own.

    **A count standing in for a property is the `F136` shape**: it is correct until the day
    somebody legitimately changes what it counts, and then it accuses the wrong thing. What
    replaced it names the property directly, and it is STRONGER rather than looser -- the
    count could not tell a shared-store record from any other, and this can.

    `d_33` STAYS RESERVED. It is the name this gate uses for the store that must exist, and
    the record `OD-17` added took `d_34` for exactly that reason.
    """
    records = _records()
    assert "d_33" not in records, (
        "d_33 exists in the readiness file; this gate reserves that name for the "
        "cross-process duplicate-suppression store, which this repository may not author"
    )
    invented = sorted(
        identifier
        for identifier, entry in records.items()
        if _names_a_store(entry) and identifier not in _RECORD_FOR_CHANNEL.values()
    )
    assert not invented, (
        f"{invented} read as a cross-process duplicate-suppression record; this repository "
        f"names what would have to exist and authors none of it"
    )
    assert _shared_store_declared() is False


# --------------------------------------------------------------------------- #
# THE KEY WAS SPLIT ON 2026-08-28, AND THIS GATE HAD TO BE SEEN TO BITE AGAIN.
#
# `OD-20-A`: "pode receber" and "pode enviar" became two questions. His decision of
# 2026-08-18 stands IN FULL for what arrives; what opened is sending, inside `OD-7`'s reach.
#
# The two nodes below are the acceptance criterion he named: **the gate must go RED when the
# INBOUND key is declared for Telegram, and must NOT fire because sending was permitted.**
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("channel", _BLOCKED_IN_ORDER, ids=str)
def test_permitting_send_does_not_open_the_inbound_door(
    channel: ChannelId, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The half `OD-20-A` opened must not reach the half it left closed.**

    A replayed INBOUND request is not a risk outbound delivery carries: nothing arrives, so
    nothing can be presented twice. If sending were to open receiving, the split would be a
    rename of the old switch rather than a division of it.
    """
    from channel_integration.compliance import readiness

    def _granted(_channel: ChannelId) -> bool:
        return True

    monkeypatch.setattr(readiness, "channel_enabled", _granted)
    assert readiness.may_send_to(channel) is True, "the send half did not follow the credential"
    assert readiness.may_receive_from(channel) is False, (
        f"granting the credential opened RECEIVING for {channel.value}, whose scheme signs no "
        f"timestamp; the split would then be a rename and not a division"
    )


@pytest.mark.parametrize("channel", _PERMITTED_IN_ORDER, ids=str)
def test_the_inbound_door_opens_for_a_scheme_that_signs_an_instant(
    channel: ChannelId, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Proof the inbound key is not simply False for everything.**

    A key that answered no to every channel would satisfy every assertion above while
    measuring nothing — the `F115` shape. Slack and the generic webhook sign an instant, so
    with the credential granted they may receive, and the ONLY thing still stopping them
    today is their own undeclared record.
    """
    from channel_integration.compliance import readiness

    def _granted(_channel: ChannelId) -> bool:
        return True

    monkeypatch.setattr(readiness, "channel_enabled", _granted)
    assert readiness.may_receive_from(channel) is True, (
        f"{channel.value} signs an instant and still may not receive with its credential "
        f"granted; the inbound key refuses everything and measures nothing"
    )


def test_the_inbound_condition_is_derived_from_the_scheme_and_not_from_a_list() -> None:
    """The permitted set stays derived — his words, and the reason is the same as always.

    A list written into the readiness module would age the day a scheme changed, and it would
    age **silently**, because nothing else in the repository would disagree with it.
    """
    from channel_integration.compliance import readiness

    source = Path(readiness.__file__).read_text(encoding="utf-8")
    for channel in ChannelId:
        assert f'"{channel.value}"' not in source and f"'{channel.value}'" not in source, (
            f"{channel.value} is written into the readiness module; the inbound condition must "
            f"be derived from provides_signed_timestamp, never from a list"
        )
