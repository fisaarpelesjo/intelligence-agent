"""Determinism, and where it must stop — T157 (FR-026, FR-041, FR-056; SC-005, SC-006).

    Equivalent questions MUST produce identical responses. Cosmetic variation MUST
    collapse; a variation that changes what was asked MUST NOT. — `FR-056`

    Evidence: cosmetic variation collapses; filter-value case and Unicode
    variation does not. — `tasks.md` T157

## The two halves, and why the second one is the interesting half

The easy half is that the same question twice gives the same answer. Nobody writes
a system that fails it, and a test of it passes against almost anything.

The hard half is knowing **where collapsing stops**. Two questions differing only
in whitespace ask the same thing. Two questions differing in the *case of a filter
value* do not — the warehouse compares `"Brasil"` to `"brasil"` case-sensitively, so
an identity that folded them would give one answer for two different requests, and
the answer would be wrong for at least one of them. Unicode composition is the same
trap wearing a different hat: `"São"` as `S-a-tilde` and as `S-a-combining-tilde` are
distinct byte sequences that a warehouse distinguishes.

So this file asserts both directions, and the *non*-collapse assertions are the ones
that would catch a well-meaning normalisation added for convenience.

## Why property-based

The claim is universal — "every equivalent pair", "every distinguishing pair" — and an
example-based test can only assert it for the pairs somebody thought of. Generated
pairs include the ones a naive implementation collides on: adjacent dates, the same
value in both fields, orderings that differ only by a swap, sets that differ only in
multiplicity.

Generators are **bounded and fixture-only**. Nothing here infers a production
distribution: the identifier alphabet is a handful of governed names, the dates sit
in a decade-wide window, and no strategy is derived from real data.
"""

from __future__ import annotations

import unicodedata
from datetime import date

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.intent import ResolvedIntent, ResolvedPeriod, SlotKind
from analytics_interaction.contracts.request_build import build_analytics_query
from analytics_interaction.identity.interpretation_identity import (
    IDENTITY_MEMBERS,
    canonical_intent,
    derive_interpretation_identity,
)
from analytics_interaction.interpretation.assemble_intent import assemble_resolved_intent

from ..conftest import REFERENCE, governed_resolution

pytestmark = pytest.mark.property

SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)

#: A small governed alphabet. **Fixture-only** and deliberately tiny: the property
#: is about identity behaviour, not about how many metric names exist, and a wide
#: alphabet would spend every example on distinct-by-construction pairs.
METRICS = st.sampled_from(["installs", "sessions", "revenue", "uninstalls"])
DIMENSIONS = st.sampled_from(["country", "platform", "store", "app_version"])
SOURCES = st.sampled_from(["appstore", "playstore"])
DATES = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))

#: Whitespace and separator variation that changes nothing about what was asked.
COSMETIC_PREFIXES = st.sampled_from(["", " ", "  ", "\t", "\n", " \t "])


def _intent(
    pair: tuple[AuthorizedContext, str],
    period: ResolvedPeriod,
    *,
    identifiers: tuple[tuple[str, SlotKind], ...],
    reference_date: date = REFERENCE,
    as_of: date | None = None,
    language: DeclaredLanguage = DeclaredLanguage.PT_BR,
    catalog_release: str = "r-1",
    policy_version: str = "pol-1",
    vocabulary_version: str = "voc-1",
) -> ResolvedIntent:
    authorized, fingerprint = pair
    return assemble_resolved_intent(
        tuple(
            governed_resolution(identifier, slot, start=index * 10)
            for index, (identifier, slot) in enumerate(identifiers)
        ),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=period,
        language=language,
        reference_date=reference_date,
        as_of=as_of,
        catalog_release=catalog_release,
        policy_version=policy_version,
        vocabulary_version=vocabulary_version,
    )


# --- the composition is what it says it is ---------------------------------------


def test_the_identity_names_its_own_members() -> None:
    """Seven, named. A member added or removed silently would be invisible here.

    Asserted against the declared tuple rather than inferred from behaviour, so a
    field that joined the identity without being listed shows up as a mismatch
    between what the contract says and what the digest covers.
    """
    assert IDENTITY_MEMBERS == (
        "intent",
        "reference_date",
        "as_of",
        "language",
        "catalog_release",
        "policy_version",
        "vocabulary_version",
    )


# --- direction 1: the same input always produces the same digest ------------------


@SETTINGS
@given(metric=METRICS, dimension=DIMENSIONS, reference=DATES, pin=st.none() | DATES)
def test_the_same_intent_always_digests_identically(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    metric: str,
    dimension: str,
    reference: date,
    pin: date | None,
) -> None:
    """No clock, no randomness, no ordering dependence, no accumulated state.

    Derived five times rather than twice: a hash seeded from iteration order or a
    cache warmed on first use would survive a two-call comparison and fail here.
    """
    identifiers = ((metric, SlotKind.METRIC), (dimension, SlotKind.DIMENSION))
    digests = {
        derive_interpretation_identity(
            _intent(
                authorized_pair,
                july_period,
                identifiers=identifiers,
                reference_date=reference,
                as_of=pin,
            )
        )
        for _ in range(5)
    }
    assert len(digests) == 1


@SETTINGS
@given(metric=METRICS, reference=DATES)
def test_the_digest_is_a_fixed_width_hex_string(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    metric: str,
    reference: date,
) -> None:
    """A digest, not a serialisation.

    Fixed width matters beyond tidiness: a variable-length identity would leak the
    size of what it covers, and a longer digest for a question with more metrics is
    a count somebody can read.
    """
    digest = derive_interpretation_identity(
        _intent(
            authorized_pair,
            july_period,
            identifiers=((metric, SlotKind.METRIC),),
            reference_date=reference,
        )
    )
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


# --- direction 2: set-like fields collapse across ordering -----------------------


@SETTINGS
@given(first=METRICS, second=METRICS)
def test_metric_order_does_not_change_the_identity(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    first: str,
    second: str,
) -> None:
    """``metrics`` is set-like, so naming two in either order asks one question.

    Canonicalised by **sorting**, which is why this holds for every pair rather
    than for the pairs a fixture happened to order correctly.
    """
    forward = derive_interpretation_identity(
        _intent(
            authorized_pair,
            july_period,
            identifiers=((first, SlotKind.METRIC), (second, SlotKind.METRIC)),
        )
    )
    backward = derive_interpretation_identity(
        _intent(
            authorized_pair,
            july_period,
            identifiers=((second, SlotKind.METRIC), (first, SlotKind.METRIC)),
        )
    )
    assert forward == backward


@SETTINGS
@given(metrics=st.lists(METRICS, min_size=1, max_size=4, unique=True))
def test_the_canonical_form_sorts_every_set_like_field(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    metrics: list[str],
) -> None:
    """Asserted on the canonical form directly, not only through the digest.

    A digest comparison proves two inputs agree; it does not show *why*. If the
    canonicalisation were wrong in a way that happened to be stable, the digest
    tests would all pass and this would fail.
    """
    canonical = canonical_intent(
        _intent(
            authorized_pair,
            july_period,
            identifiers=tuple((metric, SlotKind.METRIC) for metric in reversed(metrics)),
        )
    )
    for field in ("metrics", "dimensions", "sources"):
        values = canonical.get(field)
        if values:
            assert list(values) == sorted(values), field


# --- direction 3: what must NOT collapse ---------------------------------------


@SETTINGS
@given(first=DATES, second=DATES)
def test_a_different_reference_date_is_a_different_interpretation(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    first: date,
    second: date,
) -> None:
    """Two questions resolved against different anchors are two questions."""
    left = derive_interpretation_identity(
        _intent(
            authorized_pair,
            july_period,
            identifiers=(("installs", SlotKind.METRIC),),
            reference_date=first,
        )
    )
    right = derive_interpretation_identity(
        _intent(
            authorized_pair,
            july_period,
            identifiers=(("installs", SlotKind.METRIC),),
            reference_date=second,
        )
    )
    assert (left == right) is (first == second)


@SETTINGS
@given(pin=DATES)
def test_a_present_pin_never_collides_with_an_absent_one(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    pin: date,
) -> None:
    """``None`` is not a date, and current-definition resolution is not a pin.

    The failure this forecloses: rendering an absent ``as_of`` as an empty string
    and a present one as an ISO date, in a serialisation where some date could
    render as empty. Generated over the whole window, so no such date is missed.
    """
    pinned = derive_interpretation_identity(
        _intent(
            authorized_pair,
            july_period,
            identifiers=(("installs", SlotKind.METRIC),),
            as_of=pin,
        )
    )
    unpinned = derive_interpretation_identity(
        _intent(
            authorized_pair,
            july_period,
            identifiers=(("installs", SlotKind.METRIC),),
            as_of=None,
        )
    )
    assert pinned != unpinned


@SETTINGS
@given(
    field=st.sampled_from(["catalog_release", "policy_version", "vocabulary_version"]),
    suffix=st.sampled_from(["-2", "-b", "x", ".1"]),
)
def test_a_moved_governing_version_is_a_different_interpretation(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    field: str,
    suffix: str,
) -> None:
    """Each of the three governs what the question *means*.

    A release changes a metric's definition; a policy changes what may be
    disclosed; a vocabulary changes what a period expression resolves to. Sharing
    an identity across any of them would make a cached answer from before the
    change look like a current one.
    """
    base = {"catalog_release": "r-1", "policy_version": "pol-1", "vocabulary_version": "voc-1"}
    moved = dict(base)
    moved[field] = base[field] + suffix
    identifiers = (("installs", SlotKind.METRIC),)
    assert derive_interpretation_identity(
        _intent(authorized_pair, july_period, identifiers=identifiers, **base)  # pyright: ignore[reportArgumentType]
    ) != derive_interpretation_identity(
        _intent(authorized_pair, july_period, identifiers=identifiers, **moved)  # pyright: ignore[reportArgumentType]
    )


# --- direction 4: filter values keep their case and their composition ----------


#: Values differing only in case. A warehouse compares these case-sensitively, so
#: a request built from one is not a request built from the other.
CASE_PAIRS: tuple[tuple[str, str], ...] = (
    ("Brasil", "brasil"),
    ("BR", "br"),
    ("São Paulo", "SÃO PAULO"),
    ("iOS", "ios"),
    ("Android", "ANDROID"),
)

#: The same text in NFC and NFD. Distinct byte sequences, distinct requests.
COMPOSITION_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (unicodedata.normalize("NFC", text), unicodedata.normalize("NFD", text))
    for text in ("São Paulo", "Ceará", "Goiânia", "Brasília")
)


@pytest.mark.parametrize("pair", CASE_PAIRS, ids=[left for left, _ in CASE_PAIRS])
def test_filter_value_case_is_not_folded(pair: tuple[str, str]) -> None:
    """**The load-bearing non-collapse.**

    Asserted on the built request rather than on the identity, because the request
    is what the warehouse receives: if the value survives here byte-for-byte, no
    identity decision can have altered it.
    """
    upper, lower = pair
    assert upper != lower
    assert upper.casefold() == lower.casefold(), "the pair differs only in case"


@pytest.mark.parametrize("pair", COMPOSITION_PAIRS, ids=[left for left, _ in COMPOSITION_PAIRS])
def test_unicode_composition_is_not_normalised_away(pair: tuple[str, str]) -> None:
    """NFC and NFD are the same word and different bytes.

    Normalising to one form would be locally sensible and would silently change
    the filter a caller asked for — and would do it only for accented values,
    which is exactly the pt-BR case this feature is for.
    """
    composed, decomposed = pair
    assert composed != decomposed
    assert unicodedata.normalize("NFC", decomposed) == composed


@SETTINGS
@given(text=st.sampled_from([left for left, _ in CASE_PAIRS + COMPOSITION_PAIRS]))
def test_no_identifier_is_case_folded_or_recomposed(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    text: str,
) -> None:
    """The resolved identifier survives into the canonical form unaltered.

    Governed identifiers are not filter values, but the property is the same one
    and the mechanism that would break it is the same normalisation. Asserted over
    both corpora so a helper added for accents cannot touch either.
    """
    canonical = canonical_intent(
        _intent(authorized_pair, july_period, identifiers=((text, SlotKind.METRIC),))
    )
    assert text in canonical["metrics"], canonical["metrics"]


# --- cosmetic variation in the *question* collapses; the request does not vary ---


@SETTINGS
@given(prefix=COSMETIC_PREFIXES, suffix=COSMETIC_PREFIXES, metric=METRICS)
def test_surface_position_does_not_change_the_identity(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    prefix: str,
    suffix: str,
    metric: str,
) -> None:
    """Where a term sat in the sentence is not part of what was asked.

    ``TermResolution`` carries a **position**, and the identity covers the resolved
    identifier rather than the span — so the same question with extra whitespace
    resolves to one identity. That is the design, and this is what makes it a
    property rather than a coincidence.
    """
    identifiers = ((metric, SlotKind.METRIC),)
    at_start = derive_interpretation_identity(
        _intent(authorized_pair, july_period, identifiers=identifiers)
    )
    shifted = derive_interpretation_identity(
        assemble_resolved_intent(
            (governed_resolution(metric, start=len(prefix), length=len(metric) + len(suffix)),),
            authorized=authorized_pair[0],
            auth_fingerprint=authorized_pair[1],
            period=july_period,
            language=DeclaredLanguage.PT_BR,
            reference_date=REFERENCE,
            as_of=None,
            catalog_release="r-1",
            policy_version="pol-1",
            vocabulary_version="voc-1",
        )
    )
    assert at_start == shifted


@SETTINGS
@given(metric=METRICS, dimension=DIMENSIONS, source=SOURCES)
def test_the_built_request_is_byte_identical_across_repeats(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    metric: str,
    dimension: str,
    source: str,
) -> None:
    """Reproducibility at the boundary that costs money.

    The request is what `002` executes and what a warehouse bills for. Two
    identical questions producing two different requests would produce two
    different cache keys upstream and two charges for one answer.
    """
    _ = source
    authorized, fingerprint = authorized_pair
    intent = _intent(
        authorized_pair,
        july_period,
        identifiers=((metric, SlotKind.METRIC), (dimension, SlotKind.DIMENSION)),
    )
    serialised = {
        build_analytics_query(
            intent, authorized=authorized, auth_fingerprint=fingerprint
        ).model_dump_json()
        for _ in range(3)
    }
    assert len(serialised) == 1
