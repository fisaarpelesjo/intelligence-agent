"""ADR 0035's three conditions, and each one alone is what stops a message — T702 to T705.

`FR-062` says the system originates nothing on its own initiative. The ADR supersedes
it for **one** case: a prioritisable finding, an already-enabled channel, and an
accepted recipient. **An exception that said "the system may originate messages" would
have cost the property `FR-062` buys**, so the narrowness is the load-bearing part and
this file is where it stops being a sentence.

## `SC-705`, driven three times

Each condition is removed in turn — by satisfying the other two — and the refusal must
name **that** condition. A caller who sees one code must know which of the three
stopped it, because each is fixed by a different person doing a different thing.

## The channel is NOT a parameter any more, and these nodes changed with it

`T703` removed it: a parameter is the caller telling the function what it wants to hear.
The condition reads `004`'s readiness records now, so these nodes **substitute the reader
inside this module's namespace** rather than passing a flag -- which is honest about what
it is doing, and impossible for a production caller to do, because there is no parameter
to pass.

**Which channels may send is whatever `004`'s records say at the instant these nodes run**, and
this module states no count of them. `test_exactly_one_channel_may_send_and_none_may_receive`,
below, reads that answer and asserts against the reading — so the world may move without a
sentence here going stale.

What substitution is for is the other direction: it reaches **both** cases, the enabled and the
refused, without either depending on how the records happen to read today. **This feature enables
no channel**, and a node that wrote a readiness record to make its own assertion pass would be
doing the exact thing the whole ADR forbids -- which is why the reader is replaced in this
module's namespace and no record is ever touched.

**This paragraph used to say the real record said NOT enabled, so the enabled case could only be
reached by substitution.** `OD-18` and `OD-20-A` ended that on 2026-08-28: `may_send_to` returns
True for `TELEGRAM` now, the node below already asserted it, and this file contradicted itself for
two days because no node reads a docstring.
"""

from __future__ import annotations

import pytest
from channel_integration.compliance.readiness import ReadinessMalformed
from channel_integration.contracts.descriptor import ChannelId

from proactive_distribution.contracts import DistributionReasonCode
from proactive_distribution.distribute import RECIPIENT_KEY, conditions, may_distribute
from proactive_distribution.distribute.conditions import DISTRIBUTED_CHANNEL

pytestmark = pytest.mark.unit

#: An environment that DOES yield a recipient. The value is a placeholder for the shape
#: of the key's presence and is never asserted about — `FR-202`.
PRESENT = {RECIPIENT_KEY: "an-id-this-node-never-reads"}


def _with_channel(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    """Substitute the record reader inside this module's namespace.

    **Not a parameter and not a fixture record.** The production path takes no argument for
    this, so a caller cannot do what this helper does; and writing a readiness record to make
    a test pass would be enabling a channel, which no test may do.
    """

    def _substituted(_channel: ChannelId = DISTRIBUTED_CHANNEL) -> bool:
        return enabled

    monkeypatch.setattr(conditions, "channel_is_enabled", _substituted)


def test_the_real_record_says_the_channel_may_send_now() -> None:
    """**This node went red on 2026-08-28, twice, and both times that was its function.**

    It asserted no channel was enabled and it was right to. Then `d_24` was declared under
    `OD-18` and it went red -- correctly -- and the declaration was **withdrawn** the same
    cycle, because an earlier decision of his kept Telegram blocked for replay reasons.

    `OD-20-A` resolved that by **splitting the key**: *may a message arrive* and *may a
    message be sent* are two questions now. The 2026-08-18 rule stands in full for what
    arrives; sending opened inside `OD-7`'s reach.

    **RE-DERIVED and not deleted**, `FR-818`: it holds the new world and goes red the day
    the record is un-declared.
    """
    assert conditions.channel_is_enabled(), (
        "the record reports the channel as NOT permitted to send; d_24 was declared and "
        "signed, so either it was reverted or the derivation stopped reading it"
    )


def test_exactly_one_channel_may_send_and_none_may_receive() -> None:
    """**The reach, counted rather than asserted one channel at a time.**

    `OD-7` covers his own chat and nothing else, and a shared derivation is exactly where
    one declaration could unlock everything sharing the path. And the inbound half must
    stay shut for all four: `OD-20-A` split the key, it did not weaken the 2026-08-18 rule.
    """
    from channel_integration.compliance.readiness import may_receive_from, may_send_to
    from channel_integration.contracts.descriptor import ChannelId

    sending = sorted(channel.value for channel in ChannelId if may_send_to(channel))
    receiving = sorted(channel.value for channel in ChannelId if may_receive_from(channel))
    assert sending == [ChannelId.TELEGRAM.value], (
        f"{sending} may send; exactly one channel was authorized and enabling it must not "
        f"have unlocked another"
    )
    assert receiving == [], (
        f"{receiving} may RECEIVE; his decision of 2026-08-18 forbids that until a governed "
        f"cross-process store exists"
    )


def test_all_three_together_permit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The premise. A function that refused everything would satisfy the three below."""
    _with_channel(monkeypatch, enabled=True)
    permission = may_distribute(finding_is_prioritisable=True, environment=PRESENT)
    assert permission.permitted
    assert permission.refused_for is None
    assert permission.recipients, "permitida sem ninguem (OD-105: plural declarado)"


def test_an_unplaced_finding_stops_it_and_says_so() -> None:
    """The first condition, and the first refusal on purpose.

    A finding that was not placed answers *should anything be said at all*. Asking about
    channels or recipients first would report a configuration problem when the truth is
    there was nothing to report.
    """
    permission = may_distribute(finding_is_prioritisable=False, environment=PRESENT)
    assert not permission.permitted
    assert permission.refused_for is DistributionReasonCode.DISTRIBUTION_FINDING_NOT_PRIORITISABLE


def test_a_disabled_channel_stops_it_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """The second condition, and **it needs a substitution now that it did not need before.**

    It used to read the real record and get *not enabled* for free. Since `OD-20-A` the
    record permits sending, so the condition is driven instead of observed -- the weaker of
    the two, and said rather than hidden: a substituted `False` proves the branch exists,
    where the old reading proved the world.

    **What replaces the lost strength is the node above**, which asserts the real record
    directly and goes red if it is reverted.
    """
    _with_channel(monkeypatch, enabled=False)
    permission = may_distribute(finding_is_prioritisable=True, environment=PRESENT)
    assert not permission.permitted
    assert permission.refused_for is DistributionReasonCode.DISTRIBUTION_CHANNEL_NOT_ENABLED


def test_a_record_that_cannot_be_read_refuses_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Not measuring is never passing, and it is never a crash either.**

    `004` raises when a record is missing -- *"a missing record is not permission"* -- and a
    caller that asked a yes-or-no question must get an answer rather than an exception. The
    answer is the refusal.
    """

    def _unreadable(_channel: object) -> bool:
        raise ReadinessMalformed("multichannel-external-readiness.yaml does not exist")

    monkeypatch.setattr(conditions, "may_send_to", _unreadable)
    assert conditions.channel_is_enabled() is False

    permission = may_distribute(finding_is_prioritisable=True, environment=PRESENT)
    assert not permission.permitted
    assert permission.refused_for is DistributionReasonCode.DISTRIBUTION_CHANNEL_NOT_ENABLED


def test_no_derivable_recipient_stops_it_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """The third. The key yields nobody, so there is nobody this may originate a message to."""
    _with_channel(monkeypatch, enabled=True)
    permission = may_distribute(finding_is_prioritisable=True, environment={})
    assert not permission.permitted
    assert permission.refused_for is DistributionReasonCode.DISTRIBUTION_RECIPIENT_NOT_ACCEPTED


def test_the_three_refusals_are_three_different_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    """**One code for three conditions is a message that says nothing beyond *not today*.**"""
    codes: set[DistributionReasonCode | None] = set()

    _with_channel(monkeypatch, enabled=True)
    codes.add(may_distribute(finding_is_prioritisable=False, environment=PRESENT).refused_for)
    codes.add(may_distribute(finding_is_prioritisable=True, environment={}).refused_for)

    _with_channel(monkeypatch, enabled=False)
    codes.add(may_distribute(finding_is_prioritisable=True, environment=PRESENT).refused_for)

    assert len(codes) == 3, f"the three conditions collapse into {len(codes)} code(s): {codes}"


class TestAPermissionCannotContradictItself:
    """The container refuses the two states that would mislead every caller."""

    def test_a_refusal_must_name_a_condition(self) -> None:
        from proactive_distribution.distribute.conditions import Permission

        with pytest.raises(ValueError, match="must name the condition"):
            Permission(permitted=False, refused_for=None, recipients=())

    def test_a_permission_cannot_also_refuse(self) -> None:
        from proactive_distribution.distribute.conditions import Permission

        with pytest.raises(ValueError, match="permitted and refused"):
            Permission(
                permitted=True,
                refused_for=DistributionReasonCode.DISTRIBUTION_CHANNEL_NOT_ENABLED,
                recipients=("x",),
            )

    def test_a_permission_with_nobody_to_send_to_is_refused(self) -> None:
        from proactive_distribution.distribute.conditions import Permission

        with pytest.raises(ValueError, match="nobody to send to"):
            Permission(permitted=True, refused_for=None, recipients=())
