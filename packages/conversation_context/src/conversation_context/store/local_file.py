"""The file backend: memory that survives the caller dying every run — `FR-1107`, `FR-1108`.

## What it stores, and what it refuses to

One append-only JSONL file per resolved identity — the journal idiom this repository already
trusts — under a root the caller owns. The filename is a **digest** of the identity, so no chat id
lands in a directory listing; the identity itself travels inside the lines, where the privacy node
reads it back.

`remember` accepts **only** a `StructuredTurn`. A raw string, a dict, or anything with a free-text
shape is refused **before** any byte is written (`FR-1106`): the guard is at the door, not in a
review afterwards, and the node drives it with payloads that TRY to smuggle each thing
`003:FR-082` forbids.

## The `ConversationStore` seam, implemented — `FR-1107`

`003:FR-081` declared the store's contract in advance: two methods about nonce consumption, and
deliberately **no** method that could take custody of content. This class implements them — the
consumption record is exactly what `003` said a store *would own* — and the memory surface lives
BESIDE the seam, not inside it, so nothing the seam promised changes by this class existing. The
suite proves it by `isinstance` against the runtime-checkable Protocol and by behaviour.

## Single writer, and why that is written here

The caller runs once a day and dies; a future service on the VM would be a second writer. This
backend assumes ONE writer per root — append-only, no locks — and says so where a node can read
it. The day two writers exist, the backend is the Postgres one, which is what the seam is for.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from hashlib import sha256
from typing import TYPE_CHECKING

from ..contracts.memory import (
    MEMORY_DURATION,
    WINDOW_TURNS,
    NothingRemembered,
    RecallResult,
    Remembered,
    RememberedTurn,
    StructuredTurn,
    Unreadable,
    is_expired,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import timedelta
    from pathlib import Path

__all__ = ["LocalFileMemory"]

#: The zone the seam's local stamps use. The direct `remember()` caller passes its own; the
#: `ConversationMemory` boundary carries none, so the machine's business zone applies — the same
#: one every stamp in this repository pairs with UTC.
_LOCAL_ZONE = ZoneInfo("America/Sao_Paulo")

#: Keys whose PRESENCE in a stored line would mean `003:FR-082` material got in. The write-side
#: guard refuses the payloads; this list is what the storage-side node scans the artefact for.
FORBIDDEN_KEYS = ("question_text", "reply_text", "metric_value", "filter_value", "free_text")


class LocalFileMemory:
    """Memory with an owner, a scope and an expiry, on one JSONL file per identity."""

    def __init__(self, root: Path, *, duration: timedelta = MEMORY_DURATION) -> None:
        self._root = root
        self._duration = duration

    # ------------------------------------------------------------------ where an identity lives
    def _file_of(self, identity: str) -> Path:
        #: A digest, so no chat id lands in a directory listing. The identity itself travels
        #: inside the lines, where the privacy node reads it back.
        return self._root / f"{sha256(identity.encode('utf-8')).hexdigest()[:24]}.jsonl"

    # ------------------------------------------------------------------ the memory surface
    def remember(
        self,
        *,
        identity: str,
        scope: str,
        message_id: str,
        turn: StructuredTurn,
        instant: datetime,
        zone: ZoneInfo,
    ) -> bool:
        """Store one turn. ``False`` when the (identity, message id) pair already holds one.

        **The pair is the idempotency key from birth** (`FR-1109`): per-day cost a real send to
        three people (`S-22`), and per-identity alone would drop every amendment after the first.
        """
        if not isinstance(turn, StructuredTurn):
            #: **The door, not the review.** A raw string or a dict is where forbidden material
            #: would come in; the type is the guard, and the node tries to smuggle past it.
            message = f"a turn must be a StructuredTurn, not {type(turn).__name__}"
            raise TypeError(message)
        if instant.tzinfo is None:
            message = "instant carries no zone; refusing to assume one"
            raise ValueError(message)
        if not identity:
            message = "a memory nobody can attribute to an identity is not stored"
            raise ValueError(message)

        if self._pair_exists(identity, message_id):
            return False

        utc = instant.astimezone(UTC)
        line = {
            "identity": identity,
            "scope": scope,
            "message_id": message_id,
            "stored_at_utc": utc.isoformat(),
            "stored_at_local": utc.astimezone(zone).isoformat(),
            "expires_basis": utc.isoformat(),
            "turn": asdict(turn),
        }
        path = self._file_of(identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        return True

    def recall(self, identity: str, *, now: datetime) -> RecallResult:
        """The window for this identity — one of exactly three answers (`FR-1108`).

        Expiry is derived HERE, at read time, from the stamped basis (`FR-1104`). A file that
        cannot be read or parsed is `Unreadable`, never `NothingRemembered`: *could not read*
        impersonating *fresh conversation* is the silent failure this repository keeps paying for.
        """
        path = self._file_of(identity)
        if not path.exists():
            return NothingRemembered()
        try:
            raw_lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            return Unreadable(f"{type(error).__name__}: {error}")

        kept: list[RememberedTurn] = []
        for raw in raw_lines:
            if not raw.strip():
                continue
            try:
                line = json.loads(raw)
                if line.get("kind") == "consumption":
                    continue
                #: **The identity inside the line must match the file asked for** — a digest
                #: collision or a misplaced line must not leak another chat's turn (`FR-1102`).
                if line["identity"] != identity:
                    continue
                basis = datetime.fromisoformat(line["expires_basis"])
                if is_expired(basis, now, self._duration):
                    continue
                kept.append(
                    RememberedTurn(
                        identity=line["identity"],
                        scope=line["scope"],
                        message_id=line["message_id"],
                        stored_at_utc=line["stored_at_utc"],
                        stored_at_local=line["stored_at_local"],
                        expires_basis=line["expires_basis"],
                        turn=StructuredTurn(
                            intent=line["turn"]["intent"],
                            metric_ids=tuple(line["turn"]["metric_ids"]),
                            period=line["turn"]["period"],
                            filter_fields=tuple(line["turn"].get("filter_fields") or ()),
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                #: A torn or malformed line makes the WHOLE answer unreadable. Memory integrity
                #: outranks availability here: an answer built on half a memory is worse than an
                #: answer that says it has none to rely on.
                return Unreadable(f"linha ilegivel no diario de conversa: {type(error).__name__}")

        if not kept:
            return NothingRemembered()
        return Remembered(tuple(kept[-WINDOW_TURNS:]))

    def _pair_exists(self, identity: str, message_id: str) -> bool:
        path = self._file_of(identity)
        if not path.exists():
            return False
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if line.get("identity") == identity and line.get("message_id") == message_id:
                return True
        return False

    # ------------------------------------------------------------------ the 003:FR-081 seam
    def record_consumption(self, nonce: str, *, correlation_id: str) -> None:
        """The seam's whole addition — `003`'s `STORE_WOULD_OWN` names consumption records."""
        path = self._root / "consumptions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"kind": "consumption", "nonce": nonce, "correlation_id": correlation_id},
                    ensure_ascii=False,
                )
                + "\n"
            )

    def consumed(self, nonce: str, *, correlation_id: str) -> bool:
        """Whether this nonce was consumed. A bool, never a raise — the governed refusal and its
        code belong to `003`, exactly as its Protocol docstring says."""
        path = self._root / "consumptions.jsonl"
        if not path.exists():
            return False
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if line.get("nonce") == nonce and line.get("correlation_id") == correlation_id:
                return True
        return False

    # ------------------------------------------------------------ the OD-69 memory seam
    def remember_turn(
        self,
        *,
        identity: str,
        scope: str,
        message_id: str,
        intent: str,
        metric_ids: tuple[str, ...],
        period: str,
        filter_fields: tuple[str, ...],
        instant: datetime,
    ) -> bool:
        """`003`'s `ConversationMemory`, satisfied by construction — `OD-69`.

        The primitives arrive exactly as the boundary Protocol declares them and become a
        `StructuredTurn` at the door, so everything the door refuses stays refused whichever seam
        the caller came through.
        """
        return self.remember(
            identity=identity,
            scope=scope,
            message_id=message_id,
            turn=StructuredTurn(
                intent=intent,
                metric_ids=metric_ids,
                period=period,
                filter_fields=filter_fields,
            ),
            instant=instant,
            zone=_LOCAL_ZONE,
        )

    def remembered_window(
        self, identity: str, *, now: datetime
    ) -> tuple[dict[str, object], ...] | None:
        """Three states with primitives, as the boundary declares: window, ``()``, or ``None``."""
        answer = self.recall(identity, now=now)
        if isinstance(answer, Unreadable):
            return None
        if isinstance(answer, NothingRemembered):
            return ()
        return tuple(
            {
                "message_id": item.message_id,
                "intent": item.turn.intent,
                "metric_ids": item.turn.metric_ids,
                "period": item.turn.period,
                "filter_fields": item.turn.filter_fields,
                "stored_at_utc": item.stored_at_utc,
            }
            for item in answer.turns
        )
