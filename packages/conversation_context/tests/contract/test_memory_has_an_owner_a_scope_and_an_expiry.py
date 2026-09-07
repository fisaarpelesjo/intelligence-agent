"""Phases A–C of spec `011`, driven on the real backend — every promise the spec makes, a node.

The two decisions inside are HIS with dates: `OD-67` (one day) and `OD-68` (a window of structured
turns). The guards are the birth-guards the spec §§1–7 name, each driven in the direction that
would fail silently.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from conversation_context.contracts.memory import (
    MEMORY_DURATION,
    WINDOW_TURNS,
    NothingRemembered,
    Remembered,
    StructuredTurn,
    Unreadable,
    is_expired,
)
from conversation_context.store.local_file import FORBIDDEN_KEYS, LocalFileMemory

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path

pytestmark = pytest.mark.contract

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 8, 31, 20, 0, tzinfo=UTC)

#: Stand-ins: resolved identities as `004` would hand them over — never raw chat ids in a test.
CHAT_A = "telegram:tenant-example:identity-a"
CHAT_B = "telegram:tenant-example:identity-b"

A_TURN = StructuredTurn(
    intent="kpi_question",
    metric_ids=("new_trials",),
    period="last_week",
    filter_fields=("country",),
)


def _store(tmp_path: Path, **kwargs: object) -> LocalFileMemory:
    return LocalFileMemory(tmp_path / "memoria", **kwargs)  # type: ignore[arg-type]


def _remember(
    store: LocalFileMemory, identity: str, message_id: str, *, at: datetime = NOW
) -> bool:
    return store.remember(
        identity=identity,
        scope="tenant-example",
        message_id=message_id,
        turn=A_TURN,
        instant=at,
        zone=SAO_PAULO,
    )


# ---------------------------------------------------------------- FR-1102 · SC-1101: privacy


def test_what_A_wrote_B_cannot_read_and_A_still_can(tmp_path: Path) -> None:  # noqa: N802
    """**Both directions, on the real reader.** A leak here is the defect this FR exists for."""
    store = _store(tmp_path)
    assert _remember(store, CHAT_A, "m-1")

    theirs = store.recall(CHAT_B, now=NOW)
    assert isinstance(theirs, NothingRemembered), "chat B saw chat A's memory"

    mine = store.recall(CHAT_A, now=NOW)
    assert isinstance(mine, Remembered), "chat A lost its own memory"
    assert mine.turns[0].identity == CHAT_A


def test_a_line_inside_the_wrong_file_does_not_leak(tmp_path: Path) -> None:
    """The identity INSIDE the line must match the identity asked for — a misplaced line is
    filtered, not served (`FR-1102` at the byte level)."""
    store = _store(tmp_path)
    assert _remember(store, CHAT_A, "m-1")
    #: Forge: append a line carrying B's identity into A's file.
    file_a = store._file_of(CHAT_A)
    line = json.loads(file_a.read_text(encoding="utf-8").splitlines()[0])
    line["identity"] = CHAT_B
    line["message_id"] = "m-forjada"
    with file_a.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    mine = store.recall(CHAT_A, now=NOW)
    assert isinstance(mine, Remembered)
    assert all(turn.identity == CHAT_A for turn in mine.turns), "a foreign line was served"


# ---------------------------------------------------------------- FR-1103/04 · SC-1102: expiry


def test_within_a_day_returns_and_past_a_day_does_not(tmp_path: Path) -> None:
    """`OD-67`: the conversation of today remembers until tomorrow — derived at read time."""
    store = _store(tmp_path)
    assert _remember(store, CHAT_A, "m-1", at=NOW)

    #: Within: 23h59 later.
    fresh = store.recall(CHAT_A, now=NOW + timedelta(hours=23, minutes=59))
    assert isinstance(fresh, Remembered)

    #: Past: exactly one day later it is gone — and gone reads as NOTHING, not as an error.
    stale = store.recall(CHAT_A, now=NOW + MEMORY_DURATION)
    assert isinstance(stale, NothingRemembered)


def test_expiry_needs_zones_on_both_instants() -> None:
    """`FR-1110`: a naive instant cannot anchor an expiry — refused, never assumed UTC."""
    with pytest.raises(ValueError, match="zone"):
        is_expired(datetime(2026, 8, 31, 20, 0), NOW)  # noqa: DTZ001
    with pytest.raises(ValueError, match="zone"):
        is_expired(NOW, datetime(2026, 9, 1, 20, 0))  # noqa: DTZ001


def test_no_stored_label_asserts_the_expiry_state(tmp_path: Path) -> None:
    """`FR-1104`, the `S-25` refusal from birth: the artefact stores a BASIS, never a verdict."""
    store = _store(tmp_path)
    assert _remember(store, CHAT_A, "m-1")
    raw = store._file_of(CHAT_A).read_text(encoding="utf-8")
    for label in ("active", "expired", "vigente", "vencido"):
        assert label not in raw, f"a stored label ({label}) asserts a state that changes by itself"
    assert "expires_basis" in raw


# ---------------------------------------------------------------- FR-1108 · SC-1102/03: 3 states


def test_could_not_read_never_impersonates_a_fresh_conversation(tmp_path: Path) -> None:
    """**The third state is the whole point.** A torn line makes the answer `Unreadable`,
    and `Unreadable` is not `NothingRemembered`."""
    store = _store(tmp_path)
    assert _remember(store, CHAT_A, "m-1")
    with store._file_of(CHAT_A).open("a", encoding="utf-8") as handle:
        handle.write('{"identity": "telegram:tenant-example:identity-a", "turn": {"in')

    answer = store.recall(CHAT_A, now=NOW)
    assert isinstance(answer, Unreadable), f"a torn file answered {type(answer).__name__}"
    assert answer.reason


def test_memory_survives_the_caller_dying(tmp_path: Path) -> None:
    """`SC-1103`: the caller dies every run; a NEW store instance still remembers."""
    assert _remember(_store(tmp_path), CHAT_A, "m-1")
    reborn = _store(tmp_path)
    answer = reborn.recall(CHAT_A, now=NOW)
    assert isinstance(answer, Remembered)


# ---------------------------------------------------------------- FR-1109 · SC-1104: the pair


def test_the_same_pair_twice_stores_once_and_a_new_message_stores_again(tmp_path: Path) -> None:
    """Per PAIR from birth — `S-22` cost a day when this was per-day."""
    store = _store(tmp_path)
    assert _remember(store, CHAT_A, "m-1") is True
    assert _remember(store, CHAT_A, "m-1") is False, "the same pair stored twice"
    assert _remember(store, CHAT_A, "m-2") is True, "a new message was dropped"

    answer = store.recall(CHAT_A, now=NOW)
    assert isinstance(answer, Remembered)
    assert [turn.message_id for turn in answer.turns] == ["m-1", "m-2"]

    #: And the same message id under ANOTHER identity is another pair — not a duplicate.
    assert _remember(store, CHAT_B, "m-1") is True


# ---------------------------------------------------------------- FR-1105: the window


def test_the_window_keeps_the_last_N_oldest_first(tmp_path: Path) -> None:  # noqa: N802
    """`OD-68`'s window, capped by the design bound whose successor is written."""
    store = _store(tmp_path)
    for index in range(WINDOW_TURNS + 4):
        assert _remember(store, CHAT_A, f"m-{index:03d}")

    answer = store.recall(CHAT_A, now=NOW)
    assert isinstance(answer, Remembered)
    assert len(answer.turns) == WINDOW_TURNS
    assert answer.turns[0].message_id == "m-004", "the window did not slide"
    assert answer.turns[-1].message_id == f"m-{WINDOW_TURNS + 3:03d}"


# ---------------------------------------------------------------- FR-1106 · SC-1106: forbidden


def test_smuggling_each_forbidden_kind_is_refused_at_the_door(tmp_path: Path) -> None:
    """`003:FR-082` applied in advance, driven with payloads that TRY — the 420 rule.

    A guard that passes only because the payload happens to be clean is an empty mutation.
    """
    store = _store(tmp_path)
    smuggles = (
        "qual foi o trial conversion na semana passada?",  # raw question text
        {"question_text": "qual foi o trial?"},
        {"reply_text": "foi 2,89%"},
        {"metric_value": "2.89"},
        {"filter_value": "BR"},
    )
    for payload in smuggles:
        with pytest.raises(TypeError, match="StructuredTurn"):
            store.remember(
                identity=CHAT_A,
                scope="tenant-example",
                message_id="m-contrabando",
                turn=payload,  # type: ignore[arg-type]
                instant=NOW,
                zone=SAO_PAULO,
            )
    #: And NOTHING was written by any refused attempt.
    assert not store._file_of(CHAT_A).exists(), "a refused payload still reached the disk"


def test_the_stored_artefact_carries_no_forbidden_key_and_the_scan_can_see(tmp_path: Path) -> None:
    """`SC-1106` over the BYTES, and the scan is proven able to fire.

    Asserted over what was stored, not over intentions — and the same scan is pointed at a
    deliberately poisoned file to prove it would light, per the 420 empty-mutation rule.
    """
    store = _store(tmp_path)
    assert _remember(store, CHAT_A, "m-1")
    raw = store._file_of(CHAT_A).read_text(encoding="utf-8")
    for key in FORBIDDEN_KEYS:
        assert key not in raw, f"the artefact carries {key}"

    #: The scan itself bites: a poisoned line is exactly what it exists to see.
    poisoned = tmp_path / "poisoned.jsonl"
    poisoned.write_text('{"question_text": "raw"}\n', encoding="utf-8")
    assert any(key in poisoned.read_text(encoding="utf-8") for key in FORBIDDEN_KEYS)


def test_the_turn_schema_has_no_slot_for_free_text() -> None:
    """The schema is the guard: no field whose NAME invites content `FR-082` forbids."""
    fields = set(StructuredTurn.__dataclass_fields__)
    assert fields == {"intent", "metric_ids", "period", "filter_fields"}
    for forbidden in FORBIDDEN_KEYS:
        assert forbidden not in fields


# ---------------------------------------------------------------- FR-1107 · SC-1105: the seam


def test_the_backend_satisfies_the_seam_003_declared(tmp_path: Path) -> None:
    """`003:FR-081`'s Protocol, by isinstance and by behaviour — the store `003` anticipated.

    Consumption records are in `003`'s own `STORE_WOULD_OWN`; the memory surface lives BESIDE the
    seam, adding nothing to it and weakening nothing it promised.
    """
    from analytics_interaction.clarification.future_store import (
        STORE_MUST_NEVER_OWN,
        ConversationStore,
    )

    store = _store(tmp_path)
    assert isinstance(store, ConversationStore), "the backend does not satisfy the seam"

    assert store.consumed("nonce-1", correlation_id="c-1") is False
    store.record_consumption("nonce-1", correlation_id="c-1")
    assert store.consumed("nonce-1", correlation_id="c-1") is True
    #: The same nonce under another correlation is not consumed — the pair matters here too.
    assert store.consumed("nonce-1", correlation_id="c-2") is False

    #: And what `003` forbade the store to own maps onto the keys this backend refuses to write.
    assert set(STORE_MUST_NEVER_OWN) == {
        "raw_question_text",
        "free_text_clarification_replies",
        "metric_values",
        "filter_values",
    }


def test_no_identity_lands_in_a_directory_listing(tmp_path: Path) -> None:
    """The file-per-identity layer's REAL property: the filename is a digest.

    Found by mutation: collapsing to one shared file kept every privacy node green, because the
    identity-inside-the-line filter is the layer that actually guards reads — defense in depth
    doing its job. What the digest layer alone guarantees is THIS: no resolved identity (which may
    embed a chat id) is readable in a directory listing, however the files are organised.
    """
    store = _store(tmp_path)
    assert _remember(store, CHAT_A, "m-1")
    for path in (tmp_path / "memoria").iterdir():
        assert CHAT_A not in path.name
        assert "identity-a" not in path.name


# ---------------------------------------------------------------- OD-69: the amended boundary


def test_the_backend_satisfies_the_amended_memory_seam(tmp_path: Path) -> None:
    """`OD-69` opened `003`'s boundary THROUGH the contract, and this backend satisfies it.

    By `isinstance` and by behaviour: what goes in through `remember_turn` comes back through
    `remembered_window` with three states — a window, `()` for nothing, `None` for could-not-read
    — and the same door refuses the same smuggling whichever seam the caller came through.
    """
    from analytics_interaction.clarification.future_store import ConversationMemory

    store = _store(tmp_path)
    assert isinstance(store, ConversationMemory), "the backend does not satisfy the amended seam"

    assert (
        store.remember_turn(
            identity=CHAT_A,
            scope="tenant-example",
            message_id="m-seam",
            intent="clarification_resumed",
            metric_ids=("new_trials",),
            period="",
            filter_fields=(),
            instant=NOW,
        )
        is True
    )
    #: The pair holds across seams: the same message through the DIRECT door is a duplicate.
    assert _remember(store, CHAT_A, "m-seam") is False

    window = store.remembered_window(CHAT_A, now=NOW)
    assert window is not None and len(window) == 1
    assert window[0]["intent"] == "clarification_resumed"
    assert window[0]["metric_ids"] == ("new_trials",)

    #: Nothing remembered is (), never None.
    assert store.remembered_window(CHAT_B, now=NOW) == ()

    #: And could-not-read is None, never () — the three states survive the primitive encoding.
    with store._file_of(CHAT_A).open("a", encoding="utf-8") as handle:
        handle.write('{"rasgada')
    assert store.remembered_window(CHAT_A, now=NOW) is None
