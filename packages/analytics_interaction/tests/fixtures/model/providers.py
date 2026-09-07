"""Synthetic model ports and readiness — Phase 7 fixtures.

TEST-ONLY, and the marking matters more here than anywhere else in this suite.

**No provider is contacted.** Every port below is a local object that returns a
value or raises. There is no SDK, no HTTP client, no endpoint, no model name, no
token or cost limit and no credential — the tests exercise the *port contract*,
never a provider.

**The synthetic readiness record is not the repository's.** `D-20` is
``UNDECLARED`` in `docs/readiness/nl-analytics-external-readiness.yaml` and stays
that way; ``synthetic_ready_records`` builds an in-memory record so the tests can
reach the code path behind the gate. Nothing here is written to disk, and none of
it is evidence for `D-20`.

Every port counts its invocations, because the zero-call assertions need a
collaborator that *would* have registered a call rather than one that could not
be called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analytics_interaction.compliance.readiness import Capability, ReadinessRecord
from analytics_interaction.interpretation.model_port import (
    CandidateSelection,
    CandidateSet,
    DelimitedQuestionData,
)

__all__ = [
    "CountingPort",
    "ExplodingPort",
    "MalformedPort",
    "SelectingPort",
    "SilentPort",
    "synthetic_ready_records",
    "synthetic_unready_records",
]


def synthetic_ready_records(capability: str = "d_20") -> tuple[ReadinessRecord, ...]:
    """TEST-ONLY in-memory record declaring ``capability`` ready **with evidence**.

    Never persisted, never `D-20` evidence. Exists so the tests can reach the
    narrowing path at all — without it the gate refuses first and the validation
    logic would be unreachable and therefore untested.
    """
    return (
        ReadinessRecord(
            "fixture-feature",
            "FIXTURE-ONLY",
            {capability: Capability(capability, True, "FIXTURE-ONLY", "fixture-owner")},
        ),
    )


def synthetic_unready_records(
    capability: str = "d_20", *, declared: bool = False, evidence: str | None = None
) -> tuple[ReadinessRecord, ...]:
    """TEST-ONLY record in a state that must **not** unlock.

    Defaults to undeclared; ``declared=True, evidence=None`` models the
    declared-without-evidence case, which is a governance failure rather than a
    permission.
    """
    return (
        ReadinessRecord(
            "fixture-feature",
            "FIXTURE-ONLY",
            {capability: Capability(capability, declared, evidence, "fixture-owner")},
        ),
    )


@dataclass
class CountingPort:
    """Base behaviour: record every call, then defer to a subclass.

    ``calls`` is what the zero-call assertions read. ``seen`` records the
    requests, so a test can assert *what* crossed the boundary and not merely
    that something did.
    """

    calls: int = 0
    seen: list[tuple[DelimitedQuestionData, CandidateSet]] = field(
        default_factory=list[tuple[DelimitedQuestionData, CandidateSet]]
    )

    def narrow(
        self, question: DelimitedQuestionData, candidates: CandidateSet
    ) -> CandidateSelection | None:
        self.calls += 1
        self.seen.append((question, candidates))
        return None


@dataclass
class SelectingPort(CountingPort):
    """Returns a fixed identifier — valid or foreign, as the test requires."""

    identifier: str = "installs"

    def narrow(
        self, question: DelimitedQuestionData, candidates: CandidateSet
    ) -> CandidateSelection | None:
        super().narrow(question, candidates)
        return CandidateSelection(identifier=self.identifier)


@dataclass
class SilentPort(CountingPort):
    """Declines to choose. A complete, permitted answer."""


@dataclass
class ExplodingPort(CountingPort):
    """Fails the way a real provider fails: timeout, transport, quota, bug."""

    error: BaseException = field(default_factory=lambda: TimeoutError("provider timed out"))

    def narrow(
        self, question: DelimitedQuestionData, candidates: CandidateSet
    ) -> CandidateSelection | None:
        super().narrow(question, candidates)
        raise self.error


@dataclass
class MalformedPort(CountingPort):
    """Returns something that is not a selection at all.

    A dict, a string, a number, a list of guesses with confidence scores — the
    shapes a provider actually emits when nobody constrained it.
    """

    answer: Any = None

    def narrow(
        self, question: DelimitedQuestionData, candidates: CandidateSet
    ) -> CandidateSelection | None:
        super().narrow(question, candidates)
        return self.answer  # type: ignore[no-any-return]
