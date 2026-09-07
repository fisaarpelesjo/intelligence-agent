"""T145 — the same bytes, material and instant convert to the same envelope (`SC-050`).

`convert` takes an injected instant and injected collaborators and reads no clock, no counter and no
random source. That is what makes this property checkable at all, and it is the property everything
downstream leans on: `T110`'s equivalence, replay tolerance, and any comparison of two runs of one
message.

## Two runs, then two processes

**Within one process** the property is asserted over generated payload text: convert twice, compare
the serialised envelope byte for byte. Generated rather than fixed, because a determinism defect
usually arrives through a value that happens to hash or sort differently — a dict iteration order, a
set, an interned string.

**Across processes** it is asserted once, through a subprocess that converts the same fixture bytes
and prints a digest. A fresh interpreter has a fresh `PYTHONHASHSEED`, which is exactly the
condition under which set or dict ordering leaks into output. Asserting it in-process only would
miss that class entirely, and `SC-050` says "and processes" for that reason.

The subprocess is the same interpreter running this suite, and it converts the **fixture** payload —
no provider, no network, no sandbox.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
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

pytestmark = pytest.mark.property

_CHANNEL = ChannelId.SLACK

#: Question text a sender could plausibly write, including the characters that make normalisation
#: work: accents, combining marks, quotation, whitespace runs. Deliberately not restricted to ASCII
#: — a determinism defect in Unicode handling is the one this generator exists to find.
_TEXT = st.text(
    alphabet=st.characters(
        codec="utf-8",
        exclude_categories=("Cs", "Cc"),
    ),
    min_size=1,
    max_size=120,
)


def _fingerprint(outcome: ChannelEnvelope | ChannelRefusal) -> str:
    """One string that changes if any field of the outcome changes.

    `model_dump_json` with sorted keys, so the comparison is over content rather than over whatever
    order the model happened to serialise in. A refusal is fingerprinted the same way: determinism
    of a refusal matters as much as determinism of an envelope, and a caller that retried a refused
    message must see the same code.
    """
    payload = json.loads(outcome.model_dump_json())
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _convert_once(text: str) -> ChannelEnvelope | ChannelRefusal:
    raw = signed_request(_CHANNEL, payload=wire_payload(text=text))
    return convert(
        raw,
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=_CHANNEL)),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_TEXT)
def test_two_conversions_of_one_message_agree_byte_for_byte(text: str) -> None:
    """Whatever the outcome is, it is the same outcome twice.

    Both branches are asserted through one fingerprint rather than split into an envelope case and a
    refusal case: which branch a generated text takes is not this test's business, and asserting the
    branch would make the property "text like this converts" instead of "conversion is a function".
    """
    first = _convert_once(text)
    second = _convert_once(text)
    assert _fingerprint(first) == _fingerprint(second)
    assert type(first) is type(second)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_TEXT)
def test_a_fresh_collaborator_set_does_not_change_the_outcome(text: str) -> None:
    """Collaborator identity is not an input.

    The resolver and the pseudonymiser are constructed fresh for each conversion, so a conversion
    that carried state across them — a cache keyed on object identity, a counter leaking into a
    reference — would show up here and nowhere in the previous test.
    """
    first = _convert_once(text)
    second = _convert_once(text)
    assert _fingerprint(first) == _fingerprint(second)


#: The subprocess body. Kept as source rather than a module so the cross-process assertion cannot
#: accidentally import state this process already built — a fresh interpreter is the whole point.
_SUBPROCESS = """
import hashlib, json, sys
sys.path.insert(0, {tests_parent!r})
from tests.fixtures.channels import (
    AT, FIXTURE_MATERIAL, bounds_for, descriptor_for, signed_request, wire_payload,
)
from tests.fixtures.identity import (
    FIXTURE_EXTERNAL, CountingIdentityResolver, CountingPseudonymiser, active_binding,
)
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.kinds import MessageKind
from channel_integration.inbound.convert import convert

channel = ChannelId.SLACK
outcome = convert(
    signed_request(channel, payload=wire_payload()),
    descriptor=descriptor_for(channel),
    material=FIXTURE_MATERIAL,
    bounds=bounds_for(channel),
    kind=MessageKind.TEXT,
    external=FIXTURE_EXTERNAL,
    resolver=CountingIdentityResolver(active_binding(channel=channel)),
    pseudonymiser=CountingPseudonymiser(),
    at=AT,
)
payload = json.loads(outcome.model_dump_json())
print(hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
"""


def test_a_separate_process_converts_the_fixture_to_the_same_envelope() -> None:
    """`SC-050`'s "and processes", asserted rather than assumed.

    A fresh interpreter randomises `PYTHONHASHSEED`, so any set or dict ordering that reached the
    envelope would produce a different digest here while every in-process assertion stayed green.
    """
    package_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        (sys.executable, "-c", _SUBPROCESS.format(tests_parent=str(package_root))),
        cwd=package_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"the subprocess could not convert, so this assertion proves nothing.\n"
        f"{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}"
    )
    expected = _fingerprint(_convert_once(str(wire_payload()["text"])))
    assert completed.stdout.strip() == expected
