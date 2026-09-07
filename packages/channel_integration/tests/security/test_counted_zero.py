"""Counted zero before authentication — T052 (FR-023 to FR-025; SC-002).

**The property this feature exists for, and it is measured rather than inspected.**

A failure at any step before submission must cause **zero** work downstream. Two kinds of zero are
asserted here, and the difference between them is stated rather than blurred:

* **Measured, by counter.** The identity resolver and the pseudonymisation port are injected and
  count their calls. A failure at steps 1 to 6 must leave both at zero — no registry read, no
  reference derived. These are the only cost surfaces Phase B can reach at all, and a counter is
  the honest instrument for them.
* **Structural, by absence.** The interaction port, the catalog, a model surface and the execution
  boundary cannot be reached from Phase B because **no path to them exists**: `convert` has no
  parameter for one and no module under `inbound` or `identity` imports one. Asserted by import
  scan and by signature inspection, because there is nothing to count when nothing can be called.

Phase D's `T119` turns the structural half into an enumerated allowlist gate once the port exists.
Until then, claiming a counted zero against a port nobody can call would be theatre.
"""

from __future__ import annotations

import inspect
import re
from datetime import timedelta
from pathlib import Path

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.inbound.convert import convert

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    bounds_for,
    descriptor_for,
    signed_request,
    wire_payload,
)
from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
)

pytestmark = pytest.mark.security

_CHANNEL = ChannelId.SLACK

#: Every failing case, and the step it must fail at. Named so a failure reports which boundary
#: leaked rather than "something called something".
_FAILING_CASES: dict[str, dict[str, object]] = {
    "structural: body is not JSON": {"body": b"not json at all"},
    "structural: over the ceiling": {"body": b'{"x":"' + b"a" * 70000 + b'"}'},
    "authenticity: signature absent": {"strip_signature": True},
    "authenticity: body altered after signing": {"tamper": True},
    "replay: timestamp outside tolerance": {"late": True},
    "kind: not a textual question": {"kind": MessageKind.AUDIO},
    "envelope: undeclared field": {"payload": wire_payload(access_tags=["admin"])},
    "text: unusable": {"payload": wire_payload(text="   ")},
    "normalisation: ambiguous": {"payload": wire_payload(text="quantas @bot instalações?")},
}


def _drive(case: dict[str, object]) -> tuple[ChannelRefusal, int, int]:
    """Run one failing case and return the refusal with both counters."""
    payload = case.get("payload") or wire_payload()
    raw = signed_request(_CHANNEL, payload=payload, body=case.get("body"))  # type: ignore[arg-type]

    if case.get("strip_signature"):
        raw = raw.model_copy(
            update={
                "headers": tuple(
                    (name, value) for name, value in raw.headers if "signature" not in name.lower()
                )
            }
        )
    if case.get("tamper"):
        raw = raw.model_copy(update={"body": raw.body.replace(b"julho", b"agosto")})

    bounds = bounds_for(_CHANNEL)
    at = AT + timedelta(seconds=bounds.replay_tolerance_seconds + 1) if case.get("late") else AT

    resolver = CountingIdentityResolver(active_binding())
    pseudonymiser = CountingPseudonymiser()
    outcome = convert(
        raw,
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds,
        kind=case.get("kind", MessageKind.TEXT),  # type: ignore[arg-type]
        external=FIXTURE_EXTERNAL,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=at,
    )
    assert isinstance(outcome, ChannelRefusal), "the case was expected to refuse"
    return outcome, resolver.calls, pseudonymiser.calls


@pytest.mark.parametrize("name", sorted(_FAILING_CASES))
def test_a_failure_before_identity_costs_nothing(name: str) -> None:
    """Measured: zero registry reads, zero derivations, for every pre-step-7 failure."""
    refusal, resolver_calls, pseudonymiser_calls = _drive(_FAILING_CASES[name])
    assert resolver_calls == 0, f"{name}: the registry was consulted {resolver_calls} times"
    assert pseudonymiser_calls == 0, f"{name}: {pseudonymiser_calls} references were derived"
    assert refusal.code is not ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED


def test_the_happy_path_does_consult_both_surfaces() -> None:
    """Without this, every zero above could be a function that does nothing at all."""
    resolver = CountingIdentityResolver(active_binding())
    pseudonymiser = CountingPseudonymiser()
    outcome = convert(
        signed_request(_CHANNEL),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=AT,
    )
    assert not isinstance(outcome, ChannelRefusal), "the fixture path must reach an envelope"
    assert resolver.calls == 1
    assert pseudonymiser.calls == 2, "one conversation reference, one correlation id"


def test_conversion_has_no_parameter_through_which_a_port_could_arrive() -> None:
    """Structural: the interaction port cannot be called because it cannot be passed."""
    parameters = set(inspect.signature(convert).parameters)
    assert parameters == {
        "raw",
        "descriptor",
        "material",
        "bounds",
        "kind",
        "external",
        "resolver",
        "pseudonymiser",
        "at",
    }
    for forbidden in ("port", "interaction", "catalog", "model", "execution", "sink", "client"):
        assert not any(forbidden in name for name in parameters), (
            f"convert accepts a {forbidden}-shaped collaborator"
        )


def test_no_phase_b_module_imports_a_downstream_surface() -> None:
    """Structural: no path exists from the inbound boundary to interpretation or execution."""
    root = Path(__file__).resolve().parents[2] / "src" / "channel_integration"
    forbidden = re.compile(
        r"^\s*(?:from|import)\s+(analytics_interaction\.(?!contracts\.reason_codes)"
        r"|analytics_query\.(?!contracts\.reason_codes)"
        r"|semantic_catalog\.(?!contracts\.reason_codes))"
    )
    offenders: list[str] = []
    for module in sorted((root / "inbound").rglob("*.py")) + sorted(
        (root / "identity").rglob("*.py")
    ):
        for line in module.read_text(encoding="utf-8").splitlines():
            if forbidden.match(line):
                offenders.append(f"{module.name}: {line.strip()}")
    assert not offenders, offenders
