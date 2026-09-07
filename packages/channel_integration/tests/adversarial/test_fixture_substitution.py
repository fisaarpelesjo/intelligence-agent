"""T143 — no flag, variable or mode substitutes a fixture for a governed element (`FR-072`).

`T070` asserts containment structurally: no `src` module imports or names a fixture. This suite
attacks the same property from the outside, as an operator with an environment and a command line
would. The distinction matters because containment could hold at import time and still be defeated
at run time by a lookup keyed on a variable.

Four substitutions attempted, one per governed element:

* a fixture **channel descriptor**, enabled and configured;
* fixture **credential material** that verifies;
* a fixture **identity binding** that resolves a principal;
* a fixture **pseudonymisation key** that derives references.

Each is attempted by setting every environment variable an implementation might plausibly read, and
by passing every flag the CLI declares. **The property is that after all of it, the governed answer
is UNCHANGED** — whatever the records say with nothing set, they say with all of it set. That is
what the nodes below compare: a clean reading against a substituted one, never against a written
count.

**The sentence here used to name the reading — "every record undeclared, every channel disabled" —
and it stopped being true** when `OD-18` signed `d_24` and `OD-20-A` opened SENDING for one channel.
The nodes never depended on it, which is precisely why nothing caught it: prose that no node reads
ages without a symptom. A snapshot written in this docstring is a second copy of the records that
nobody has to keep true, so there is none — `capabilities`, `may_send_to` and `may_receive_from`
answer that question at the instant they are asked.

## Why the environment is set rather than only scanned

A scan proves no variable is read **today**. Setting the variables and observing that nothing
changes proves it for the code as it runs, including any dependency that might read one on this
feature's behalf.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from channel_integration.cli.main import main
from channel_integration.compliance.readiness import (
    CHANNEL_CAPABILITIES,
    capability_state,
    channel_enabled,
)
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.governance.capabilities import resolve_capability_matrix
from channel_integration.governance.resolve import ContentUnresolvable

pytestmark = pytest.mark.adversarial

#: Every variable name a substitution would plausibly use. Deliberately broad: the point is not that
#: these specific names are read — none is — but that setting all of them changes nothing.
_HOSTILE_ENVIRONMENT = {
    "CHANNEL_INTEGRATION_FIXTURE_MODE": "1",
    "CHANNEL_INTEGRATION_TEST_MODE": "true",
    "CHANNEL_INTEGRATION_DEMO": "on",
    "CHANNEL_FIXTURE_CHANNELS": "SLACK,WHATSAPP",
    "CHANNEL_FIXTURE_SECRET": "fixture-secret-not-a-credential",
    "CHANNEL_FIXTURE_BINDING": "principal-ref-a",
    "CHANNEL_PSEUDONYM_KEY": "fixture-key",
    "CHANNEL_READINESS_OVERRIDE": "READY",
    "CHANNEL_CAPABILITIES_FILE": "/dev/null",
    "CHANNEL_GOVERNED_CONTENT_ROOT": "/tmp",
    #: The **names** are what a substitution would read; the values are deliberately not
    #: credential-shaped. The first version used a `xoxb-` prefixed string and `T031`'s
    #: fabricated-credential gate flagged it — correctly, because a token-shaped string in this
    #: repository is what that gate forbids whatever the intent behind it.
    "SLACK_BOT_TOKEN": "this is not a credential",
    "WHATSAPP_ACCESS_TOKEN": "this is not a credential",
    "TELEGRAM_BOT_TOKEN": "this is not a credential",
    "PYTEST_CURRENT_TEST_CHANNEL": "SLACK",
}


@contextmanager
def _hostile_environment() -> Iterator[None]:
    """Set every variable, then restore exactly what was there.

    Restoration is by saved value rather than by deletion: a variable that already existed must keep
    its value, or this suite would be the thing that broke a later test.
    """
    saved = {name: os.environ.get(name) for name in _HOSTILE_ENVIRONMENT}
    os.environ.update(_HOSTILE_ENVIRONMENT)
    try:
        yield
    finally:
        for name, previous in saved.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def _governed_answer() -> dict[str, object]:
    """The complete governed answer, as the readiness and governance surfaces give it.

    Collected into one comparable structure so the assertion is "nothing changed" rather than a list
    of individually checked facts — a new governed surface is then covered without editing this
    test.
    """
    matrices: dict[str, str] = {}
    for channel in ChannelId:
        try:
            resolve_capability_matrix(channel)
            matrices[channel.value] = "resolved"
        except ContentUnresolvable as refusal:
            matrices[channel.value] = refusal.code.value
    return {
        "records": {name: capability_state(name).value for name in CHANNEL_CAPABILITIES},
        "channels": {channel.value: channel_enabled(channel) for channel in ChannelId},
        "matrices": matrices,
    }


def test_the_governed_answer_is_identical_with_a_hostile_environment_set() -> None:
    """The central assertion: fourteen variables, and not one changes anything."""
    before = _governed_answer()
    with _hostile_environment():
        during = _governed_answer()
    after = _governed_answer()

    assert during == before, (
        f"the environment changed the governed answer: {before} became {during}"
    )
    assert after == before, "the environment was not restored"


def test_no_record_becomes_declared_and_no_channel_becomes_enabled() -> None:
    """The same property stated as the two facts an operator would care about.

    Kept separate from the structural comparison because a failure here should read as "a channel
    turned on", which is the sentence somebody needs to see, rather than as a dictionary diff.
    """
    #: **RE-DERIVED on 2026-08-28, and the property is unchanged.** This asserted that NOTHING
    #: was declared and NOTHING enabled, which was a true description of the world and not the
    #: property: the property is that a hostile environment CHANGES NOTHING. `OD-18` declared
    #: `d_24` and `OD-20-A` opened sending, so the baseline moved -- and it is now read from the
    #: clean world rather than written here, which is why this node stops needing an edit the
    #: next time he declares something.
    clean_states = {name: capability_state(name).value for name in CHANNEL_CAPABILITIES}
    clean_sending = {channel: channel_enabled(channel) for channel in ChannelId}

    with _hostile_environment():
        assert {
            name: capability_state(name).value for name in CHANNEL_CAPABILITIES
        } == clean_states, "a readiness record changed under a hostile environment"
        assert {channel: channel_enabled(channel) for channel in ChannelId} == clean_sending, (
            "a channel's enablement changed under a hostile environment"
        )


def test_the_cli_reports_the_same_state_under_a_hostile_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The operator-facing surface, because that is where a substitution would be visible.

    A CLI that reported channels enabled while the library refused would be worse than either: an
    operator would act on the report.
    """
    main(["capabilities"])
    baseline = capsys.readouterr().out
    with _hostile_environment():
        main(["capabilities"])
        hostile = capsys.readouterr().out
    assert hostile == baseline

    parsed = json.loads(baseline)
    #: **RE-DERIVED on 2026-08-28.** It asserted `False`, which described the world rather than
    #: the property this file is about: the CLI must agree with the library, whatever the
    #: library says. Now it compares the two -- so it goes on holding after the next declaration
    #: without anybody editing it.
    #: **Each direction against its OWN predicate**, since the CLI stopped answering one
    #: ambiguous `enabled`. Comparing the two sides under a single word was the shape that let
    #: a label change meaning undetected -- the `387` class, caught here by the reviewer.
    from channel_integration.compliance.readiness import may_receive_from, may_send_to
    from channel_integration.contracts.descriptor import ChannelId as _ChannelId

    assert parsed["any_channel_may_send"] is any(may_send_to(c) for c in _ChannelId), (
        "the CLI reports a different SENDING state than the library; an operator would act on "
        "the report"
    )
    assert parsed["any_channel_may_receive"] is any(may_receive_from(c) for c in _ChannelId), (
        "the CLI reports a different RECEIVING state than the library, which is the half his "
        "2026-08-18 decision governs"
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["capabilities", "--fixture"],
        ["capabilities", "--test-mode"],
        ["capabilities", "--enable", "SLACK"],
        ["render", "--channel", "SLACK", "--fixture-matrix"],
        ["render", "--channel", "SLACK", "--capability", "{}"],
        ["simulate", "--sandbox"],
        ["convert", "--file", "x.json", "--secret", "abc"],
    ],
)
def test_no_substituting_flag_is_accepted_by_the_cli(argv: list[str]) -> None:
    """A flag that does not exist cannot be set, which is the strongest form of "off by default".

    Each of these is a flag somebody would reach for. `argparse` rejects an unknown option with exit
    2, which this CLI's convention already reserves for a broken invocation — so the assertion is
    that the flag is *unknown*, not that it was handled safely.
    """
    assert main(argv) == 2, f"{argv} was accepted"


def test_the_governed_documents_still_refuse_under_a_hostile_environment() -> None:
    """The four `channel_governance/` documents, checked through their own resolution.

    A substitution that pointed the content root at a writable directory would be the most direct
    attack, and `CHANNEL_GOVERNED_CONTENT_ROOT` is set to one above.
    """
    with _hostile_environment():
        for channel in ChannelId:
            with pytest.raises(ContentUnresolvable):
                resolve_capability_matrix(channel)
