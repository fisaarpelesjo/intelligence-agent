"""Slot-resolution semantics — T079 (FR-005, FR-007, FR-008, FR-011, FR-066; SC-001, SC-012).

Five properties, each of which fails in a way the others would not catch.

**Six slot kinds and no seventh.** The closed set is what lets a clarification
name its unresolved slot without a free-text field.

**`001`'s three-way outcome carried distinctly.** Published, pending stub and
not-governed stay separate. The first consumer to flatten them treats "pending"
as "missing" and sends a user away to build their own number.

**``ResolutionBasis`` records what was proved.** An open-text resolution is never
presented with enumerated standing — a country term that is merely shape-valid
has not been shown to exist in the data.

**Role ambiguity clarifies.** ``google_play`` is both a governed source id and a
governed store dimension value, and preferring one by convention would silently
answer a different question roughly half the time.

**An operator outside `002`'s matrix abstains.** Never approximated with a
permitted one.

Every catalog read below goes through a fixture that filters by access *before*
deciding the outcome shape — the same order `001`'s ``CatalogApi`` uses. A
fixture that filtered afterwards would let a disclosure test pass that the real
surface would fail.
"""

from __future__ import annotations

from datetime import date

import pytest
from analytics_query.contracts.operators import DimensionType, GovernedOperator
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.search.outcomes import Ambiguous, NotGoverned, Resolved
from semantic_catalog.search.resolve import Candidate
from semantic_catalog.search.resolve import MatchKind as CatalogMatchKind

from analytics_interaction.authorization.context_preflight import (
    AuthorizedContext,
    resolve_authorization_context,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intake import PrincipalContext
from analytics_interaction.contracts.intent import (
    MatchKind,
    ResolutionBasis,
    SlotKind,
    TermRef,
    TermResolution,
)
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.interpretation.basis import basis_for_dimension_type, is_weaker_than
from analytics_interaction.interpretation.operators import (
    GOVERNED_OPERATORS,
    require_governed_operator,
)
from analytics_interaction.interpretation.outcomes import (
    LifecycleStanding,
    TermOutcome,
    classify,
)
from analytics_interaction.interpretation.resolve_terms import (
    REPRESENTABLE_MATCH_KINDS,
    TermRequest,
    candidate_refs,
    discover,
    resolve_term,
)
from analytics_interaction.interpretation.roles import RoleReading, resolve_role
from analytics_interaction.interpretation.slots import (
    FILL_ORDER,
    SLOT_KINDS,
    fill_position,
    ordered_slots,
)

from ..fixtures.catalog.discovery import (
    FIXTURE_DIMENSION_VALUES,
    FIXTURE_SOURCE_IDS,
    FixtureCatalog,
    FixtureTerm,
)
from ..fixtures.counters import CountingResolver, Surfaces

pytestmark = pytest.mark.unit

ON = date(2026, 8, 13)
SCOPE = "tenant-a"
OTHER_SCOPE = "tenant-z"

RESOLVED_PRINCIPAL = PrincipalContext(
    principal_ref="p-1",
    principal_type=PrincipalType.USER,
    authorization_scope=SCOPE,
    granted_access_tags=frozenset({"installs:read"}),
    authorization_policy_pin="authpol-1",
)
SUPPLIED = PrincipalContext(principal_ref="p-1", principal_type=PrincipalType.USER)


def _authorized(scope: str = SCOPE) -> AuthorizedContext:
    resolved = RESOLVED_PRINCIPAL.model_copy(update={"authorization_scope": scope})
    return resolve_authorization_context(
        SUPPLIED, resolver=CountingResolver(Surfaces(), answer=resolved)
    )


def _term(
    surface: str,
    metric_id: str,
    kind: CatalogMatchKind = CatalogMatchKind.CANONICAL_NAME,
    score: float = 1.0,
    visible_to: frozenset[str] = frozenset({SCOPE}),
) -> FixtureTerm:
    """TEST-ONLY authored term. Never `D-11` evidence."""
    return FixtureTerm(
        surface=surface, metric_id=metric_id, kind=kind, score=score, visible_to=visible_to
    )


def _request(slot: SlotKind = SlotKind.METRIC) -> TermRequest:
    return TermRequest(term=TermRef(start=0, length=8), slot=slot)


# --- six slot kinds, no seventh ------------------------------------------------


def test_there_are_exactly_six_slot_kinds() -> None:
    assert len(SLOT_KINDS) == 6
    assert {slot.value for slot in SLOT_KINDS} == {
        "metric",
        "dimension",
        "dimension_value",
        "source",
        "period",
        "comparison",
    }


def test_the_fill_order_covers_every_slot_exactly_once() -> None:
    assert set(FILL_ORDER) == SLOT_KINDS
    assert len(FILL_ORDER) == len(set(FILL_ORDER)) == 6


def test_the_fill_order_places_the_metric_first_and_the_comparison_last() -> None:
    """Nothing has meaning without the metric; a comparison is over resolutions."""
    assert FILL_ORDER[0] is SlotKind.METRIC
    assert FILL_ORDER[-1] is SlotKind.COMPARISON


def test_source_fills_before_dimension_value() -> None:
    """So the `google_play` role question usually has evidence by the value slot."""
    assert fill_position(SlotKind.SOURCE) < fill_position(SlotKind.DIMENSION_VALUE)


def test_ordering_is_by_the_governed_order_not_the_input_order() -> None:
    """A frozenset's iteration order is stable per process, not across them."""
    subset = frozenset({SlotKind.COMPARISON, SlotKind.METRIC, SlotKind.PERIOD})
    assert ordered_slots(subset) == (SlotKind.METRIC, SlotKind.PERIOD, SlotKind.COMPARISON)
    assert ordered_slots(subset) == ordered_slots(subset)


def test_a_seventh_slot_kind_has_no_fill_position() -> None:
    """A slot the order does not know would be one silently placed last."""
    with pytest.raises(ValueError, match="no declared fill position"):
        fill_position("aggregation")  # type: ignore[arg-type]


# --- the three-way outcome, carried distinctly ---------------------------------


def test_the_three_outcome_shapes_stay_distinct() -> None:
    query = "instalações"
    candidate = _term(query, "installs").candidate()
    assert classify(Resolved(query=query, candidate=candidate)) is TermOutcome.RESOLVED
    assert classify(Ambiguous(query=query, candidates=(candidate,))) is TermOutcome.AMBIGUOUS
    assert classify(NotGoverned(query=query)) is TermOutcome.NOT_GOVERNED


def test_published_and_pending_are_separate_from_the_outcome_shape() -> None:
    """`FR-008`. Folding them in would make "pending" read as "did not resolve"."""
    assert set(LifecycleStanding) == {
        LifecycleStanding.PUBLISHED,
        LifecycleStanding.PENDING,
    }
    assert set(TermOutcome).isdisjoint({member.value for member in LifecycleStanding})


def test_a_governed_term_resolves_to_its_canonical_identifier() -> None:
    catalog = FixtureCatalog(terms=(_term("instalações", "installs"),))
    resolution = resolve_term(
        _request(), "instalações", catalog=catalog, authorized=_authorized(), on=ON
    )
    assert isinstance(resolution, TermResolution)
    assert resolution.resolved_to == "installs"
    assert resolution.matched_via is MatchKind.CANONICAL_ID


def test_several_authorised_candidates_refuse_rather_than_picking_one() -> None:
    """`FR-016` carried through: never a silent single resolution."""
    catalog = FixtureCatalog(
        terms=(_term("conversões", "installs"), _term("conversões", "signups"))
    )
    with pytest.raises(ContractViolation) as caught:
        resolve_term(_request(), "conversões", catalog=catalog, authorized=_authorized(), on=ON)
    assert caught.value.code is Code.INTENT_AMBIGUOUS


def test_an_ungoverned_term_refuses_without_a_nearest_match() -> None:
    catalog = FixtureCatalog(terms=(_term("instalações", "installs"),))
    with pytest.raises(ContractViolation) as caught:
        resolve_term(_request(), "instalacoes!", catalog=catalog, authorized=_authorized(), on=ON)
    assert caught.value.code is Code.TERM_NOT_GOVERNED


# --- match-kind representability ----------------------------------------------


@pytest.mark.parametrize(
    ("catalog_kind", "expected"),
    [
        (CatalogMatchKind.CANONICAL_NAME, MatchKind.CANONICAL_ID),
        (CatalogMatchKind.LABEL, MatchKind.LABEL),
        (CatalogMatchKind.SYNONYM, MatchKind.SYNONYM_FORMAL),
        (CatalogMatchKind.GLOSSARY, MatchKind.GLOSSARY_TERM),
    ],
)
def test_each_governed_naming_maps_to_its_recorded_match_kind(
    catalog_kind: CatalogMatchKind, expected: MatchKind
) -> None:
    catalog = FixtureCatalog(terms=(_term("termo", "installs", kind=catalog_kind),))
    resolution = resolve_term(_request(), "termo", catalog=catalog, authorized=_authorized(), on=ON)
    assert resolution.matched_via is expected


@pytest.mark.parametrize("catalog_kind", [CatalogMatchKind.DESCRIPTION, CatalogMatchKind.FUZZY])
def test_a_match_this_feature_cannot_record_does_not_resolve(
    catalog_kind: CatalogMatchKind,
) -> None:
    """`FR-006` requires recording *how* it matched.

    A description match is prose about the metric rather than a governed naming
    of it; a fuzzy match is string distance. This feature's closed ``MatchKind``
    declares neither, so it refuses rather than claiming a naming that never
    happened.
    """
    catalog = FixtureCatalog(terms=(_term("algo", "installs", kind=catalog_kind),))
    with pytest.raises(ContractViolation) as caught:
        resolve_term(_request(), "algo", catalog=catalog, authorized=_authorized(), on=ON)
    assert caught.value.code is Code.TERM_NOT_GOVERNED


def test_the_representable_map_covers_only_governed_namings() -> None:
    assert set(REPRESENTABLE_MATCH_KINDS) == {
        CatalogMatchKind.CANONICAL_NAME,
        CatalogMatchKind.LABEL,
        CatalogMatchKind.SYNONYM,
        CatalogMatchKind.GLOSSARY,
    }
    assert CatalogMatchKind.DESCRIPTION not in REPRESENTABLE_MATCH_KINDS
    assert CatalogMatchKind.FUZZY not in REPRESENTABLE_MATCH_KINDS


def test_a_description_only_match_fails_closed() -> None:
    """Prose *about* a metric is not a governed naming of it.

    Named separately from the parametrized case so the failure message says
    which kind regressed.
    """
    catalog = FixtureCatalog(
        terms=(_term("relatório mensal", "installs", kind=CatalogMatchKind.DESCRIPTION),)
    )
    with pytest.raises(ContractViolation) as caught:
        resolve_term(
            _request(), "relatório mensal", catalog=catalog, authorized=_authorized(), on=ON
        )
    assert caught.value.code is Code.TERM_NOT_GOVERNED


def test_a_fuzzy_only_match_fails_closed() -> None:
    """String distance is not a naming at all, and this feature performs none."""
    catalog = FixtureCatalog(terms=(_term("instalacoes", "installs", kind=CatalogMatchKind.FUZZY),))
    with pytest.raises(ContractViolation) as caught:
        resolve_term(_request(), "instalacoes", catalog=catalog, authorized=_authorized(), on=ON)
    assert caught.value.code is Code.TERM_NOT_GOVERNED


def test_neither_unrepresentable_kind_is_mapped_onto_a_neighbouring_one() -> None:
    """The refusal must not be a disguised resolution.

    Mapping ``DESCRIPTION`` to ``label`` or ``FUZZY`` to ``synonym_informal``
    would record a governed naming that never happened, which `FR-006` forbids.
    """
    for kind in (CatalogMatchKind.DESCRIPTION, CatalogMatchKind.FUZZY):
        assert kind not in REPRESENTABLE_MATCH_KINDS
    assert set(REPRESENTABLE_MATCH_KINDS.values()) == {
        MatchKind.CANONICAL_ID,
        MatchKind.LABEL,
        MatchKind.SYNONYM_FORMAL,
        MatchKind.GLOSSARY_TERM,
    }


def test_a_mixed_candidate_set_resolves_to_the_representable_one() -> None:
    """One governed naming plus one unrepresentable match is not an ambiguity.

    `001` returns both as candidates; this feature can offer only the one it can
    truthfully describe, so the outcome is a resolution rather than a choice the
    user cannot be given.
    """
    catalog = FixtureCatalog(
        terms=(
            _term("conversões", "installs", kind=CatalogMatchKind.CANONICAL_NAME),
            _term("conversões", "revenue", kind=CatalogMatchKind.DESCRIPTION),
        )
    )
    outcome = discover("conversões", catalog=catalog, authorized=_authorized(), on=ON)
    refs = candidate_refs(
        outcome, slot=SlotKind.METRIC, content_version="unversioned", language="pt-BR"
    )
    assert [ref.identifier for ref in refs] == ["installs"]


def test_a_mixed_set_of_two_unrepresentable_matches_offers_nothing() -> None:
    """And offering nothing is not the same as resolving one of them."""
    catalog = FixtureCatalog(
        terms=(
            _term("conversões", "installs", kind=CatalogMatchKind.DESCRIPTION),
            _term("conversões", "revenue", kind=CatalogMatchKind.FUZZY),
        )
    )
    outcome = discover("conversões", catalog=catalog, authorized=_authorized(), on=ON)
    assert (
        candidate_refs(
            outcome, slot=SlotKind.METRIC, content_version="unversioned", language="pt-BR"
        )
        == ()
    )

    with pytest.raises(ContractViolation) as caught:
        resolve_term(_request(), "conversões", catalog=catalog, authorized=_authorized(), on=ON)
    assert caught.value.code is Code.INTENT_AMBIGUOUS


def test_the_informal_and_abbreviation_kinds_stay_representable() -> None:
    """`001` does not distinguish them today; the contract still declares them.

    A narrower produced set than the declared one is safe. Removing them would
    be a contract change for an upstream limitation that may not be permanent.
    """
    assert MatchKind.SYNONYM_INFORMAL in set(MatchKind)
    assert MatchKind.SYNONYM_ABBREVIATION in set(MatchKind)
    assert MatchKind.SYNONYM_INFORMAL not in set(REPRESENTABLE_MATCH_KINDS.values())
    assert MatchKind.SYNONYM_ABBREVIATION not in set(REPRESENTABLE_MATCH_KINDS.values())


# --- resolution basis ----------------------------------------------------------


def test_an_enumerated_dimension_carries_membership_standing() -> None:
    assert (
        basis_for_dimension_type(DimensionType.ENUMERATED_TEXT)
        is ResolutionBasis.ENUMERATED_MEMBERSHIP
    )


def test_an_open_text_dimension_carries_shape_standing_only() -> None:
    """`R-5`: there is no set to test membership against."""
    assert basis_for_dimension_type(DimensionType.OPEN_TEXT) is ResolutionBasis.OPEN_TEXT_SHAPE


def test_an_open_text_resolution_proves_less_than_an_enumerated_one() -> None:
    """The whole point of recording the basis."""
    assert is_weaker_than(ResolutionBasis.OPEN_TEXT_SHAPE, ResolutionBasis.ENUMERATED_MEMBERSHIP)
    assert not is_weaker_than(
        ResolutionBasis.ENUMERATED_MEMBERSHIP, ResolutionBasis.OPEN_TEXT_SHAPE
    )


def test_the_date_dimension_has_no_filter_basis() -> None:
    """`002` §4.3.1: not filterable at all. A basis would imply one exists."""
    with pytest.raises(ContractViolation) as caught:
        basis_for_dimension_type(DimensionType.TEMPORAL_DATE)
    assert caught.value.code is Code.TERM_NOT_GOVERNED


def test_the_basis_travels_on_the_resolution() -> None:
    catalog = FixtureCatalog(terms=(_term("brasil", "country"),))
    resolution = resolve_term(
        _request(SlotKind.DIMENSION_VALUE),
        "brasil",
        catalog=catalog,
        authorized=_authorized(),
        on=ON,
        basis=ResolutionBasis.OPEN_TEXT_SHAPE,
    )
    assert resolution.confidence_basis is ResolutionBasis.OPEN_TEXT_SHAPE


# --- role ambiguity ------------------------------------------------------------


def test_google_play_is_both_a_governed_source_and_a_governed_value() -> None:
    """The premise. Without it the ambiguity test would prove nothing."""
    assert "google_play" in FIXTURE_SOURCE_IDS
    assert "google_play" in FIXTURE_DIMENSION_VALUES


def test_an_undetermined_role_refuses_rather_than_choosing() -> None:
    with pytest.raises(ContractViolation) as caught:
        resolve_role(
            "google_play",
            governed_source_ids=FIXTURE_SOURCE_IDS,
            dimension_values=FIXTURE_DIMENSION_VALUES,
            resolved_dimensions=frozenset(),
        )
    assert caught.value.code is Code.SLOT_ROLE_AMBIGUOUS


def test_a_resolved_dimension_settles_the_role() -> None:
    verdict = resolve_role(
        "google_play",
        governed_source_ids=FIXTURE_SOURCE_IDS,
        dimension_values=FIXTURE_DIMENSION_VALUES,
        resolved_dimensions=frozenset({"store"}),
    )
    assert verdict.reading is RoleReading.DIMENSION_VALUE
    assert verdict.slot is SlotKind.DIMENSION_VALUE


def test_a_term_that_is_only_a_source_reads_as_a_source() -> None:
    verdict = resolve_role(
        "website",
        governed_source_ids=FIXTURE_SOURCE_IDS,
        dimension_values=FIXTURE_DIMENSION_VALUES,
        resolved_dimensions=frozenset(),
    )
    assert verdict.reading is RoleReading.SOURCE
    assert verdict.slot is SlotKind.SOURCE


def test_a_value_with_no_resolved_dimension_refuses() -> None:
    """`permitted_values` is a property of the dimension, not of the question."""
    with pytest.raises(ContractViolation) as caught:
        resolve_role(
            "android",
            governed_source_ids=FIXTURE_SOURCE_IDS,
            dimension_values=FIXTURE_DIMENSION_VALUES,
            resolved_dimensions=frozenset(),
        )
    assert caught.value.code is Code.TERM_NOT_GOVERNED


def test_a_term_that_is_neither_refuses() -> None:
    with pytest.raises(ContractViolation) as caught:
        resolve_role(
            "nada",
            governed_source_ids=FIXTURE_SOURCE_IDS,
            dimension_values=FIXTURE_DIMENSION_VALUES,
            resolved_dimensions=frozenset({"store"}),
        )
    assert caught.value.code is Code.TERM_NOT_GOVERNED


# --- operators -----------------------------------------------------------------


@pytest.mark.parametrize("operator", sorted(GOVERNED_OPERATORS))
def test_each_governed_operator_is_accepted(operator: str) -> None:
    assert require_governed_operator(operator) is GovernedOperator(operator)


def test_the_allowlist_is_002s_closed_set() -> None:
    assert {"eq", "ne", "in", "not_in", "between"} == GOVERNED_OPERATORS


@pytest.mark.parametrize(
    "operator", ["gt", "gte", "lt", "lte", "contains", "starts_with", "regex", "like", "EQ"]
)
def test_an_operator_outside_the_matrix_abstains(operator: str) -> None:
    """Never approximated with a permitted one."""
    with pytest.raises(ContractViolation) as caught:
        require_governed_operator(operator)
    assert caught.value.code is Code.CALCULATION_NOT_SUPPORTED


def test_no_ungoverned_operator_maps_to_a_governed_one() -> None:
    """The approximation path does not exist, checked as an absence of mapping.

    "acima de 1000" has an obvious near-translation into ``between(1000, ...)``
    and the ceiling would be invented — a number the user never gave, in an
    answer that looks correct.
    """
    for ungoverned in ("gt", "gte", "contains", "regex"):
        with pytest.raises(ContractViolation):
            require_governed_operator(ungoverned)


# --- candidate references are governed pointers only ---------------------------


def test_candidate_refs_carry_identifiers_and_governed_pointers_only() -> None:
    catalog = FixtureCatalog(
        terms=(_term("conversões", "installs"), _term("conversões", "signups"))
    )
    outcome = discover("conversões", catalog=catalog, authorized=_authorized(), on=ON)
    refs = candidate_refs(
        outcome, slot=SlotKind.METRIC, content_version="unversioned", language="pt-BR"
    )

    assert [ref.identifier for ref in refs] == ["installs", "signups"]
    for ref in refs:
        rendered = ref.model_dump_json()
        assert "conversões" not in rendered, "the question's wording reached a candidate"
        assert "score" not in rendered
        assert "value" not in rendered


def test_candidate_ordering_is_stable_across_repeats() -> None:
    catalog = FixtureCatalog(
        terms=(
            _term("conversões", "signups", score=0.9),
            _term("conversões", "installs", score=0.9),
        )
    )
    first = candidate_refs(
        discover("conversões", catalog=catalog, authorized=_authorized(), on=ON),
        slot=SlotKind.METRIC,
        content_version="unversioned",
        language="pt-BR",
    )
    second = candidate_refs(
        discover("conversões", catalog=catalog, authorized=_authorized(), on=ON),
        slot=SlotKind.METRIC,
        content_version="unversioned",
        language="pt-BR",
    )
    assert first == second
    assert [ref.identifier for ref in first] == ["installs", "signups"]


def test_a_resolved_outcome_produces_no_candidate_list() -> None:
    """A single resolution is not a choice to offer."""
    catalog = FixtureCatalog(terms=(_term("instalações", "installs"),))
    outcome = discover("instalações", catalog=catalog, authorized=_authorized(), on=ON)
    assert (
        candidate_refs(
            outcome, slot=SlotKind.METRIC, content_version="unversioned", language="pt-BR"
        )
        == ()
    )


def test_an_unrepresentable_candidate_is_not_offered() -> None:
    """A candidate this feature cannot say how it matched is one it cannot offer."""
    catalog = FixtureCatalog(
        terms=(
            _term("conversões", "installs"),
            _term("conversões", "signups", kind=CatalogMatchKind.DESCRIPTION),
        )
    )
    outcome = discover("conversões", catalog=catalog, authorized=_authorized(), on=ON)
    refs = candidate_refs(
        outcome, slot=SlotKind.METRIC, content_version="unversioned", language="pt-BR"
    )
    assert [ref.identifier for ref in refs] == ["installs"]


# --- candidate precedence ------------------------------------------------------


def test_an_exact_canonical_match_is_not_displaced_by_a_weaker_one() -> None:
    """`001`'s ordering: score, then match kind, then identifier.

    Reused rather than re-derived — a key of this feature's own could let a
    synonym outrank a canonical identifier.
    """
    catalog = FixtureCatalog(
        terms=(
            _term("installs", "signups", kind=CatalogMatchKind.SYNONYM, score=1.0),
            _term("installs", "installs", kind=CatalogMatchKind.CANONICAL_NAME, score=1.0),
        )
    )
    outcome = discover("installs", catalog=catalog, authorized=_authorized(), on=ON)
    refs = candidate_refs(
        outcome, slot=SlotKind.METRIC, content_version="unversioned", language="pt-BR"
    )
    assert refs[0].identifier == "installs"


def test_a_higher_score_outranks_a_more_exact_kind() -> None:
    """Score first, then kind — `001`'s ``sort_key``, unchanged.

    Asserted so the precedence is a documented property rather than an artefact
    nobody checked.
    """
    hit = Candidate(metric_id="a", kind=CatalogMatchKind.SYNONYM, score=0.99, matched_term="x")
    weaker = Candidate(
        metric_id="b", kind=CatalogMatchKind.CANONICAL_NAME, score=0.50, matched_term="x"
    )
    assert sorted((weaker, hit), key=lambda c: c.sort_key)[0] is hit
