"""Identity resolution and tenant consistency — T062 (FR-017 to FR-020, FR-028; SC-010).

Five binding conditions collapse into one sender-facing code, and each keeps its own
operator-facing class. Plus: no cache exists, and a tenant that disagrees with the binding refuses.
"""

from __future__ import annotations

import pathlib

import pytest

from channel_integration.contracts._base import ChannelViolation, PrincipalRef, TenantId
from channel_integration.contracts.audit import DetailClass
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.identity import BindingStatus
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.identity import resolve as resolve_module
from channel_integration.identity.resolve import IdentityRefused, resolve_identity
from channel_integration.identity.tenant import require_consistent_tenant

from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    CountingIdentityResolver,
    active_binding,
)

pytestmark = pytest.mark.unit


def test_exactly_one_active_binding_resolves() -> None:
    resolver = CountingIdentityResolver(active_binding())
    binding = resolve_identity(resolver, ChannelId.SLACK, FIXTURE_EXTERNAL)
    assert binding.principal_ref == FIXTURE_PRINCIPAL
    assert resolver.calls == 1, "the registry is consulted once, not per field"


def test_no_binding_refuses_as_unmapped() -> None:
    with pytest.raises(IdentityRefused) as caught:
        resolve_identity(CountingIdentityResolver(), ChannelId.SLACK, FIXTURE_EXTERNAL)
    assert caught.value.code is ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED
    assert caught.value.detail_class is DetailClass.BINDING_ABSENT


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (BindingStatus.REVOKED, DetailClass.BINDING_REVOKED),
        (BindingStatus.EXPIRED, DetailClass.BINDING_EXPIRED),
    ],
)
def test_a_revoked_or_expired_binding_refuses_with_the_same_code(
    status: BindingStatus, detail: DetailClass
) -> None:
    """Same code to the sender, different class to the operator (ADR 0018)."""
    resolver = CountingIdentityResolver(active_binding(status=status))
    with pytest.raises(IdentityRefused) as caught:
        resolve_identity(resolver, ChannelId.SLACK, FIXTURE_EXTERNAL)
    assert caught.value.code is ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED
    assert caught.value.detail_class is detail


def test_a_revoked_binding_is_reported_even_beside_an_expired_one() -> None:
    """The worst status wins, so a revocation is not hidden behind an expiry."""
    resolver = CountingIdentityResolver(
        active_binding(status=BindingStatus.EXPIRED),
        active_binding(status=BindingStatus.REVOKED),
    )
    with pytest.raises(IdentityRefused) as caught:
        resolve_identity(resolver, ChannelId.SLACK, FIXTURE_EXTERNAL)
    assert caught.value.detail_class is DetailClass.BINDING_REVOKED


def test_two_usable_bindings_refuse_rather_than_choosing() -> None:
    resolver = CountingIdentityResolver(
        active_binding(principal_ref=PrincipalRef("principal-ref-a")),
        active_binding(principal_ref=PrincipalRef("principal-ref-b")),
    )
    with pytest.raises(IdentityRefused) as caught:
        resolve_identity(resolver, ChannelId.SLACK, FIXTURE_EXTERNAL)
    assert caught.value.code is ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED
    assert caught.value.detail_class is DetailClass.BINDING_AMBIGUOUS


def test_a_binding_for_another_channel_is_not_this_channels_binding() -> None:
    resolver = CountingIdentityResolver(active_binding(channel=ChannelId.WHATSAPP))
    with pytest.raises(IdentityRefused) as caught:
        resolve_identity(resolver, ChannelId.SLACK, FIXTURE_EXTERNAL)
    assert caught.value.code is ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED


def test_every_refusal_carries_the_same_sender_facing_code() -> None:
    """The collapse, as one assertion: five conditions, one code (`SC-011` in spirit)."""
    cases = [
        CountingIdentityResolver(),
        CountingIdentityResolver(active_binding(status=BindingStatus.REVOKED)),
        CountingIdentityResolver(active_binding(status=BindingStatus.EXPIRED)),
        CountingIdentityResolver(active_binding(), active_binding()),
        CountingIdentityResolver(active_binding(channel=ChannelId.WHATSAPP)),
    ]
    codes: set[ChannelReasonCode] = set()
    for resolver in cases:
        with pytest.raises(IdentityRefused) as caught:
            resolve_identity(resolver, ChannelId.SLACK, FIXTURE_EXTERNAL)
        codes.add(caught.value.code)
    assert codes == {ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED}


def test_the_resolver_module_holds_no_cache() -> None:
    """`FR-021`, `R-7`: a cache would be a local authorization decision with a TTL.

    Asserted structurally: no module-level mutable container, and no memoisation decorator.
    """
    source = resolve_module.__file__
    assert source is not None
    text = pathlib.Path(source).read_text(encoding="utf-8")
    for forbidden in ("lru_cache", "cache(", "_CACHE", "global "):
        assert forbidden not in text, f"the resolver contains {forbidden}"
    members: dict[str, object] = dict(vars(resolve_module))
    module_state: dict[str, object] = {
        name: value
        for name, value in members.items()
        if not name.startswith("__") and isinstance(value, dict | list | set)
    }
    assert not any(
        isinstance(value, list | set) or (isinstance(value, dict) and name.isupper() is False)
        for name, value in module_state.items()
    ), f"mutable module state: {sorted(module_state)}"


def test_a_tenant_that_disagrees_with_the_binding_refuses() -> None:
    binding = active_binding()
    assert require_consistent_tenant(FIXTURE_TENANT, binding) == FIXTURE_TENANT
    with pytest.raises(ChannelViolation) as caught:
        require_consistent_tenant(TenantId("tenant-b"), binding)
    assert caught.value.code is ChannelReasonCode.CHANNEL_TENANT_MISMATCH
