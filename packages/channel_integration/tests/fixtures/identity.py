"""Fixture identity bindings and pseudonymisation key — T051 (FR-072; SC-034).

**TEST-ONLY.** The key here is a fixed test key, not `D-31` material: `D-31` is undeclared, so the
production port refuses and every flow needing a reference refuses with
``CHANNEL_AUDIT_UNAVAILABLE``. A fixture key lets the contract be exercised without the material
existing, and it changes no readiness state.

No real phone number, member id, chat id, handle or email appears here. The external identities
are obviously synthetic, because a fixture carrying a real identifier would put personal data in
version control — the thing `FR-077` exists to prevent.

`CountingIdentityResolver` counts its calls. That is what makes "a failure before step 7 causes
**zero** identity resolutions" a measured property rather than an inspected one (`T052`).
"""

from __future__ import annotations

from analytics_interaction.contracts.intake import PrincipalContext

from channel_integration.contracts._base import PrincipalRef, TenantId
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.identity import (
    BindingStatus,
    ChannelIdentityBinding,
    ExternalIdentity,
)
from channel_integration.identity.pseudonymise import KeyedPseudonymiser, PseudonymPort

__all__ = [
    "FIXTURE_EXTERNAL",
    "FIXTURE_KEY",
    "FIXTURE_PRINCIPAL",
    "FIXTURE_TENANT",
    "CountingIdentityResolver",
    "CountingPseudonymiser",
    "active_binding",
    "fixture_principal_context",
    "fixture_pseudonymiser",
]

FIXTURE_TENANT = TenantId("tenant-a")
FIXTURE_PRINCIPAL = PrincipalRef("principal-ref-a")

#: Synthetic. Not a phone number, not a member id, not anyone's chat.
FIXTURE_EXTERNAL = ExternalIdentity("fixture-external-identity-1")

#: A fixed 32-byte test key. Fixed rather than random, so a derived reference is byte-identical
#: across runs and a determinism test can assert it.
FIXTURE_KEY = b"fixture-pseudonymisation-key-000"


def fixture_pseudonymiser() -> KeyedPseudonymiser:
    """The fixture port. Never the production one, which refuses."""
    return KeyedPseudonymiser(FIXTURE_KEY, "fixture-key-1")


def active_binding(
    channel: ChannelId = ChannelId.SLACK,
    tenant: TenantId = FIXTURE_TENANT,
    principal_ref: PrincipalRef = FIXTURE_PRINCIPAL,
    status: BindingStatus = BindingStatus.ACTIVE,
) -> ChannelIdentityBinding:
    """One binding, active by default."""
    return ChannelIdentityBinding(
        channel=channel,
        tenant=tenant,
        principal_ref=principal_ref,
        status=status,
        binding_version="fixture-registry-1",
    )


class CountingIdentityResolver:
    """A registry that records how many times it was consulted."""

    def __init__(self, *bindings: ChannelIdentityBinding) -> None:
        self._bindings = bindings
        self.calls = 0

    def bindings_for(
        self, channel: ChannelId, external: ExternalIdentity
    ) -> tuple[ChannelIdentityBinding, ...]:
        self.calls += 1
        return self._bindings


class CountingPseudonymiser:
    """A pseudonymiser that records how many references it derived.

    Wraps the fixture port rather than reimplementing it, so a counted derivation is the same
    derivation the real code path performs.
    """

    def __init__(self) -> None:
        self._inner = fixture_pseudonymiser()
        self.key_version = self._inner.key_version
        self.calls = 0

    def derive(self, label: str, *parts: str) -> str:
        self.calls += 1
        return self._inner.derive(label, *parts)


#: Structural check that the counting wrapper still satisfies the port, at import time.
_COUNTER_SATISFIES_THE_PORT: PseudonymPort = CountingPseudonymiser()


# --------------------------------------------------------------------------- #
# The authorization context — added 2026-08-19 for T122's composed round trip  #
# --------------------------------------------------------------------------- #
# `QuestionIntake.principal` is a full `PrincipalContext`: a reference **plus** a principal type, an
# authorization scope, a granted tag set and a policy pin. `src/channel_integration/interaction/
# port.py` records the measurement — nothing in `004` produces the other four fields, so the
# composed path takes the context as an argument and this fixture supplies one for tests.
#
# It lives here rather than in a new module because the ledger declares no fixture module for an
# authorization context, and inventing one would be an undeclared artifact. An identity fixture is
# what this file is for.


def fixture_principal_context(
    principal_ref: str = str(FIXTURE_PRINCIPAL),
    granted_access_tags: frozenset[str] = frozenset(),
) -> PrincipalContext:
    """A resolved authorization context. **TEST-ONLY, and it authorizes nothing.**

    Built through ``model_validate`` with ``principal_type`` as the string the contract declares,
    deliberately: `PrincipalType` lives in `semantic_catalog.contracts.access_tag`, which
    `contracts/interaction-port.md` §3 does not list. Importing it would add a twenty-second
    upstream name, and `T119` says plainly that a twenty-second name is a new decision. The string
    reaches `003`'s own field validator and `003` decides whether it is a member — the same
    reasoning `intake_from_envelope` applies to the declared language.

    The scope is `None` and the tag set is empty by default: a fixture that granted itself a scope
    would be a fixture that decides authorization, which is the one thing no part of this feature
    may do. A test needing granted tags passes them and says so at the call site.
    """
    return PrincipalContext.model_validate(
        {
            "principal_ref": principal_ref,
            "principal_type": "user",
            "authorization_scope": None,
            "granted_access_tags": granted_access_tags,
            "authorization_policy_pin": None,
        }
    )
