"""Every bound comes from `D-26` — T101 (FR-013, FR-057; SC-027).

A limit, a window or a tolerance written into the code is a governed value this feature authored,
and the whole point of `D-26` is that it does not get to. So the transport-facing modules are
scanned for numeric literals, and the ones that survive are named and justified individually.

Three kinds of number are legitimate and are enumerated rather than waved through:

* **structural ceilings** in `inbound/parse.py`, which exist to stop an unauthenticated payload from
  costing anything before verification. They are deliberately *not* `D-26` values: the sender is
  unauthenticated at that point, so no governed policy has been resolved yet, and the refusal names
  no number (`FR-013`).
* **protocol constants** — an HMAC digest length, a version tag — which describe a provider's wire
  format rather than a policy.
* **indices and small structural integers** — ``0``, ``1``, ``2`` — which are arithmetic on
  positions,
  not thresholds.

Anything else fails, and the failure message names the file and the value.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from channel_integration.delivery import attempt, rate_limit, retry
from channel_integration.governance import bounds as bounds_module
from channel_integration.idempotency import window as window_module
from channel_integration.inbound import parse, verify
from channel_integration.outbound import continuation

pytestmark = pytest.mark.contract

#: Modules that make transport decisions. Scanned strictly.
_TRANSPORT_MODULES = (attempt, retry, rate_limit, window_module, verify, continuation)

#: Values a structural or protocol constant may legitimately be, with the reason each is permitted.
_PERMITTED_LITERALS = {
    0: "an index, a count or an empty size",
    1: "an index, a first attempt or a single-item bound",
    2: "a pair, or a two-element structural split",
    60: "seconds in a minute — a unit conversion, not a policy",
    64: "the hexadecimal length of a SHA-256 digest — a protocol fact",
}


def _numeric_literals(module: object) -> list[tuple[str, float]]:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")  # type: ignore[arg-type]
    tree = ast.parse(source)
    found: list[tuple[str, float]] = []
    name = Path(inspect.getfile(module)).name  # type: ignore[arg-type]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            if isinstance(node.value, bool):
                continue
            found.append((name, node.value))
    return found


@pytest.mark.parametrize("module", _TRANSPORT_MODULES, ids=lambda m: Path(inspect.getfile(m)).stem)
def test_no_transport_module_hardcodes_a_limit_window_or_tolerance(module: object) -> None:
    """`SC-027`: every threshold is resolved, never written."""
    offenders = [
        f"{name}: {value}"
        for name, value in _numeric_literals(module)
        if value not in _PERMITTED_LITERALS
    ]
    assert not offenders, offenders


def test_the_structural_ceilings_live_only_in_the_parse_module() -> None:
    """They are permitted **there**, and named, because the sender is unauthenticated at that point.

    `D-26` cannot govern them: resolving a policy requires knowing which channel and which tenant,
    and neither is trustworthy before verification. So the ceilings are structural, they are
    declared as named constants rather than inline, and the refusal quotes no number.
    """
    text = Path(inspect.getfile(parse)).read_text(encoding="utf-8")
    for named in ("STRUCTURAL_MAX_BYTES", "STRUCTURAL_MAX_DEPTH", "STRUCTURAL_MAX_FIELDS"):
        assert named in text, f"{named} is not declared as a named constant"

    # And nowhere else declares one, so a second ceiling cannot appear quietly.
    root = Path(inspect.getfile(parse)).resolve().parents[1]
    for source in sorted(root.rglob("*.py")):
        if source == Path(inspect.getfile(parse)):
            continue
        body = source.read_text(encoding="utf-8")
        assert "STRUCTURAL_MAX" not in body, f"{source.name} declares a structural ceiling"


def test_the_bounds_object_carries_every_governed_value() -> None:
    """The seven `D-26` values, so a caller has no reason to reach for a literal."""
    declared = set(bounds_module.TransportBounds.model_fields)
    for required in (
        "replay_tolerance_seconds",
        "maximum_inbound_bytes",
        "timeout_seconds",
        "retry_attempts",
        "retry_backoff_seconds",
        "rate_limit_per_minute",
        "idempotency_window_seconds",
    ):
        assert required in declared, f"the bounds object omits {required}"


def test_the_bounds_object_is_unconstructible_from_governed_content_today() -> None:
    """`D-26` undeclared, so resolution refuses rather than returning defaults."""
    from channel_integration.contracts.descriptor import ChannelId
    from channel_integration.governance.resolve import ContentUnresolvable

    for channel in ChannelId:
        with pytest.raises(ContentUnresolvable):
            bounds_module.resolve_bounds(channel)
