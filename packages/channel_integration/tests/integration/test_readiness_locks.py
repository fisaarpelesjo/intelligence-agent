"""T135 — each lock gates exactly one capability, and gates it alone (`SC-053`, `SC-059`).

The property is **independence**. Eleven governed decisions are open; each one holds back a
specific capability; and satisfying any one of them must unlock that capability and *nothing else*.
A lock that unlocked two things would mean one approval silently bought a second, and a lock that
unlocked nothing would mean the record is decorative.

## The task says ten locks. There are eleven. The code wins, and the difference is recorded.

`T135`'s wording — "the ten locks" — predates `d_32`, which
`src/channel_integration/compliance/readiness.py` records as added on 2026-08-17: "a record in the
directory that this tuple does not name is a decorative record, which is the failure the naming
prevents". `CHANNEL_CAPABILITIES` holds eleven entries, and this file is written against that tuple
rather than against the number in the task text — derived from it, in fact, so a twelfth cannot
appear without this file exercising it.

The staleness is recorded in the ledger row rather than quietly reconciled, exactly as `T119`'s was.

## `d_32` fails closed **PARTIALLY**, and that is stated in the record itself

Every other lock in this feature fails fully closed. `d_32` does not, and the record says so in its
own words: "This is the one place in this feature where an unmet governed value leaves a gap open
rather than closed, and it is recorded here for exactly that reason." A test that treated all eleven
as identical would paper over the one that is different, so
`test_exactly_one_lock_fails_closed_only_partially` asserts the asymmetry and holds the record to
its own sentence.

## The real record is never edited

Not once, not temporarily, not restored afterwards. The fixture is an **in-memory** capability map
built from what the real records actually say, with one entry replaced; `load_all_records` is
patched to return it for the duration of one assertion.
`test_the_real_records_are_untouched` hashes all four files at import and again at the end.

Patching the loader rather than pointing `readiness_root` at a temporary directory is deliberate:
`readiness_root` is "located rather than configured" precisely so no deployment can aim readiness at
a file of its own making, and a test that made it configurable would be modelling a seam the design
refuses to have.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from channel_integration.compliance import readiness
from channel_integration.compliance.readiness import (
    CHANNEL_CAPABILITIES,
    READINESS_RECORDS,
    Capability,
    CapabilityState,
    aggregate_ready,
    capabilities_in_own_record,
    capability_state,
    channel_enabled,
    load_all_records,
    readiness_root,
)
from channel_integration.contracts.descriptor import ChannelId

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = pytest.mark.integration

#: Which channel each credential lock gates. Derived from the same source the production code uses,
#: so this cannot drift from it: a test with its own copy of the mapping would keep passing after
#: the real one was rewired.
_CREDENTIAL_LOCKS: Mapping[str, ChannelId] = {
    readiness_module_value.value: channel
    for channel, readiness_module_value in vars(readiness)["_CHANNEL_CREDENTIAL"].items()
}


def _digest_of_records() -> dict[str, str]:
    """A content hash per record file, so an edit anywhere is detectable."""
    root = readiness_root()
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in READINESS_RECORDS
    }


_DIGESTS_AT_IMPORT = _digest_of_records()


def _with_one_lock_satisfied(identifier: str) -> dict[str, Capability]:
    """The real capability map, with ``identifier`` alone flipped to READY. **In memory.**

    Built from `load_all_records()` rather than from a hand-written fixture: the point is to change
    one thing about the real state, and a hand-written map would also change everything else that
    was ever mis-transcribed.
    """
    fixture: dict[str, Capability] = {}
    for key, capability in load_all_records().items():
        if key == identifier:
            fixture[key] = Capability(
                identifier=capability.identifier,
                declared=True,
                evidence_ref="fixture-evidence-not-a-real-approval",
                owner_role=capability.owner_role,
            )
        else:
            fixture[key] = capability
    return fixture


#: The one lock the owner opened, and it is named rather than counted.
#:
#: **RE-DERIVED on 2026-08-28, not deleted** -- `FR-818`. This file's baseline was *every lock
#: closed*, which was a true description of the world and stopped being one when `OD-18` signed
#: `d_24` and `OD-20-A` applied it to SENDING. The assertions below are all statements about a
#: CHANGE from the baseline, so the baseline moved and the reasoning did not.
OPENED_BY_THE_OWNER = "d_24"
#: OD-91 (2026-09-02): a segunda abertura dele — d_34 com a emenda OD-87 verde.
OPENED_SET = ("d_24", "d_34")

#: The locks still closed. Derived by removing the one he opened, so a second declaration is a
#: failure here rather than a silent widening.
CLOSED_LOCKS = tuple(name for name in CHANNEL_CAPABILITIES if name not in OPENED_SET)


def test_every_lock_except_the_one_he_opened_is_closed() -> None:
    """The baseline. Every assertion below is a statement about a change from this state."""
    for identifier in CLOSED_LOCKS:
        assert capability_state(identifier) is not CapabilityState.READY, (
            f"{identifier} is ready, so this file is measuring a different system"
        )
    # OD-91: aggregate_ready e CONJUNCAO ("todos prontos?") — com os fechados no meio,
    # o conjunto inteiro segue NAO-pronto; os dois abertos respondem sozinhos.
    assert not aggregate_ready(CHANNEL_CAPABILITIES), (
        "o conjunto inteiro leu pronto; os cadeados fechados sumiram"
    )
    assert aggregate_ready(OPENED_SET), "os dois que ele abriu nao leem prontos juntos"


def test_the_lock_he_opened_is_open_and_it_is_the_only_one() -> None:
    """**The other half.** A file that only excused `d_24` would stop measuring it.

    Emendado no ciclo 510 (2026-09-02, OD-91): a segunda abertura dele (d_34) entra no
    conjunto; um TERCEIRO aberto continua falhando aqui. Nome fincado pelo baseline de
    node-IDs do proprio 004 — o corpo e a verdade."""
    for name in OPENED_SET:
        assert capability_state(name) is CapabilityState.READY, f"{name} deveria estar aberto"
    opened = sorted(
        name for name in CHANNEL_CAPABILITIES if capability_state(name) is CapabilityState.READY
    )
    assert opened == sorted(OPENED_SET), f"{opened} are open; exactly two were authorized"


def test_exactly_one_channel_may_send_and_none_may_receive() -> None:
    """The consequence of the four credential locks, **after one of them was lifted**.

    `OD-20-A` split the key: sending follows the credential, receiving also needs a scheme that
    signs an instant. Telegram signs none, so it may send and may not receive — which is the
    whole shape of his decision, asserted rather than described.
    """
    from channel_integration.compliance.readiness import may_receive_from, may_send_to

    sending = sorted(channel.value for channel in ChannelId if may_send_to(channel))
    receiving = sorted(channel.value for channel in ChannelId if may_receive_from(channel))
    assert sending == [ChannelId.TELEGRAM.value], f"{sending} may send"
    assert receiving == [], f"{receiving} may RECEIVE, which the 2026-08-18 decision forbids"


@pytest.mark.parametrize("identifier", CLOSED_LOCKS)
def test_satisfying_one_lock_changes_that_lock_and_no_other(
    identifier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Independence, one lock at a time, across all eleven.

    Parametrised over `CHANNEL_CAPABILITIES` rather than over a literal list, so a twelfth lock is
    exercised the moment it is declared instead of being silently untested.
    """
    baseline = {key: capability.state for key, capability in load_all_records().items()}
    fixture = _with_one_lock_satisfied(identifier)
    monkeypatch.setattr(readiness, "load_all_records", lambda: fixture)

    assert capability_state(identifier) is CapabilityState.READY, (
        f"satisfying {identifier} did not make it ready, so the lock gates nothing"
    )
    assert aggregate_ready([identifier])

    for other in CHANNEL_CAPABILITIES:
        if other == identifier:
            continue
        assert capability_state(other) is baseline[other], (
            f"satisfying {identifier} also changed {other}, so one approval bought two"
        )
        #: UNCHANGED is the property, not CLOSED. `d_24` is open by his decision and must stay
        #: open; asserting it closed here would make this node measure the world instead of the
        #: change, which is what it went red for on 2026-08-28.
        assert aggregate_ready([other]) is (baseline[other] is CapabilityState.READY)


@pytest.mark.parametrize(
    "identifier", sorted(name for name in _CREDENTIAL_LOCKS if name in CLOSED_LOCKS)
)
def test_a_credential_lock_enables_its_own_channel_and_only_that_one(
    identifier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`SC-059` at the level an operator would feel it: one approval, one channel."""
    gated = _CREDENTIAL_LOCKS[identifier]
    #: The clean world, read BEFORE the fixture: `d_24` is open by his decision and Telegram may
    #: send. The property is that satisfying one lock changes ITS channel and leaves the others
    #: exactly as they were -- not that the others are off, which was true yesterday and is what
    #: this node went red for on 2026-08-28.
    before = {channel: channel_enabled(channel) for channel in ChannelId}

    fixture = _with_one_lock_satisfied(identifier)
    monkeypatch.setattr(readiness, "load_all_records", lambda: fixture)

    assert channel_enabled(gated), f"{identifier} did not enable {gated.value}"
    for channel in ChannelId:
        if channel is gated:
            continue
        assert channel_enabled(channel) is before[channel], (
            f"satisfying {identifier} changed {channel.value} as well, which no approval covered"
        )


@pytest.mark.parametrize("identifier", CLOSED_LOCKS)
def test_the_aggregate_stays_closed_while_any_lock_is_open(
    identifier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conjunction, asserted from the direction that can fail.

    Eleven separate unlocks are eleven separate approvals. Lifting one must not move the aggregate,
    because the aggregate is what "this feature is ready" means and no single decision is that.
    """
    fixture = _with_one_lock_satisfied(identifier)
    monkeypatch.setattr(readiness, "load_all_records", lambda: fixture)

    assert not aggregate_ready(CHANNEL_CAPABILITIES), (
        f"satisfying {identifier} alone made the whole feature read ready"
    )


def test_a_declaration_without_evidence_unlocks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half of `READY`, which is the half an eager operator would skip.

    Declaring a capability is a statement of intent. Evidence is the thing that makes it true, and a
    lock that opened on the declaration alone would be a lock anyone could talk their way past.
    """
    #: A lock that is CLOSED, so the node still measures a transition from closed.
    identifier = CLOSED_LOCKS[0]
    fixture = dict(load_all_records())
    original = fixture[identifier]
    fixture[identifier] = Capability(
        identifier=original.identifier,
        declared=True,
        evidence_ref=None,
        owner_role=original.owner_role,
    )
    monkeypatch.setattr(readiness, "load_all_records", lambda: fixture)

    assert capability_state(identifier) is CapabilityState.DECLARED_WITHOUT_EVIDENCE
    assert not aggregate_ready([identifier])
    assert not channel_enabled(_CREDENTIAL_LOCKS[identifier])


def test_evidence_without_a_declaration_unlocks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """And the mirror. Evidence nobody declared is evidence nobody is answerable for."""
    #: A lock that is CLOSED, so the node still measures a transition from closed.
    identifier = CLOSED_LOCKS[0]
    fixture = dict(load_all_records())
    original = fixture[identifier]
    fixture[identifier] = Capability(
        identifier=original.identifier,
        declared=False,
        evidence_ref="fixture-evidence-not-a-real-approval",
        owner_role=original.owner_role,
    )
    monkeypatch.setattr(readiness, "load_all_records", lambda: fixture)

    assert capability_state(identifier) is CapabilityState.EVIDENCE_WITHOUT_DECLARATION
    assert not aggregate_ready([identifier])


def test_the_locks_and_the_record_name_the_same_set() -> None:
    """The correspondence, in **both** directions, because either alone can be right while wrong.

    An identifier that no record declares would raise on every read; a declared entry this tuple
    does not name would be decorative. The two sets must be the same set.

    ## The count is gone, and its own message said why

    It asserted `== 11` and told the next reader to *"re-derive rather than adjusting the
    number"*. **The number was the weaker half all along**: it moved to twelve when `d_34` was
    listed under `OD-17`, and it would have moved again on the next capability — while the
    correspondence, which is the property, holds at any count.

    And the missing half is the one that let `d_34` live a day governing nothing: it checked
    that every NAMED lock is declared, and never that every DECLARED lock is named.
    """
    assert len(set(CHANNEL_CAPABILITIES)) == len(CHANNEL_CAPABILITIES), "a lock is listed twice"

    own = set(capabilities_in_own_record())
    listed = set(CHANNEL_CAPABILITIES)
    assert listed == own, (
        f"the enumeration and this feature's record disagree: {sorted(listed - own)} are named "
        f"and absent from the file, {sorted(own - listed)} are in the file and govern nothing"
    )

    declared = load_all_records()
    missing = [key for key in CHANNEL_CAPABILITIES if key not in declared]
    assert not missing, f"these locks are named in code and declared by no record: {missing}"


def test_exactly_one_lock_fails_closed_only_partially() -> None:
    """`d_32` is the asymmetry, and the record is held to saying so in its own words.

    Read out of the governed record rather than restated here. If a second lock ever becomes
    partially fail-closed, or if `d_32` becomes fully closed, this fails — which is the point: the
    one place a gap stays open is the one place nobody may forget.
    """
    record = (readiness_root() / "multichannel-external-readiness.yaml").read_text(encoding="utf-8")
    assert "  - id: d_32" in record, "d_32 is no longer declared by the 004 record"

    entries = record.split("  - id: ")[1:]
    partial = sorted(
        entry.split("\n", 1)[0].strip()
        for entry in entries
        if "fail_closed" in entry and "PARTIAL" in entry.split("fail_closed")[1][:400]
    )
    assert partial == ["d_32"], (
        f"the set of partially fail-closed locks is {partial}, not ['d_32']. Every other lock in "
        "this feature closes fully, and a second exception is a decision nobody recorded"
    )
    assert "leaves a gap open" in record, (
        "the record no longer states the gap in its own words, so this holds it to nothing"
    )


def test_the_real_records_are_untouched() -> None:
    """Every fixture above is in memory. This proves it rather than promising it."""
    assert _digest_of_records() == _DIGESTS_AT_IMPORT, (
        "a readiness record changed on disk while this module ran. The real record is evidence, "
        "and a test that edits evidence is a test that manufactures it"
    )


def test_the_fixture_map_is_not_the_real_one() -> None:
    """Anti-vacuity: the fixture genuinely differs, and only in the one entry it claims to.

    Without this, a `_with_one_lock_satisfied` that quietly returned the real map would make every
    independence assertion above pass by never changing anything.
    """
    #: A lock that is CLOSED, so the node still measures a transition from closed.
    identifier = CLOSED_LOCKS[0]
    real = load_all_records()
    fixture = _with_one_lock_satisfied(identifier)

    assert set(fixture) == set(real), "the fixture added or dropped a capability"
    assert fixture[identifier].state is CapabilityState.READY
    assert real[identifier].state is not CapabilityState.READY

    differing = sorted(key for key in real if fixture[key].state is not real[key].state)
    assert differing == [identifier], f"the fixture changed more than one entry: {differing}"
