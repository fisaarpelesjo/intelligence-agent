"""Shared fixtures. TEST-ONLY, and never evidence for any external record.

Kept small on purpose. Three things recur across the intent, identity and
request suites — a resolved authorization context, a governed resolution set and
the intent they assemble into — and duplicating them in each file would let two
suites drift into testing slightly different worlds.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType

from analytics_interaction.authorization.context_preflight import (
    AuthorizedContext,
    resolve_authorization_context,
)
from analytics_interaction.contracts.intake import DeclaredLanguage, PrincipalContext
from analytics_interaction.contracts.intent import (
    MatchKind,
    ResolutionBasis,
    ResolvedIntent,
    ResolvedPeriod,
    SlotKind,
    TermRef,
    TermResolution,
)
from analytics_interaction.identity.authorization_fingerprint import (
    derive_authorization_fingerprint,
)
from analytics_interaction.interpretation.assemble_intent import assemble_resolved_intent
from analytics_interaction.interpretation.period import resolve_explicit_period

from .fixtures.counters import CountingResolver, Surfaces

ON = date(2026, 8, 13)
REFERENCE = date(2026, 8, 13)
JULY = (date(2026, 7, 1), date(2026, 7, 31))

RESOLVED_PRINCIPAL = PrincipalContext(
    principal_ref="p-1",
    principal_type=PrincipalType.USER,
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    authorization_policy_pin="authpol-1",
)
SUPPLIED_PRINCIPAL = PrincipalContext(principal_ref="p-1", principal_type=PrincipalType.USER)


def authorize(resolved: PrincipalContext = RESOLVED_PRINCIPAL) -> AuthorizedContext:
    """Run the real step-2 preflight against a synthetic identity answer."""
    return resolve_authorization_context(
        SUPPLIED_PRINCIPAL, resolver=CountingResolver(Surfaces(), answer=resolved)
    )


@pytest.fixture
def authorized() -> AuthorizedContext:
    return authorize()


@pytest.fixture
def authorized_pair(authorized: AuthorizedContext) -> tuple[AuthorizedContext, str]:
    """The context and the fingerprint resolution ran under, as a pair.

    A pair rather than two fixtures, because the whole point of the binding is
    that they travel together — handing a test one without the other would let it
    accidentally assemble an intent under a fingerprint nobody derived.
    """
    return authorized, derive_authorization_fingerprint(authorized)


@pytest.fixture
def july_period() -> ResolvedPeriod:
    """An explicit range. Needs no `D-18`, which is why it resolves today."""
    start, end = JULY
    return resolve_explicit_period(start, end, reference_date=REFERENCE, on=ON)


def governed_resolution(
    identifier: str,
    slot: SlotKind = SlotKind.METRIC,
    *,
    start: int = 0,
    length: int = 8,
    matched_via: MatchKind = MatchKind.CANONICAL_ID,
    basis: ResolutionBasis = ResolutionBasis.ENUMERATED_MEMBERSHIP,
) -> TermResolution:
    """One governed term, as `001`'s surface would have resolved it."""
    return TermResolution(
        term=TermRef(start=start, length=length),
        slot=slot,
        resolved_to=identifier,
        matched_via=matched_via,
        confidence_basis=basis,
    )


@pytest.fixture
def resolution_factory() -> Callable[..., TermResolution]:
    return governed_resolution


@pytest.fixture
def resolved_intent(
    authorized_pair: tuple[AuthorizedContext, str], july_period: ResolvedPeriod
) -> ResolvedIntent:
    """A complete, minimal governed intent: one metric over an explicit period."""
    context, fingerprint = authorized_pair
    return assemble_resolved_intent(
        (governed_resolution("installs"),),
        authorized=context,
        auth_fingerprint=fingerprint,
        period=july_period,
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        as_of=None,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )


#: Every node ID this session collected, recorded by the hook below.
#:
#: The coverage audits (`T169`—`T174`) need to know which test modules contribute **real**
#: tests, so a requirement cited in a comment cannot count as validated. Three ways to
#: get that, and only one is sound:
#:
#: * scanning for ``def test_`` misses a parametrised, decorated or conditionally-defined
#:   test — exactly the ones a citation is most likely to sit beside;
#: * shelling out to ``pytest --collect-only`` **recurses**: the child imports the audit
#:   modules, which collect at import, which shell out again;
#: * this hook, which reads the collection of the very run the audit is part of.
#:
#: Populated before any test executes, so an audit reading it sees the whole session
#: rather than whatever had run by then.
COLLECTED_NODE_IDS: set[str] = set()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Record the session's node IDs. Modifies nothing.

    Named for the hook it implements rather than for what it does, which is pytest's
    convention. The name is the contract; the body deliberately reorders, deselects and
    skips nothing — a collection hook that changed the run would make every audit reading
    this set describe a different run from the one that happened.
    """
    COLLECTED_NODE_IDS.update(item.nodeid for item in items)
