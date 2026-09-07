"""A transport asserts nothing — T055 (FR-107; SC-061).

The threat this closes is the ordinary shape of a channel integration bug: an adapter that has
already checked the signature, sets ``verified=True``, and the core believes it. From then on the
security of the whole feature is the security of whoever can reach that field.

So the rule is that **there is no such field**, anywhere on the inbound path, for any of the facts
a transport might try to assert:

* authenticity — ``verified``, ``authenticated``, ``signature_ok``, ``trusted``;
* identity — ``principal``, ``user_id``, ``authorised_as`` on the wire;
* tenant, language and dates as *decided* values rather than declared ones;
* authorisation — ``allowed``, ``permissions``, ``scopes``, ``access_tags``;
* limits — ``max_rows``, ``max_bytes``, ``timeout``, ``rate_limit`` presented by a caller.

Asserted three ways, because one way is defeatable:

1. **By field set.** The canonical contracts and the wire shape declare no such name, and both are
   closed to extras, so the value cannot arrive.
2. **By signature.** `convert` has no parameter through which a caller says "already verified", so
   the claim cannot arrive out-of-band either.
3. **By behaviour.** A payload that *tries* to declare one refuses, and a request carrying such a
   header is verified exactly as if it had not.

The tenant is the interesting case and it is stated rather than glossed: the wire **does** declare
a tenant, because a caller must say which tenant it believes it is acting for. That declaration is
never trusted — `identity.tenant` compares it against the resolved binding and a disagreement
refuses. Declaring is not deciding.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from channel_integration.contracts.audit import ChannelAuditEvent
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.raw import RawChannelRequest
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.inbound.convert import convert
from channel_integration.inbound.envelope import WIRE_FIELDS
from channel_integration.inbound.verify import verify_authenticity

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

pytestmark = pytest.mark.contract

_SRC = Path(__file__).resolve().parents[2] / "src" / "channel_integration"
_CHANNEL = ChannelId.SLACK

#: Names through which a transport would assert a fact it is not entitled to assert. Grouped by
#: the fact, so a failure says *which* authority leaked rather than "a forbidden name appeared".
_ASSERTED_AUTHORITY: dict[str, tuple[str, ...]] = {
    "authenticity": ("verified", "authenticated", "signature_ok", "signature_valid", "trusted"),
    "identity": ("principal", "user_id", "actor", "authorised_as", "authorized_as", "on_behalf_of"),
    "authorisation": ("allowed", "permissions", "scopes", "access_tags", "roles", "grants"),
    "language_decision": ("detected_language", "language_confidence", "translate"),
    "date_decision": ("today", "now", "current_date", "resolved_as_of"),
    "limits": ("max_rows", "max_bytes", "limit", "timeout", "rate_limit", "byte_ceiling"),
}

_ALL_FORBIDDEN = tuple(name for names in _ASSERTED_AUTHORITY.values() for name in names)


def test_no_canonical_contract_declares_an_asserted_authority() -> None:
    """By field set, over every contract an inbound payload can reach."""
    offenders: list[str] = []
    for model in (RawChannelRequest, ChannelEnvelope, ChannelAuditEvent, ChannelRefusal):
        for fact, names in _ASSERTED_AUTHORITY.items():
            for name in names:
                if name in model.model_fields:
                    offenders.append(f"{model.__name__}.{name} asserts {fact}")
    assert not offenders, offenders


def test_the_wire_shape_declares_no_asserted_authority() -> None:
    """A caller has nowhere to put the claim, so it cannot be dropped-but-believed."""
    assert not WIRE_FIELDS & set(_ALL_FORBIDDEN)


def test_the_wire_declares_a_tenant_and_that_is_not_a_decision() -> None:
    """Stated explicitly, because "declares a tenant" looks like an exception and is not."""
    assert "tenant" in WIRE_FIELDS
    text = (_SRC / "identity" / "tenant.py").read_text(encoding="utf-8")
    assert "CHANNEL_TENANT_MISMATCH" in text, "the declaration is compared, not accepted"


def test_conversion_accepts_no_already_verified_claim() -> None:
    """By signature: the claim cannot arrive out-of-band either."""
    parameters = set(inspect.signature(convert).parameters)
    for name in _ALL_FORBIDDEN:
        assert name not in parameters
    assert not any("verif" in name for name in parameters), (
        "a parameter named for verification would be a claim the caller controls"
    )


def test_verification_takes_no_parameter_that_could_skip_it() -> None:
    parameters = set(inspect.signature(verify_authenticity).parameters)
    assert parameters == {"raw", "descriptor", "material", "bounds", "at"}
    for name in ("skip", "force", "trust", "already", "assume"):
        assert not any(name in parameter for parameter in parameters)


@pytest.mark.parametrize("name", sorted(_ALL_FORBIDDEN))
def test_a_payload_declaring_an_authority_refuses(name: str) -> None:
    """By behaviour: trying it refuses, with the unknown-field code and nothing derived."""
    resolver = CountingIdentityResolver(active_binding())
    pseudonymiser = CountingPseudonymiser()
    outcome = convert(
        signed_request(_CHANNEL, payload=wire_payload(**{name: "anything"})),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN
    assert resolver.calls == 0 and pseudonymiser.calls == 0


def test_a_header_claiming_verification_changes_nothing() -> None:
    """The adapter-side version of the same attack: assert it in a header instead."""
    raw = signed_request(_CHANNEL)
    claimed = raw.model_copy(
        update={
            "headers": (
                *raw.headers,
                ("x-verified", "true"),
                ("x-authenticated-user", "somebody-else"),
                ("x-max-rows", "1000000"),
            )
        }
    )
    common = {
        "descriptor": descriptor_for(_CHANNEL),
        "material": FIXTURE_MATERIAL,
        "bounds": bounds_for(_CHANNEL),
        "kind": MessageKind.TEXT,
        "external": FIXTURE_EXTERNAL,
        "at": AT,
    }
    plain = convert(
        raw,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=CountingPseudonymiser(),
        **common,  # type: ignore[arg-type]
    )
    with_claims = convert(
        claimed,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=CountingPseudonymiser(),
        **common,  # type: ignore[arg-type]
    )
    assert isinstance(plain, ChannelEnvelope)
    assert isinstance(with_claims, ChannelEnvelope)
    assert plain.model_dump() == with_claims.model_dump(), "a header claim changed the outcome"


def test_a_forged_signature_is_not_rescued_by_a_verified_header() -> None:
    raw = signed_request(_CHANNEL)
    forged = raw.model_copy(
        update={
            "body": raw.body.replace(b"julho", b"agosto"),
            "headers": (*raw.headers, ("x-verified", "true")),
        }
    )
    outcome = convert(
        forged,
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID


def test_the_scheme_is_chosen_by_the_descriptor_not_by_the_payload() -> None:
    """A payload that could name its own scheme could name the weakest one.

    Checked over the module's **code**, with docstrings excluded by parsing rather than by string
    matching: the prose in `verify.py` explains this very rule and says the word "payload" while
    doing so, and a scan that could not tell prose from code would forbid its own explanation.
    """
    source = (_SRC / "inbound" / "verify.py").read_text(encoding="utf-8")
    assert re.search(r"descriptor\.verification_scheme", source)

    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    arguments = {
        argument.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for argument in [*node.args.args, *node.args.kwonlyargs]
    }
    for identifier in names | attributes | arguments:
        assert "payload" not in identifier, f"verification reads a payload: {identifier}"
