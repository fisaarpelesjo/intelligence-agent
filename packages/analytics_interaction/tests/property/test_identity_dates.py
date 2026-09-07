"""The two dates in the reproducibility identity — T094 (FR-096, FR-097, FR-098; SC-006, SC-056).

    Both MUST be disclosed in every response and both MUST participate in the
    interpretation identity, so the same sentence asked under a different
    reference date or a different pin is a **different interpretation** rather
    than a collision. — `FR-098`

    Evidence: generated pairs differing in exactly one date always produce
    distinct identities. — `tasks.md` T094

Property-based, because the claim is universal. An example-based test shows the
identity differs for the two dates somebody thought to write down; a generated
one shows it differs for **every** pair, including the ones that make a naive
implementation collide — adjacent days, the same date in both fields, a pin far
in the past, an omitted pin beside a present one.

Three properties, and each fails differently:

* **separateness** — changing only ``reference_date`` changes the identity, and
  changing only ``as_of`` changes it too. An implementation that hashed one and
  ignored the other would pass half of this;
* **independence** — changing one leaves the other's value untouched in the
  intent and in the request. A derivation would keep the identity distinct while
  quietly corrupting the pin;
* **determinism** — the same pair always produces the same digest, with no clock,
  no randomness and no ordering dependence.

`hypothesis` is the only dependency this feature added anywhere, it is dev-only,
and it is pinned — a property suite that drifts with its generator is a suite
whose failures nobody can reproduce.
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.intent import ResolvedIntent, ResolvedPeriod
from analytics_interaction.contracts.request_build import build_analytics_query
from analytics_interaction.identity.interpretation_identity import (
    IDENTITY_MEMBERS,
    derive_interpretation_identity,
)
from analytics_interaction.interpretation.assemble_intent import assemble_resolved_intent

from ..conftest import REFERENCE, governed_resolution

pytestmark = pytest.mark.property

#: Bounded so generated dates stay inside the range a caller could plausibly
#: supply. Unbounded dates would exercise `datetime`'s edges rather than this
#: feature's.
DATES = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))

SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)


def _intent(
    pair: tuple[AuthorizedContext, str],
    period: ResolvedPeriod,
    *,
    reference_date: date,
    as_of: date | None,
) -> ResolvedIntent:
    authorized, fingerprint = pair
    return assemble_resolved_intent(
        (governed_resolution("installs"),),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=period,
        language=DeclaredLanguage.PT_BR,
        reference_date=reference_date,
        as_of=as_of,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )


# --- the composition -----------------------------------------------------------


def test_both_dates_are_declared_members_of_the_identity() -> None:
    """Seven members, and two of them are the dates.

    Asserted against the named composition rather than inferred from behaviour,
    so a member silently added or removed is visible.
    """
    assert "reference_date" in IDENTITY_MEMBERS
    assert "as_of" in IDENTITY_MEMBERS
    assert len(IDENTITY_MEMBERS) == 7


# --- separateness ---------------------------------------------------------------


@SETTINGS
@given(first=DATES, second=DATES)
def test_changing_only_the_reference_date_changes_the_identity(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    first: date,
    second: date,
) -> None:
    """Every pair, not the two somebody thought of."""
    pin = date(2026, 1, 15)
    left = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=first, as_of=pin)
    )
    right = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=second, as_of=pin)
    )
    assert (left == right) == (first == second)


@SETTINGS
@given(first=DATES, second=DATES)
def test_changing_only_the_as_of_changes_the_identity(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    first: date,
    second: date,
) -> None:
    left = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=REFERENCE, as_of=first)
    )
    right = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=REFERENCE, as_of=second)
    )
    assert (left == right) == (first == second)


@SETTINGS
@given(pin=DATES)
def test_an_omitted_pin_is_distinct_from_any_present_one(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    pin: date,
) -> None:
    """ "No pin" and "pinned to a date" are different interpretations.

    Serialising the absence as ``null`` rather than dropping the key is what
    makes this hold for every date, including one that happens to equal the
    reference date.
    """
    omitted = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=REFERENCE, as_of=None)
    )
    present = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=REFERENCE, as_of=pin)
    )
    assert omitted != present


@SETTINGS
@given(reference=DATES, pin=DATES)
def test_equal_dates_are_a_legitimate_pair_and_still_identify_distinctly(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    reference: date,
    pin: date,
) -> None:
    """The collision an implementation that conflated the two would produce.

    A system that stored one date and reused it would give the same identity to
    ``(reference, pin)`` and ``(pin, reference)`` whenever they differ.
    """
    forward = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=reference, as_of=pin)
    )
    swapped = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=pin, as_of=reference)
    )
    assert (forward == swapped) == (reference == pin)


# --- independence ---------------------------------------------------------------


@SETTINGS
@given(reference=DATES, pin=DATES)
def test_neither_date_is_derived_from_the_other_in_the_intent(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    reference: date,
    pin: date,
) -> None:
    intent = _intent(authorized_pair, july_period, reference_date=reference, as_of=pin)
    assert intent.reference_date == reference
    assert intent.as_of == pin


@SETTINGS
@given(reference=DATES, pin=DATES)
def test_only_the_pin_reaches_the_request(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    reference: date,
    pin: date,
) -> None:
    """`FR-097` at the boundary that matters.

    The reference date is disclosed and identifies the interpretation; the
    request carries the pin alone, because `002` resolves versions by it.
    """
    authorized, fingerprint = authorized_pair
    intent = _intent(authorized_pair, july_period, reference_date=reference, as_of=pin)
    request = build_analytics_query(intent, authorized=authorized, auth_fingerprint=fingerprint)
    assert request.as_of == pin
    assert request.as_of != reference or pin == reference


@SETTINGS
@given(reference=DATES)
def test_an_omitted_pin_stays_omitted_in_the_request_whatever_the_reference_date(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    reference: date,
) -> None:
    """The derivation would be invisible here without the generated sweep."""
    authorized, fingerprint = authorized_pair
    intent = _intent(authorized_pair, july_period, reference_date=reference, as_of=None)
    request = build_analytics_query(intent, authorized=authorized, auth_fingerprint=fingerprint)
    assert request.as_of is None


# --- determinism ----------------------------------------------------------------


@SETTINGS
@given(reference=DATES, pin=st.one_of(st.none(), DATES))
def test_the_same_pair_always_produces_the_same_identity(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    reference: date,
    pin: date | None,
) -> None:
    """No clock, no randomness, no state between calls."""
    first = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=reference, as_of=pin)
    )
    second = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=reference, as_of=pin)
    )
    assert first == second


@SETTINGS
@given(reference=DATES, pin=st.one_of(st.none(), DATES))
def test_the_identity_is_a_stable_hex_digest(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    reference: date,
    pin: date | None,
) -> None:
    identity = derive_interpretation_identity(
        _intent(authorized_pair, july_period, reference_date=reference, as_of=pin)
    )
    assert len(identity) == 64
    assert all(character in "0123456789abcdef" for character in identity)


# --- the identity is not derived from the question -----------------------------


@SETTINGS
@given(start=st.integers(min_value=0, max_value=500), length=st.integers(min_value=1, max_value=50))
def test_the_term_position_never_changes_the_identity(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    start: int,
    length: int,
) -> None:
    """`FR-056`: never derived from the question.

    Two people asking the same thing in different words place the same
    identifier at different offsets. If positions entered the identity, they
    would be two interpretations — and the identity would be a function of
    wording after all.
    """
    authorized, fingerprint = authorized_pair
    baseline = assemble_resolved_intent(
        (governed_resolution("installs", start=0, length=8),),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=july_period,
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        as_of=None,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )
    moved = assemble_resolved_intent(
        (governed_resolution("installs", start=start, length=length),),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=july_period,
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        as_of=None,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )
    assert derive_interpretation_identity(baseline) == derive_interpretation_identity(moved)


@SETTINGS
@given(
    release=st.text(
        min_size=1, max_size=12, alphabet=st.characters(min_codepoint=97, max_codepoint=122)
    )
)
def test_a_different_catalog_release_is_a_different_interpretation(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    release: str,
) -> None:
    """Governing versions are identity members, so a re-release is not a collision."""
    authorized, fingerprint = authorized_pair
    baseline = _intent(authorized_pair, july_period, reference_date=REFERENCE, as_of=None)
    other = assemble_resolved_intent(
        (governed_resolution("installs"),),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=july_period,
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        as_of=None,
        catalog_release=release,
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )
    left = derive_interpretation_identity(baseline)
    right = derive_interpretation_identity(other)
    assert (left == right) == (release == "r-1")
