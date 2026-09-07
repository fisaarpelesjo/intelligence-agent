"""One send per declared recipient, and the failures that must not become silence — `FR-1007`.

## Why this is in the package and not in the harness script

The first version of this loop lived in `deliver_daily_report.py`, and the harness nodes **stub
that module out** — they replace `deliver` with a function whose behaviour they choose, so the
loop itself was reached by nothing. Driven, three mutations of it stayed green:

| mutation | result before this module existed |
|---|---|
| the loop `break`s on the first failure | **987 passed** |
| a pending recipient **outside** the declaration is accepted | **987 passed** |
| `getChat` stops being called before each send | **987 passed** |

**The thing that actually sends was the thing no node could reach**, which is cycle 408's lesson in
its most expensive form: the guard cannot be where the decision is not.

## What it refuses, and why each refusal is a refusal and not a crash

- a recipient **outside** the declaration — `OD-7` as amended on 2026-08-31 is *the declared
  recipients and no other*, and the caller does not get to widen the list;
- an **empty** list of pending recipients — sending to nobody satisfies every check phrased as
  "each recipient was authorised", so it is answered here rather than downstream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Iterable, Sequence

__all__ = ["FanOut", "send_to_each"]


class FanOut(NamedTuple):
    """What one pass over the recipients turned out to be."""

    sent: tuple[str, ...]
    failed: tuple[str, ...]
    refused_for: str | None = None

    @property
    def all_delivered(self) -> bool:
        """**Two of three is not success**, and neither is a refusal before sending."""
        return self.refused_for is None and not self.failed and bool(self.sent)


def send_to_each(
    pending: Sequence[str],
    declared: Iterable[str],
    *,
    send: Callable[[str], None],
    identify: Callable[[str], None],
    on_result: Callable[[str, str, str], None] | None = None,
) -> FanOut:
    """Send once to each of ``pending``, in order, and report **per recipient**.

    ``identify`` is called **before every send** — that is `getChat` in production, and it is
    `OD-7`'s method surviving the amendment: who is about to receive something is read from the
    API and shown, never assumed from a number in a file. Its failure is the recipient's failure:
    sending to a chat nobody could identify is exactly what it exists to prevent.

    **One failing does not stop the others.** The loop runs to the end and the outcome is recorded
    for each person, because a failure on the second must not cost the third its delivery.
    """
    allowed = set(declared)
    if not allowed:
        return FanOut((), (), "nenhum destinatario declarado")

    outside = [one for one in pending if one not in allowed]
    if outside:
        #: A governed refusal, not a crash, and **nothing is sent** — not even to the ones that
        #: were fine. A list containing a chat nobody declared is not a list to act on.
        return FanOut((), (), f"{len(outside)} destinatario(s) fora da lista declarada")

    if not pending:
        return FanOut((), (), "nenhum destinatario pendente")

    sent: list[str] = []
    failed: list[str] = []
    for recipient in pending:
        try:
            identify(recipient)
            send(recipient)
        except Exception as error:
            failed.append(recipient)
            if on_result is not None:
                on_result(recipient, "failed", f"{type(error).__name__}: {error}"[:400])
            continue
        sent.append(recipient)
        if on_result is not None:
            on_result(recipient, "sent", "")

    return FanOut(tuple(sent), tuple(failed))
