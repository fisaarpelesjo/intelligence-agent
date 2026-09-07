"""Completion-evidence tests for T044, T045, T046.

T044 evidence: deterministic resolution of the seed synonym set, including the
informal and misspelled forms present in the seed.
T045 evidence: three distinct response shapes; never a silent single resolution.
T046 evidence: closed union return type.

**None of this proves SC-002.** SC-002 is measured over at least 50 real business
phrasings, and that corpus is D-11 (T107), still open. What is proven here is
functional behaviour over the governed seed — nothing about accuracy against
phrasings nobody has collected.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType, TagDenial
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.loader.projection import MetricView, PendingStub
from semantic_catalog.search.api import AccessContext, CatalogApi, authorize
from semantic_catalog.search.outcomes import (
    Ambiguous,
    NotGoverned,
    Resolved,
    resolve_outcome,
)
from semantic_catalog.search.resolve import (
    MatchKind,
    SearchIndex,
    build_index,
    normalise,
    resolve,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
SEMANTIC = REPO / "semantic"
COMMIT = "0000000"
ON = date(2026, 8, 11)


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(
        SEMANTIC,
        current_commit=COMMIT,
        on=ON,
        source_commits={"subscription_daily": COMMIT},
    )


@pytest.fixture(scope="module")
def api(bundle: Bundle) -> CatalogApi:
    return CatalogApi.from_bundle(bundle)


@pytest.fixture(scope="module")
def index(bundle: Bundle) -> SearchIndex:
    return build_index(bundle.internal)


def _access() -> AccessContext:
    return AccessContext(PrincipalType.USER, "default", ON)


# --- T044 normalisation and resolution -------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Usuários ativos", "usuarios ativos"),
        ("RETENÇÃO D7", "retencao d7"),
        ("  sessões,  ", "sessoes"),
        ("Nota média!", "nota media"),
    ],
)
def test_normalisation_folds_case_accents_and_punctuation(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


@pytest.mark.parametrize(
    "query, expected",
    [
        ("active_users", "active_users"),
        ("usuários ativos", "active_users"),
        ("usuarios ativos", "active_users"),  # accent-stripped
        ("quantos usaram o app", "active_users"),  # informal, authored
        ("dau", "active_users"),  # abbreviation, authored
        ("novos usuários", "new_users"),
        ("usuarios novos", "new_users"),  # informal, authored
        ("sessões", "sessions"),
        ("acessos", "sessions"),
        ("downloads", "downloads"),
        ("baixados", "downloads"),
        ("instalações", "installs"),
        ("instalacoes", "installs"),  # misspelling authored in the seed
        ("taxa de falhas", "crash_rate"),
        ("crash rate", "crash_rate"),
        ("nota média", "average_rating"),
        ("nota da loja", "average_rating"),
        ("rating", "average_rating"),
        ("avaliações", "review_count"),
        ("comentários", "review_count"),
        ("retenção d7", "retention_rate_d7"),
        ("retencao d7", "retention_rate_d7"),  # misspelling authored in the seed
        ("retenção d1", "retention_rate_d1"),
        ("retenção d30", "retention_rate_d30"),
    ],
)
def test_every_seed_synonym_resolves_to_its_canonical_identifier(
    index: SearchIndex, query: str, expected: str
) -> None:
    outcome = resolve_outcome(query, index)
    assert isinstance(outcome, Resolved), f"{query!r} -> {outcome}"
    assert outcome.metric_id == expected


def test_resolution_is_deterministic_across_repeated_calls(index: SearchIndex) -> None:
    for _ in range(5):
        assert [c.metric_id for c in resolve("usuários ativos", index)] == ["active_users"]
        assert [c.metric_id for c in resolve("retencao d7", index)] == ["retention_rate_d7"]


def test_a_typo_resolves_by_fuzzy_match_and_reports_it_as_fuzzy(index: SearchIndex) -> None:
    """Tolerant of misspellings the seed does not author (FR-015)."""
    candidates = resolve("usuarios ativoss", index)
    assert candidates
    assert candidates[0].metric_id == "active_users"
    assert candidates[0].kind is MatchKind.FUZZY
    assert candidates[0].score < 1.0


def test_an_exact_match_never_falls_through_to_fuzzy(index: SearchIndex) -> None:
    candidates = resolve("downloads", index)
    assert [c.kind for c in candidates] == [MatchKind.CANONICAL_NAME]
    assert candidates[0].score == 1.0


def test_an_empty_query_resolves_to_nothing(index: SearchIndex) -> None:
    assert resolve("   ", index) == ()
    assert isinstance(resolve_outcome("   ", index), NotGoverned)


# --- T045 the three shapes -------------------------------------------------


def test_an_unmatched_term_is_an_explicit_non_answer(index: SearchIndex) -> None:
    outcome = resolve_outcome("receita recorrente mensal", index)
    assert isinstance(outcome, NotGoverned)
    assert outcome.query == "receita recorrente mensal"


def test_a_term_claimed_by_several_metrics_returns_all_candidates(index: SearchIndex) -> None:
    """FR-016: never a silent single resolution."""
    outcome = resolve_outcome("retencao d", index)
    assert isinstance(outcome, Ambiguous), outcome
    assert set(outcome.metric_ids) >= {"retention_rate_d1", "retention_rate_d7"}
    assert len(outcome.candidates) > 1


def test_the_three_shapes_are_mutually_exclusive(index: SearchIndex) -> None:
    shapes = {
        type(resolve_outcome(q, index))
        for q in ("downloads", "retencao d", "receita recorrente mensal")
    }
    assert shapes == {Resolved, Ambiguous, NotGoverned}


# --- T046 closed union and access gating -----------------------------------


def test_get_metric_returns_a_pending_stub_for_a_pending_metric(api: CatalogApi) -> None:
    result = api.get_metric("retention_rate_d7", access=_access())
    assert isinstance(result, PendingStub)
    assert result.status == "pending"


def test_get_metric_returns_not_governed_for_an_unknown_name(api: CatalogApi) -> None:
    result = api.get_metric("receita_recorrente", access=_access())
    assert isinstance(result, NotGoverned)


def test_get_metric_returns_only_members_of_the_closed_union(api: CatalogApi) -> None:
    for name in ("active_users", "retention_rate_d1", "nao_existe"):
        result = api.get_metric(name, access=_access())
        assert isinstance(result, MetricView | PendingStub | NotGoverned)


def test_an_unauthorised_metric_is_indistinguishable_from_a_missing_one(
    api: CatalogApi,
) -> None:
    """A refusal must not let a caller enumerate what exists."""
    denied = AccessContext(PrincipalType.USER, "finance", ON)
    assert isinstance(api.get_metric("active_users", access=denied), NotGoverned)
    assert isinstance(api.get_metric("nao_existe", access=denied), NotGoverned)


def test_search_filters_hits_by_access(api: CatalogApi) -> None:
    assert api.search("usuários ativos", access=_access())
    denied = AccessContext(PrincipalType.USER, "finance", ON)
    assert api.search("usuários ativos", access=denied) == ()


def test_search_returns_pending_stubs_not_raw_models(api: CatalogApi) -> None:
    hits = api.search("retenção d7", access=_access())
    assert len(hits) == 1
    assert hits[0].is_pending
    assert isinstance(hits[0].projection, PendingStub)


def test_access_filtering_happens_before_the_shape_is_decided(api: CatalogApi) -> None:
    denied = AccessContext(PrincipalType.USER, "finance", ON)
    assert isinstance(api.resolve("retencao d", access=denied), NotGoverned)


def test_an_absent_access_registry_denies_everything() -> None:
    assert authorize("standard", None, _access()) is TagDenial.UNKNOWN


def test_a_service_principal_is_authorised_by_the_governed_registry(api: CatalogApi) -> None:
    context = AccessContext(PrincipalType.SERVICE_PRINCIPAL, "default", ON)
    assert isinstance(api.get_metric("active_users", access=context), PendingStub)


def test_search_does_not_prove_sc_002(api: CatalogApi) -> None:
    """Guard against a later reading of this suite as measured quality.

    The seed carries far fewer than the 50 real phrasings SC-002 requires, and
    none of them came from a user. D-11 (T107) is what makes SC-002 measurable.
    """
    seed_phrasings = {
        synonym.text
        for metric in api.bundle.internal.metrics.values()
        for synonym in metric.synonyms
    }
    assert len(seed_phrasings) < 50
