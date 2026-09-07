"""Governed proactive distribution — saying it to the person who needs it, unasked.

The seventh package of the governed stack, and the first that **originates** anything.
That is its whole novelty and its whole risk, so the authority for it is narrow and
written down where a reviewer reads it. The ADR that supersedes `004`'s `FR-062`
**for one case only** lives in `docs/adr/`, and `004`'s specification is not amended.

**Three conditions, all required**: the finding is prioritisable, the channel is
already enabled, and the recipient has accepted. Everything outside them stays under
`FR-062` unchanged.

**Nothing here is generated.** The message is five labelled fields — the owner's shape,
chosen on 2026-08-27 over three alternatives — and the labels are his words. He has not
written them, so **every path through this package refuses today**, and that is the
feature working rather than a gap in it.

**And it originates nothing on its own.** No scheduler, no timer, no thread, no event
loop: a run is called and receives what it needs as parameters. The same constraint
`005` and `006` carry, for the same reason.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__: list[str] = []
