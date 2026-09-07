"""Constant-time comparison — T053 (FR-011; SC-004).

Two instruments, and the difference between what each can prove is stated rather than blurred.

* **Static, and this is the load-bearing half.** Every comparison of secret-derived bytes in the
  verification path goes through :func:`hmac.compare_digest`. No ``==``, ``!=``, ``in``,
  ``startswith`` or ``sorted`` over a digest, a token or key material. This is decidable by
  reading the source, so it is asserted by reading the source.
* **Measured, and deliberately weak.** A timing measurement on a shared CI runner cannot prove
  constant time — the noise floor is larger than the signal it would look for. What the
  measurement here *can* show is the absence of a **gross** asymmetry: a scheme that returned
  early on the first differing byte of a 64-character digest, or that hashed only on the success
  path. It is written as an order-of-magnitude bound, not a tight one, because a tight bound on a
  noisy instrument is a flaky test pretending to be a proof.

The honest claim: constant-time comparison is guaranteed by `hmac.compare_digest`, asserted
statically; the timing test is a smoke alarm for a refactor that stops using it in a way the
static scan somehow misses.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.inbound.schemes import VerificationMaterial
from channel_integration.inbound.verify import SCHEMES

from ..fixtures.channels import FIXTURE_MATERIAL, descriptor_for, signed_request

pytestmark = pytest.mark.security

_SCHEME_ROOT = Path(__file__).resolve().parents[2] / "src" / "channel_integration" / "inbound"

#: A comparison of two secret-derived values written with an operator instead of the constant-time
#: primitive. Matches the operator applied to any name containing a digest-ish word.
_UNSAFE_COMPARISON = re.compile(
    r"(?:signature|digest|token|secret|material|hmac|expected|presented)\w*\s*(?:==|!=)\s*\w"
    r"|\w+\s*(?:==|!=)\s*\w*(?:signature|digest|token|secret|material|hmac)\w*",
    re.IGNORECASE,
)


def _scheme_sources() -> list[Path]:
    return [*sorted((_SCHEME_ROOT / "schemes").rglob("*.py")), _SCHEME_ROOT / "verify.py"]


def test_every_scheme_module_uses_the_constant_time_primitive() -> None:
    """`FR-011`, statically: the comparison lives in one place and that place is `hmac`."""
    hmac_module = _SCHEME_ROOT / "schemes" / "_hmac.py"
    text = hmac_module.read_text(encoding="utf-8")
    assert "hmac.compare_digest" in text, "the shared comparison is not constant-time"

    for source in _scheme_sources():
        body = source.read_text(encoding="utf-8")
        if "compare_digest" in body:
            continue
        # A scheme that does not compare directly must delegate to the shared helper.
        assert "_hmac" in body or "verify_hexdigest" in body or "schemes" in body, (
            f"{source.name} neither compares constant-time nor delegates"
        )


def test_no_module_in_the_verification_path_compares_secrets_with_an_operator() -> None:
    """The failure mode this closes: a refactor that "simplifies" a digest check to `==`."""
    offenders: list[str] = []
    for source in _scheme_sources():
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            if "compare_digest" in code:
                continue
            if _UNSAFE_COMPARISON.search(code):
                offenders.append(f"{source.name}:{number}: {line.strip()}")
    assert not offenders, offenders


#: Ordering or prefix-matching **secret-derived** material. A version tag such as Slack's
#: ``v0=`` is public and is deliberately not covered: forbidding it would make the test assert a
#: style rule instead of the security property.
_ORDERED_SECRET = re.compile(
    r"(?:material\.\w+|\w*(?:digest|token|secret)\w*)\s*\.\s*(?:startswith|endswith)\("
    r"|(?:sorted|min|max)\(\s*(?:material\.|\w*(?:digest|token|secret))",
    re.IGNORECASE,
)


def test_no_scheme_orders_or_prefix_matches_secret_derived_material() -> None:
    """A prefix comparison over a digest leaks as surely as an early-exit compare.

    Slack's ``v0=`` version check is intentionally out of scope: the tag is public, carries no
    secret, and refusing it would be a style assertion dressed as a security one.
    """
    offenders: list[str] = []
    for source in _scheme_sources():
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            if _ORDERED_SECRET.search(code):
                offenders.append(f"{source.name}:{number}: {line.strip()}")
    assert not offenders, offenders


def _elapsed(scheme_name: str, body: bytes, headers: tuple[tuple[str, str], ...]) -> float:
    """Median wall time of one verification, over enough repeats to damp scheduler noise."""
    scheme = SCHEMES[scheme_name]
    samples: list[float] = []
    for _ in range(200):
        start = time.perf_counter()
        scheme.verify(body, headers, FIXTURE_MATERIAL)
        samples.append(time.perf_counter() - start)
    samples.sort()
    return samples[len(samples) // 2]


def test_a_first_byte_mismatch_is_not_faster_than_a_last_byte_mismatch() -> None:
    """The gross-asymmetry alarm. An order-of-magnitude bound, on purpose.

    An early-exit comparison would return after one byte for the first case and after sixty-three
    for the second, so a leaking implementation shows a large ratio. A constant-time one shows a
    ratio dominated by noise, which is why the bound is loose.
    """
    raw = signed_request(ChannelId.WHATSAPP)
    scheme_name = descriptor_for(ChannelId.WHATSAPP).verification_scheme
    presented = dict(raw.headers)["x-hub-signature-256"].removeprefix("sha256=")

    first_differs = "0" * 64 if presented[0] != "0" else "1" + presented[1:]
    last_differs = presented[:-1] + ("0" if presented[-1] != "0" else "1")

    def with_signature(value: str) -> tuple[tuple[str, str], ...]:
        return tuple(
            (name, "sha256=" + value if name == "x-hub-signature-256" else header)
            for name, header in raw.headers
        )

    early = _elapsed(scheme_name, raw.body, with_signature(first_differs))
    late = _elapsed(scheme_name, raw.body, with_signature(last_differs))
    ratio = max(early, late) / max(min(early, late), 1e-9)
    assert ratio < 10.0, f"gross timing asymmetry between mismatch positions: ratio {ratio:.1f}"


def test_a_failing_verification_does_the_same_work_as_a_succeeding_one() -> None:
    """A scheme that skipped the HMAC on the failure path would be trivially distinguishable."""
    raw = signed_request(ChannelId.SLACK)
    scheme_name = descriptor_for(ChannelId.SLACK).verification_scheme
    wrong = tuple(
        (name, "v0=" + "0" * 64 if name == "x-slack-signature" else value)
        for name, value in raw.headers
    )
    ok = _elapsed(scheme_name, raw.body, raw.headers)
    bad = _elapsed(scheme_name, raw.body, wrong)
    ratio = max(ok, bad) / max(min(ok, bad), 1e-9)
    assert ratio < 10.0, f"success and failure paths do different amounts of work: {ratio:.1f}"


def test_retired_material_is_checked_with_the_same_primitive() -> None:
    """Rotation must not introduce a second, weaker comparison (`FR-074`)."""
    retired = "fixture-retired-key"
    material = VerificationMaterial(active="fixture-new-key", retired=(retired,))
    raw = signed_request(
        ChannelId.WHATSAPP, material=VerificationMaterial(active=retired, retired=())
    )
    outcome = SCHEMES[descriptor_for(ChannelId.WHATSAPP).verification_scheme].verify(
        raw.body, raw.headers, material
    )
    assert not outcome.ok, "a signature under withdrawn material must not verify"
    text = (_SCHEME_ROOT / "schemes" / "_hmac.py").read_text(encoding="utf-8")
    assert text.count("compare_digest") >= 1
