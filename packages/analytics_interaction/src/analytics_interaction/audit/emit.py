"""Synchronous, fail-closed emission — T137 (FR-054; SC-025, SC-046).

**No answer is released until its `RELEASE` event is durably accepted.**

That is the load-bearing rule, inherited verbatim from `002`: releasing a value
whose derivation could not be recorded produces exactly the state the audit
contract exists to prevent — an answer in the world with no trace of who asked
for it or which definitions produced it.

Emission is synchronous at **every** stage. A stage is not complete until its
sink call returns successfully. There is no fire-and-forget path, no best-effort
mode, and no buffered emission that could outlive the request.

## What a sink failure withholds, stage by stage

| Stage | Behaviour |
|---|---|
| `INTAKE`, `INTERPRETATION` | nothing has been submitted; refuse, and no port call occurs |
| `CLARIFICATION` | no contract is issued; one nobody could record is not silently issued |
| `REFUSAL` | the refusal **still stands**, and the emission failure is itself raised |
| `SUBMISSION` | the request does not cross the port |
| `RELEASE` | **the answer is withheld** — the caller receives the audit failure, not a result |

The `REFUSAL` row is the one worth reading twice. A refusal is the safe outcome,
so a failure to record it does not turn into an answer; but it is still raised,
because a refusal nobody recorded is a governance event that left no trace.

## No retry, no buffer, no queue, no downgrade

All four are the same mistake wearing different clothes: each converts "this was
not recorded" into "this will probably be recorded", and the caller receives an
answer either way. A retry loop also turns a failing sink into an unbounded wait
on the request path.

So :func:`emit` calls once and raises. `T141`'s scan asserts there is no queue,
no scheduler, no durable store and no retry decorator anywhere in the package.

## Refusal auditing terminates

Emitting a `REFUSAL` can itself fail. That failure is raised as an audit failure
and is **never** re-audited — a second `REFUSAL` event describing the first one's
emission failure would fail the same way, and the loop is unbounded. `T143`
asserts termination by counting sink calls on a sink that always raises.

## No clock

Event instants are supplied where a contract requires them. Nothing here reads
``now()``: two identical flows must produce equivalent ordered sequences, and a
timestamp read inside emission would make every event unequal to every other.

## What this feature does not own

Durable storage, retention, indexing and access are `EXT-B` / `001:T110`'s. This
module emits and refuses to define the transport — a feature that emits an event
it cannot archive is honest about the gap; one that invents an archive claims a
readiness nobody approved.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from analytics_query.contracts.reason_codes import AnalyticsReasonCode

from ..contracts.audit import InterpretationStage

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

    from ..contracts.audit import InterpretationAuditEvent

__all__ = [
    "WITHHOLDING",
    "AuditEmissionFailed",
    "InterpretationAuditSink",
    "emit",
    "emit_sequence",
]

#: What a failure at each stage withholds. Data rather than prose, so a caller
#: can act on it and `T143` can assert the whole matrix rather than a sample.
#:
#: Every entry is a withholding. There is no stage whose audit failure is
#: survivable, because "recorded" is a precondition everywhere — the stages
#: differ only in *what* goes unreleased.
_WITHHOLDING: dict[InterpretationStage, str] = {
    InterpretationStage.INTAKE: "no request is submitted",
    InterpretationStage.INTERPRETATION: "no request is submitted",
    InterpretationStage.CLARIFICATION: "no clarification contract is issued",
    InterpretationStage.REFUSAL: "the refusal stands and the failure is raised",
    InterpretationStage.SUBMISSION: "the request does not cross the execution port",
    InterpretationStage.RELEASE: "the answer is withheld",
}

#: Read-only. A mutable module-level mapping is a store nobody called a store,
#: and this one is consulted on every failure path — a caller that could edit it
#: could edit what a stage withholds.
WITHHOLDING: Mapping[InterpretationStage, str] = MappingProxyType(_WITHHOLDING)


@runtime_checkable
class InterpretationAuditSink(Protocol):
    """Durable acceptance, or an exception. **There is no third answer.**

    Shaped exactly as `001`'s sink protocol and for the same reason: a sink that
    returned a status code would invite a caller to inspect it and continue, and
    raising is what makes "durably accepted" the only way past this line.

    A sink returning anything at all is treated as malformed by :func:`emit` — a
    return value is a channel through which a caller could be told "accepted,
    sort of", and there is no such state.
    """

    def accept(self, event: InterpretationAuditEvent) -> None:
        """Persist the event durably. Raises if it could not."""
        ...


class AuditEmissionFailed(Exception):  # noqa: N818 - a governed refusal, not an error
    """The event could not be durably accepted, so what it guarded is withheld.

    Carries `002`'s ``AUDIT_EMISSION_FAILED`` rather than a code of this
    feature's own. The governed fact is identical — an audit sink did not accept
    an event — and inventing a thirty-third interpretation code to describe it
    would be this feature naming an implementation condition as a governance one.

    ``withheld`` states the consequence in the same object that reports the
    failure, so a caller cannot handle the exception without seeing what did not
    happen.
    """

    def __init__(self, stage: InterpretationStage, detail: str) -> None:
        self.code = AnalyticsReasonCode.AUDIT_EMISSION_FAILED
        self.stage = stage
        self.detail = detail
        self.withheld = WITHHOLDING[stage]
        super().__init__(f"{self.code.value} at {stage.value}: {self.withheld}")


def emit(sink: InterpretationAuditSink | None, event: InterpretationAuditEvent) -> None:
    """Emit one event synchronously, or refuse whatever it guarded.

    **One call.** No retry, no fallback sink, no buffer, no queue. A second
    attempt would convert "not recorded" into "probably recorded", and the caller
    would receive an answer either way.

    Three ways to fail, and all three are the same governed fact:

    * **absent sink** — a missing collaborator is a refusal, never a bypass. A
      default no-op sink would make every fail-closed guarantee in this module
      vacuous, and nothing would look wrong;
    * **the sink raised** — deliberately broad. A sink can fail in ways this
      package cannot enumerate, and every one of them means the event was not
      durably accepted. Narrowing this would let an unanticipated failure
      propagate as something other than a withholding;
    * **the sink returned a value** — the protocol returns ``None``. Anything
      else is a malformed acknowledgement, and treating it as success would let a
      sink that answered "queued" pass as one that answered "stored".
    """
    if sink is None:
        raise AuditEmissionFailed(event.stage, "no audit sink was supplied")

    try:
        acknowledgement = sink.accept(event)
    except AuditEmissionFailed:
        # Already a governed audit failure — re-raising it unchanged keeps one
        # stage's failure from being reported as another's.
        raise
    except Exception as exc:
        raise AuditEmissionFailed(event.stage, "the audit sink did not accept the event") from exc

    if acknowledgement is not None:
        raise AuditEmissionFailed(
            event.stage, "the audit sink returned a malformed acknowledgement"
        )


def emit_sequence(
    sink: InterpretationAuditSink | None, events: tuple[InterpretationAuditEvent, ...]
) -> None:
    """Emit an ordered sequence, stopping at the first failure.

    Stopping is the point. Continuing past a failed stage would produce a trail
    in which a later event implies an earlier one that was never recorded — and a
    reader reconstructing the chain would infer a step that did not happen.

    Nothing is emitted concurrently and nothing is reordered: the sequence is the
    order the sequence occurred in, and an audit trail that reordered itself
    would be evidence of an ordering the code never performed.
    """
    for event in events:
        emit(sink, event)
