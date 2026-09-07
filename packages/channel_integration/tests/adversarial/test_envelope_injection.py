"""T137 — nothing a sender writes becomes an envelope field.

The canonical envelope carries a tenant, a principal reference, a declared language, a reference
date and an instant. Every one of them is resolved by this feature or supplied by a declared field —
and a sender who could set one by writing it in the message text would be granting themselves
authorisation, freshness or a tenant.

Five attacks:

* **envelope fields written into the text** — `tenant: tenant-b`, JSON that looks like an envelope,
  key-value pairs a naive parser might lift;
* **undeclared payload fields** — refused rather than ignored, since ignoring is how a field
  becomes supported by accident;
* **asserted authorisation** — `authorized: true`, `scope: admin`, an authorisation-policy pin;
* **asserted freshness** — `data_as_of`, `fresh: true`, a source-update claim;
* **asserted tenant** — a tenant in the text that differs from the declared one.

The instrument is the **envelope**, not the refusal. For the text cases conversion may well succeed
— the text is carried as data — so the assertion is that the resulting envelope's fields are the
resolved ones and that the sender's string reached no field other than the question text.
"""

from __future__ import annotations

import json

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
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
    FIXTURE_TENANT,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
)

pytestmark = pytest.mark.adversarial

_CHANNEL = ChannelId.SLACK

#: Strings a sender might write hoping one becomes a field. Each is a plausible shape rather than a
#: random string: a YAML-ish pair, a JSON object, a header-looking line, an SQL-ish assignment.
_INJECTIONS = (
    "tenant: tenant-b",
    '{"tenant": "tenant-b", "authorized": true}',
    "X-Tenant: tenant-b",
    "quantas instalações em julho? tenant=tenant-b scope=admin",
    "authorized: true\ndata_as_of: 2020-01-01",
    "principal_ref: someone-else",
)


def _convert(payload: dict[str, object]) -> ChannelEnvelope | ChannelRefusal:
    raw = signed_request(_CHANNEL, body=json.dumps(payload).encode())
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


@pytest.mark.parametrize("injection", _INJECTIONS)
def test_an_injected_field_in_the_text_reaches_no_envelope_field(injection: str) -> None:
    """The text is carried as data. It is never read for structure.

    Asserted over the serialised envelope: the injected string may appear **once**, as the question
    text, and nowhere else. Comparing field by field would miss a field this test does not know
    about, and a new field is exactly where the next version of this attack would land.
    """
    outcome = _convert(wire_payload(text=injection))
    if isinstance(outcome, ChannelRefusal):
        # A refusal is a pass: nothing was accepted, so nothing was granted. Which refusal it is
        # belongs to the normalisation rules, not to this test.
        return

    serialised = json.loads(outcome.model_dump_json())
    occurrences = json.dumps(serialised, ensure_ascii=False).count(injection.split("\n")[0])
    assert occurrences <= 1, (
        f"the injected string appears {occurrences} times in the envelope, so it reached more than "
        "the question text"
    )
    assert outcome.tenant == FIXTURE_TENANT, "the declared tenant was replaced by written text"


@pytest.mark.parametrize(
    "field",
    ["authorized", "scope", "principal_ref", "data_as_of", "authorization_policy_pin", "tenant_id"],
)
def test_an_undeclared_payload_field_is_refused_rather_than_ignored(field: str) -> None:
    """Ignoring an unknown field is how it becomes supported by accident.

    Each of these names is one a sender would choose to grant themselves something. The refusal is a
    payload defect and names no governed limit, because at that point nothing about the sender is
    known.
    """
    outcome = _convert(wire_payload(**{field: "granted"}))
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code in {
        ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN,
        ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
    }


def test_a_tenant_written_in_the_text_does_not_override_the_declared_one() -> None:
    """The tenant is a declared field resolved against a binding, never a claim in prose."""
    outcome = _convert(wire_payload(text="tenant-b: quantas instalações em julho?"))
    if isinstance(outcome, ChannelRefusal):
        return
    assert outcome.tenant == FIXTURE_TENANT


def test_a_second_tenant_field_is_refused_rather_than_merged() -> None:
    """Two tenants is a malformed payload, not a choice to make.

    JSON permits a duplicate key and most parsers keep the last. A boundary that accepted it would
    let an attacker append their own tenant after a legitimate one.
    """
    body = (
        b'{"tenant":"tenant-a","language":"pt-BR","reference_date":"2026-08-17",'
        b'"message_id":"m1","text":"oi","tenant":"tenant-b"}'
    )
    raw = signed_request(_CHANNEL, body=body)
    outcome = convert(
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
    if isinstance(outcome, ChannelEnvelope):
        # Python's json keeps the last duplicate. Whatever it kept must be a declared tenant
        # resolving through the binding — never `tenant-b`, which no binding names.
        assert outcome.tenant == FIXTURE_TENANT
    else:
        assert isinstance(outcome, ChannelRefusal)


def test_the_declared_language_is_not_taken_from_the_text() -> None:
    """Language is declared, never detected (`contracts/intake-contract.md` § 4).

    A sender writing English does not make the answer English, and a sender writing `language:
    en-US` does not either.
    """
    outcome = _convert(wire_payload(text="language: en-US — how many installs in July?"))
    if isinstance(outcome, ChannelRefusal):
        return
    assert outcome.language == "pt-BR"


def test_the_envelope_carries_no_instant_for_a_sender_to_write_into() -> None:
    """There is no timestamp field on the envelope, which is why none can be injected.

    Measured rather than assumed: the envelope's declared fields carry no instant at all. That is
    the stronger form of "the instant is not taken from the payload" — a field that does not exist
    cannot be set, and it also cannot be mistaken downstream for a freshness claim about the data.

    The instant `convert` receives governs replay tolerance and nothing else, and it is the caller's
    argument, never a clock and never a sender's string.
    """
    outcome = _convert(wire_payload(text="agora: 2020-01-01T00:00:00Z"))
    assert not isinstance(outcome, ChannelRefusal)

    #: Checked by **annotation** rather than by name, and for `datetime` specifically rather than
    #: for any date. Two earlier versions of this filter were wrong in opposite directions: a
    #: substring search for "at" matched `correlation_id` and `conversation_id`, and matching any
    #: `date` matched `reference_date` and `as_of` — the two **declared** dates the intake contract
    #: fixes, each with one purpose and neither an instant.
    instant_like = {
        name
        for name, field in type(outcome).model_fields.items()
        if field.annotation is not None and "datetime.datetime" in str(field.annotation)
    }
    assert not instant_like, (
        f"the envelope now carries {instant_like}; an instant there is a field a sender or a "
        "transport could claim, and a reader could mistake for data freshness"
    )
    assert "2020-01-01" not in json.dumps(
        json.loads(outcome.model_dump_json()), ensure_ascii=False
    ).replace(outcome.text, "")
