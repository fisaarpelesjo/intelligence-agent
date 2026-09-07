"""The interaction double — T121 (`FR-072`, `SC-034`). **TEST-ONLY.**

`contracts/interaction-port.md` §2 says it plainly: until Phase D0 ships the composed entry point
and its validation passes, no implementation of the port is constructible, "the port type exists so
the rest of `004` can be written and tested against a fixture double, production has none".

This is that double. It is reachable from `tests/` alone — **no flag, environment setting or
deployment mode selects it**, because nothing in `src/` can name it. That is not a convention here,
it is enforced: `tests/contract/test_fixture_containment.py` collects every top-level `def`, `class`
and `^FIXTURE_*` name in this directory and greps each one across every `src/**/*.py`, docstrings
included. A name declared here that appears anywhere in `src` fails that gate.

Which is why nothing below is called `InteractionPort`, `ask`, `submit` or `intake_from_envelope`.
Those are the real names and they live in `src`; a double that shared one would take the production
module down with it.

## What the double records, and why recording is the point

`T134` asserts "one `ask` per inbound message, zero after a refusal". That is a **count**, and a
double that only returned an outcome could not answer it. So `RecordingInteraction` keeps every
intake it was handed, in order, and the count is a property of the list rather than a separate
counter that could drift from it.

The intakes are kept whole rather than summarised. `T124` and `T127` need to assert *what* was
submitted — that a refused message submitted nothing, that a crossed conversation never reached the
port — and a stored count cannot answer either.

## The double decides nothing

It returns what it was constructed with. It does not inspect the intake, branch on it, or synthesise
an outcome from it: a double that chose its answer would be a second interpretation path, and the
tests built on it would be measuring the double rather than the boundary.

`refusing_interaction` is the one convenience, and it still decides nothing — it is constructed with
a refusal and returns it, exactly like the answering form.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analytics_interaction.contracts.intake import QuestionIntake

from channel_integration.interaction import InteractionPort

__all__ = [
    "FIXTURE_INTERACTION_OUTCOME",
    "RecordingInteraction",
    "recording_interaction",
    "refusing_interaction",
]

#: The outcome the plain double returns when a test does not care which one it is. A sentinel object
#: rather than a synthetic `AnalyticsAnswer`: a test asserting *that* the port was reached should
#: not also have to construct an answer, and one asserting *what* came back passes its own.
FIXTURE_INTERACTION_OUTCOME = object()


@dataclass
class RecordingInteraction:
    """An `InteractionPort` that records every intake and returns a fixed outcome.

    ``outcome`` is returned unchanged on every call. ``intakes`` is the whole record, in call order,
    so a test can assert the count, the content, or that the list is empty — which is the assertion
    a refusal path needs.
    """

    outcome: object = FIXTURE_INTERACTION_OUTCOME
    intakes: list[QuestionIntake] = field(default_factory=list[QuestionIntake])

    def ask(self, intake: QuestionIntake) -> object:
        """Record and return. No branch, no inspection, no synthesis."""
        self.intakes.append(intake)
        return self.outcome

    @property
    def calls(self) -> int:
        """How many times the port was reached. Derived from the record, never counted separately.

        A separate counter could disagree with the list it is supposed to describe, and the two
        disagreeing is exactly the bug a zero-call assertion is meant to catch.
        """
        return len(self.intakes)


def recording_interaction(outcome: object = FIXTURE_INTERACTION_OUTCOME) -> RecordingInteraction:
    """A double that answers with ``outcome``. **TEST-ONLY.**"""
    return RecordingInteraction(outcome=outcome)


def refusing_interaction(refusal: object) -> RecordingInteraction:
    """A double that returns an upstream refusal as an **outcome**, not as a raise.

    Separate from `recording_interaction` only for what it says at the call site: `003`'s port
    returns a refusal rather than raising it, and a test reading `refusing_interaction(...)` is
    stating which of the three outcome members it is exercising.
    """
    return RecordingInteraction(outcome=refusal)


#: Static conformance, checked at import rather than asserted in a test: if the double stops
#: satisfying the port, every module importing this one fails immediately and says so, instead of
#: one test somewhere reporting a shape mismatch.
_DOUBLE_SATISFIES_THE_PORT: InteractionPort = RecordingInteraction()
