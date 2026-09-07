"""A fake execution port — T147. **TEST-ONLY.**

Stands where `002`'s ADR 0010 entry point would, so the submission path can be
exercised without a warehouse. `D-12` gates the real one, and every governed
request in this repository refuses long before reaching it.

The port here **counts** rather than answers. That is deliberate: almost every
claim this feature makes about execution is a claim about *how many times* the
boundary was crossed — one call per side, zero on a refusal, none speculative —
and a fixture that returned a plausible answer would make the counts the
incidental part.

A fixture is never evidence for an external record. Nothing here reaches a
warehouse, an adapter, a ledger or a credential, and `test_fixture_containment`
asserts no `src/` module can reach it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from analytics_query.contracts.request import AnalyticsQuery
    from analytics_query.execute import ExecutedAnswer

    from analytics_interaction.authorization.context_preflight import AuthorizedContext

__all__ = ["FIXTURE_MARKER", "CountingPort", "RefusingPort"]

#: Carried by every synthetic value here, and asserted absent from `src/`.
FIXTURE_MARKER = "fixture-only-no-warehouse"


@dataclass
class CountingPort:
    """An ``ExecutionPort`` that records submissions and answers nothing.

    Fail-loud on use rather than on construction: a port that raised when built
    could never demonstrate that it *would* have been called, and a zero-call
    assertion against something uncallable proves nothing.
    """

    submissions: list[AnalyticsQuery] = field(default_factory=list["AnalyticsQuery"])

    def submit(
        self,
        request: AnalyticsQuery,
        *,
        authorized: AuthorizedContext,
        auth_fingerprint: str,
        correlation_id: str,
    ) -> ExecutedAnswer:
        del authorized, auth_fingerprint, correlation_id
        self.submissions.append(request)
        raise AssertionError(f"{FIXTURE_MARKER}: this port reaches no warehouse")

    @property
    def count(self) -> int:
        return len(self.submissions)


@dataclass
class RefusingPort:
    """A port that refuses every submission, counting the attempts.

    Distinct from :class:`CountingPort` in what it models: this one is a
    *governed* refusal arriving from `002`, not a fixture declining to pretend.
    A suite asserting "the refusal propagates unchanged" needs the first; one
    asserting "nothing was reached" needs the second.
    """

    attempts: list[str] = field(default_factory=list[str])

    def submit(
        self,
        request: AnalyticsQuery,
        *,
        authorized: AuthorizedContext,
        auth_fingerprint: str,
        correlation_id: str,
    ) -> ExecutedAnswer:
        del request, authorized, auth_fingerprint
        self.attempts.append(correlation_id)
        raise AssertionError(f"{FIXTURE_MARKER}: the governed request was refused upstream")

    @property
    def count(self) -> int:
        return len(self.attempts)
