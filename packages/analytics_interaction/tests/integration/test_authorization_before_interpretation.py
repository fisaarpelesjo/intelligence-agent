"""Authorization precedes everything — T047 (FR-089, FR-091; SC-050, SC-051).

**Counted, not inspected.** `FR-089` requires the zero-call property to be
measured against each surface. Every assertion here reads a counter that a real
call would have incremented.

**The contrast case is what makes the test mean anything.** A suite that only
showed zero calls for an unauthorized principal would pass just as well against a
system that never called anything at all. So an authorized principal is driven
through the same sequence and must get **one stage further** — reaching governed
content resolution at step 3 and refusing there, because `D-18` and `D-19` hold
no approved instance. Two different refusals, from two different steps, proves
the ordering is real.

The sequence is composed here rather than imported: steps 1-2 are all that exist
today, the orchestrator is a later phase, and a placeholder one built for this
test would be exactly the "placeholder implementation for later tasks" the phase
boundary forbids.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType

from analytics_interaction.authorization.context_preflight import (
    AuthorizationContextResolver,
    AuthorizedContext,
    resolve_authorization_context,
)
from analytics_interaction.authorization.refusal import AuthorizationRefused
from analytics_interaction.contracts.intake import PrincipalContext
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.governance.policy import resolve_policy
from analytics_interaction.governance.resolve import ContentUnresolvable
from analytics_interaction.governance.vocabulary import resolve_period_vocabulary

from ..fixtures.counters import SURFACES, CountingResolver, Surfaces

pytestmark = pytest.mark.integration

ON = date(2026, 8, 13)

RESOLVED = PrincipalContext(
    principal_ref="p-1",
    principal_type=PrincipalType.USER,
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    authorization_policy_pin="authpol-1",
)

#: What a caller supplies: who they claim to be, and nothing about what they may
#: see. Scope, tags and pin are left for the identity system to answer.
SUPPLIED = PrincipalContext(principal_ref="p-1", principal_type=PrincipalType.USER)


def _step_2(
    supplied: PrincipalContext, resolver: AuthorizationContextResolver | None
) -> AuthorizedContext:
    """Step 2 alone."""
    return resolve_authorization_context(supplied, resolver=resolver)


def _steps_2_and_3(
    supplied: PrincipalContext, resolver: AuthorizationContextResolver | None
) -> None:
    """Steps 2 then 3, in order, stopping at the first refusal.

    Step 3 is governed-content resolution. It is reached only if step 2 returned,
    which is the ordering under test.
    """
    authorized = _step_2(supplied, resolver)
    assert isinstance(authorized, AuthorizedContext)
    resolve_period_vocabulary(ON)
    resolve_policy(ON)


# --- an unresolvable context: counted zero across all six ---------------------


#: Each entry builds the collaborator for one failure mode against a fresh
#: counter set. Typed explicitly so a new case cannot quietly return
#: something the preflight would accept.
UnresolvableCase = Callable[[Surfaces], AuthorizationContextResolver | None]

UNRESOLVABLE: dict[str, UnresolvableCase] = {
    "no resolver configured": lambda _s: None,
    "principal unknown": lambda s: CountingResolver(s, answer=None),
    "identity system failed": lambda s: CountingResolver(s, raises=RuntimeError("idp down")),
    "resolver answered the wrong principal": lambda s: CountingResolver(
        s, answer=RESOLVED.model_copy(update={"principal_ref": "someone-else"})
    ),
    "scope did not resolve": lambda s: CountingResolver(
        s, answer=RESOLVED.model_copy(update={"authorization_scope": None})
    ),
    "policy pin did not resolve": lambda s: CountingResolver(
        s, answer=RESOLVED.model_copy(update={"authorization_policy_pin": None})
    ),
    "caller asserted a wider tag set": lambda s: CountingResolver(s, answer=RESOLVED),
}


def _supplied_for(case: str) -> PrincipalContext:
    if case == "caller asserted a wider tag set":
        return SUPPLIED.model_copy(
            update={"granted_access_tags": frozenset({"installs:read", "revenue:read"})}
        )
    return SUPPLIED


@pytest.mark.parametrize("case", sorted(UNRESOLVABLE))
def test_an_unresolvable_context_refuses(case: str) -> None:
    surfaces = Surfaces()
    with pytest.raises(AuthorizationRefused) as caught:
        _steps_2_and_3(_supplied_for(case), UNRESOLVABLE[case](surfaces))
    assert caught.value.code is InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE


@pytest.mark.parametrize("case", sorted(UNRESOLVABLE))
def test_an_unresolvable_context_produces_counted_zero_on_every_surface(case: str) -> None:
    """The whole vector at once, so a seventh surface cannot go unchecked."""
    surfaces = Surfaces()
    with pytest.raises(AuthorizationRefused):
        _steps_2_and_3(_supplied_for(case), UNRESOLVABLE[case](surfaces))

    assert surfaces.counts() == dict.fromkeys(SURFACES, 0), f"{case} reached: {surfaces.touched()}"


@pytest.mark.parametrize("surface", SURFACES)
def test_each_named_surface_is_individually_zero(surface: str) -> None:
    """Named one at a time as well, so a failure says which surface was touched."""
    surfaces = Surfaces()
    with pytest.raises(AuthorizationRefused):
        _steps_2_and_3(SUPPLIED, CountingResolver(surfaces, answer=None))
    assert getattr(surfaces, surface) == 0


def test_the_counters_are_not_vacuous() -> None:
    """A counter that cannot increment would make every zero meaningless.

    Each collaborator is driven once and observed to count. Without this the
    suite above would pass against six inert objects.
    """
    surfaces = Surfaces()
    catalog = surfaces.catalog_surface()
    for call in (
        lambda: catalog.evaluate(),
        lambda: catalog.search(),
        lambda: surfaces.model_port().narrow(),
        lambda: surfaces.clarification_issuer().issue(),
        lambda: surfaces.execution_port().submit(),
        lambda: surfaces.limit_discloser().disclose(),
    ):
        with pytest.raises(AssertionError):
            call()

    assert surfaces.counts() == {
        "catalog": 2,
        "model": 1,
        "candidates": 1,
        "clarification": 1,
        "execution": 1,
        "limit_disclosure": 1,
    }
    assert not surfaces.all_zero()
    assert sorted(surfaces.touched()) == sorted(SURFACES)


# --- the contrast: an authorized principal gets one stage further -------------


def test_an_authorized_principal_passes_step_2_and_refuses_at_step_3() -> None:
    """The ordering is real, not asserted.

    Same sequence, same surfaces, a different refusal — from governed-content
    resolution rather than from authorization. If step 2 ran after step 3, or if
    step 3 never ran, this could not hold.
    """
    surfaces = Surfaces()
    with pytest.raises(ContentUnresolvable) as caught:
        _steps_2_and_3(SUPPLIED, CountingResolver(surfaces, answer=RESOLVED))

    assert caught.value.code is InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE
    assert surfaces.resolver_calls == ["p-1"], "step 2 ran exactly once"


def test_the_authorized_case_still_touches_no_cost_surface() -> None:
    """Passing step 2 buys no catalog read, model call or execution.

    Those come later in the sequence, and today none of them is reachable at all
    — so the authorized path costs nothing either.
    """
    surfaces = Surfaces()
    with pytest.raises(ContentUnresolvable):
        _steps_2_and_3(SUPPLIED, CountingResolver(surfaces, answer=RESOLVED))
    assert surfaces.counts() == dict.fromkeys(SURFACES, 0)


def test_the_two_refusals_are_different_types_and_different_codes() -> None:
    """Otherwise "one stage later" would be unobservable."""
    unauthorized = Surfaces()
    with pytest.raises(AuthorizationRefused) as first:
        _steps_2_and_3(SUPPLIED, CountingResolver(unauthorized, answer=None))

    authorized = Surfaces()
    with pytest.raises(ContentUnresolvable) as second:
        _steps_2_and_3(SUPPLIED, CountingResolver(authorized, answer=RESOLVED))

    assert first.value.code is not second.value.code


# --- cost attribution ---------------------------------------------------------


def test_no_resolver_call_is_made_for_a_caller_the_contract_already_rejects() -> None:
    """`FR-091`: cost is never incurred on behalf of an unresolved caller.

    A missing collaborator is refused before the identity system is consulted, so
    even the resolver lookup is not performed.
    """
    surfaces = Surfaces()
    with pytest.raises(AuthorizationRefused):
        _step_2(SUPPLIED, None)
    assert surfaces.resolver_calls == []


def test_the_resolver_is_asked_exactly_once_and_about_the_stated_principal() -> None:
    """One call, one principal. A second lookup would be a second cost."""
    surfaces = Surfaces()
    _step_2(SUPPLIED, CountingResolver(surfaces, answer=RESOLVED))
    assert surfaces.resolver_calls == ["p-1"]


# --- determinism and non-disclosure -------------------------------------------


def test_repeated_equivalent_inputs_produce_equivalent_decisions() -> None:
    """No clock, no cache, no state between calls."""
    first = _step_2(SUPPLIED, CountingResolver(Surfaces(), answer=RESOLVED))
    second = _step_2(SUPPLIED, CountingResolver(Surfaces(), answer=RESOLVED))
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_every_failure_mode_serialises_to_a_byte_identical_refusal() -> None:
    """The non-disclosure property, asserted rather than documented.

    Seven different causes, one indistinguishable output. A caller who could tell
    them apart could map the identity system by probing it.
    """
    rendered: set[str] = set()
    for case in sorted(UNRESOLVABLE):
        surfaces = Surfaces()
        with pytest.raises(AuthorizationRefused) as caught:
            _step_2(_supplied_for(case), UNRESOLVABLE[case](surfaces))
        rendered.add(f"{caught.value.code.value}|{caught.value.detail}|{caught.value!s}")

    assert len(rendered) == 1, f"the refusal varies by cause: {sorted(rendered)}"


def test_the_refusal_names_no_candidate_limit_or_policy_detail() -> None:
    """An unauthorized caller learns nothing about the catalog or the policy."""
    with pytest.raises(AuthorizationRefused) as caught:
        _step_2(SUPPLIED, CountingResolver(Surfaces(), answer=None))

    rendered = f"{caught.value!s} {caught.value.detail}".lower()
    for leak in (
        "installs",
        "revenue",
        "google_play",
        "tenant-a",
        "authpol",
        "p-1",
        "scope",
        "policy pin",
        "threshold",
        "bound",
        "8192",
    ):
        assert leak not in rendered, f"the refusal disclosed {leak!r}"
