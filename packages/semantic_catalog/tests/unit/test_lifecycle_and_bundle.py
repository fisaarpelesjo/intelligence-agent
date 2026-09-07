"""Completion-evidence tests for T040, T041, T043.

T040 evidence: clearing a required field flips published → pending.
T041 evidence: the serialised public bundle contains none of the withheld fields.
T043 evidence: two projections; content-addressed, stable release id.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.approval import PendingVisibilityApprovals
from semantic_catalog.contracts.metric import Lifecycle, Metric
from semantic_catalog.contracts.policy import CatalogPolicy, PolicyUnresolvableError
from semantic_catalog.loader.bundle import (
    build_bundle,
    compute_release_id,
    serialise_authored,
    serialise_public,
)
from semantic_catalog.loader.lifecycle import PendingReason, derive_lifecycle
from semantic_catalog.loader.load import LoadedCatalog, load_catalog
from semantic_catalog.loader.projection import (
    MetricView,
    PendingCandidates,
    PendingStub,
    pending_candidates,
    project_metric,
)
from semantic_catalog.loader.visibility import resolve_visibility

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
SEMANTIC = REPO / "semantic"
COMMIT = "0000000"
ON = date(2026, 8, 11)

COMPLETE_METRIC: dict[str, object] = {
    "catalog_schema_version": 1,
    "kind": "metric",
    "name": "sessions",
    "owner": "product_analytics",
    "access": "standard",
    "grain_family": "day",
    "versions": [
        {
            "version": 1,
            "effective_from": date(2026, 8, 11),
            "source_view": "semantic.product_daily_metrics",
            "grain": "date x platform",
            "aggregation": "sum",
            "additivity": "additive",
            "unit": "sessions",
            "time_dimension": "date",
            "calculation_basis": "Sessões iniciadas no dia.",
            "content": {
                "lang": "pt-BR",
                "label": "Sessões",
                "description": "Número de sessões iniciadas no dia.",
            },
        }
    ],
}

COHORT_METRIC: dict[str, object] = {
    **COMPLETE_METRIC,
    "name": "retention_rate_d7",
    "grain_family": "cohort",
    "retention": {
        "window_days": 7,
        "retention_style": "exact_day",
        "cohort_assignment": "first_eligible_activity",
        "cohort_timezone": "America/Sao_Paulo",
        "eligible_event": "Evento elegível de teste.",
        "identity_rule": "Regra de identidade de teste.",
        "numerator": "Usuários da coorte que retornam no dia 7.",
        "denominator": "Usuários da coorte.",
        "min_maturity_days": 7,
    },
}


def _metric(payload: dict[str, object]) -> Metric:
    return Metric.model_validate(payload)


# --- T040 lifecycle derivation --------------------------------------------


def test_a_complete_owned_approved_metric_is_published() -> None:
    state = derive_lifecycle(_metric(COMPLETE_METRIC), owner_known=True, publication_eligible=True)
    assert state.lifecycle is Lifecycle.PUBLISHED
    assert state.reasons == ()
    assert state.is_requestable


def test_clearing_a_required_field_flips_published_to_pending() -> None:
    """T040 evidence, stated exactly."""
    metric = _metric(COHORT_METRIC)
    assert metric.retention is not None
    before = derive_lifecycle(metric, owner_known=True, publication_eligible=True)
    assert before.lifecycle is Lifecycle.PUBLISHED

    cleared = metric.model_copy(
        update={"retention": metric.retention.model_copy(update={"identity_rule": None})}
    )
    after = derive_lifecycle(cleared, owner_known=True, publication_eligible=True)
    assert after.lifecycle is Lifecycle.PENDING
    assert after.missing_fields == ("retention.identity_rule",)
    assert PendingReason.REQUIRED_FIELDS_UNSET in after.reasons
    assert not after.is_requestable


def test_an_unresolvable_owner_makes_a_complete_metric_pending() -> None:
    state = derive_lifecycle(_metric(COMPLETE_METRIC), owner_known=False, publication_eligible=True)
    assert state.lifecycle is Lifecycle.PENDING
    assert state.reasons == (PendingReason.OWNER_UNRESOLVED,)


def test_an_unapproved_source_makes_a_complete_metric_pending() -> None:
    state = derive_lifecycle(_metric(COMPLETE_METRIC), owner_known=True, publication_eligible=False)
    assert state.lifecycle is Lifecycle.PENDING
    assert state.reasons == (PendingReason.SOURCE_NOT_APPROVED,)


def test_deprecation_is_terminal_and_never_walks_back_to_pending() -> None:
    """A retired metric must not reappear as "on its way in"."""
    metric = _metric({**COMPLETE_METRIC, "deprecation": {"deprecated_from": date(2026, 9, 1)}})
    state = derive_lifecycle(metric, owner_known=True, publication_eligible=False)
    assert state.lifecycle is Lifecycle.DEPRECATED
    assert PendingReason.SOURCE_NOT_APPROVED in state.reasons
    assert not state.is_requestable


def test_missing_fields_are_names_never_values() -> None:
    metric = _metric(COHORT_METRIC)
    assert metric.retention is not None
    cleared = metric.model_copy(
        update={
            "retention": metric.retention.model_copy(
                update={"eligible_event": None, "identity_rule": None}
            )
        }
    )
    state = derive_lifecycle(cleared, owner_known=True, publication_eligible=True)
    assert state.missing_fields == ("retention.eligible_event", "retention.identity_rule")
    assert "Evento elegível de teste." not in str(state)


# --- T041 projection -------------------------------------------------------


def _no_approvals() -> PendingVisibilityApprovals:
    return PendingVisibilityApprovals(
        catalog_schema_version=1, kind="pending_visibility_approvals", approvals=()
    )


def _policy() -> CatalogPolicy:
    catalog = load_catalog(SEMANTIC)
    return catalog.policies[0]


def test_a_published_metric_projects_in_full() -> None:
    metric = _metric(COMPLETE_METRIC)
    state = derive_lifecycle(metric, owner_known=True, publication_eligible=True)
    view = project_metric(
        metric,
        state,
        visibility=resolve_visibility(
            metric.name, policy=_policy(), approvals=_no_approvals(), current_commit=COMMIT, on=ON
        ),
    )
    assert isinstance(view, MetricView)
    assert view.to_public_dict()["status"] == "published"
    assert "calculation_basis" in json.dumps(view.to_public_dict(), ensure_ascii=False)


def test_a_pending_metric_projects_to_the_six_field_stub() -> None:
    metric = _metric(COHORT_METRIC)
    assert metric.retention is not None
    cleared = metric.model_copy(
        update={"retention": metric.retention.model_copy(update={"identity_rule": None})}
    )
    state = derive_lifecycle(cleared, owner_known=True, publication_eligible=True)
    stub = project_metric(
        cleared,
        state,
        visibility=resolve_visibility(
            cleared.name, policy=_policy(), approvals=_no_approvals(), current_commit=COMMIT, on=ON
        ),
    )
    assert isinstance(stub, PendingStub)
    assert stub.to_public_dict() == {
        "name": "retention_rate_d7",
        "status": "pending",
        "missing_fields": ["retention.identity_rule"],
        "owner": "product_analytics",
    }


def test_an_owner_that_does_not_resolve_is_omitted_not_defaulted() -> None:
    metric = _metric(COMPLETE_METRIC)
    state = derive_lifecycle(metric, owner_known=False, publication_eligible=True)
    stub = project_metric(
        metric,
        state,
        visibility=resolve_visibility(
            metric.name, policy=_policy(), approvals=_no_approvals(), current_commit=COMMIT, on=ON
        ),
        owner_known=False,
    )
    assert isinstance(stub, PendingStub)
    assert stub.owner is None
    assert "owner" not in stub.to_public_dict()


def test_the_candidate_date_has_no_authored_home_today() -> None:
    """Documented deviation: no approved contract carries a committed date."""
    candidates = pending_candidates(_metric(COMPLETE_METRIC))
    assert candidates.public_name == "Sessões"
    assert candidates.expected_available_from is None


def test_candidates_are_never_exposed_without_an_approval() -> None:
    metric = _metric(COMPLETE_METRIC)
    state = derive_lifecycle(metric, owner_known=True, publication_eligible=False)
    stub = project_metric(
        metric,
        state,
        visibility=resolve_visibility(
            metric.name, policy=_policy(), approvals=_no_approvals(), current_commit=COMMIT, on=ON
        ),
        candidates=PendingCandidates(
            public_name="Sessões", expected_available_from=date(2027, 1, 1)
        ),
    )
    assert isinstance(stub, PendingStub)
    assert stub.public_name is None
    assert stub.expected_available_from is None


# --- T043 bundle -----------------------------------------------------------


def test_the_bundle_carries_both_projections() -> None:
    bundle = build_bundle(
        SEMANTIC,
        current_commit=COMMIT,
        on=ON,
        source_commits={"subscription_daily": COMMIT},
    )
    # TWELVE since 2026-08-26, on both projections, which is the point of the
    # assertion: the two must agree on the count whatever it is.
    #: RE-DERIVADO em 2026-08-30: era `== 12` e foi para 31 com a `T829`. As duas projecoes
    #: tem de concordar na contagem QUALQUER QUE ELA SEJA, que e o que o comentario acima
    #: ja dizia -- o numero escrito e que contradizia a frase.
    assert bundle.public, "the public projection is empty"
    assert len(bundle.public) == len(bundle.internal.metrics)
    assert bundle.internal.sources  # internal keeps everything
    assert bundle.pending == tuple(sorted(bundle.public))
    assert bundle.published == ()


def test_the_release_id_is_a_content_hash_of_the_public_bundle() -> None:
    bundle = build_bundle(
        SEMANTIC,
        current_commit=COMMIT,
        on=ON,
        source_commits={"subscription_daily": COMMIT},
    )
    assert bundle.release_id == compute_release_id(bundle.public, bundle.internal)
    assert bundle.release_id.startswith("sha256:")
    assert len(bundle.release_id) == len("sha256:") + 64


def test_the_release_id_changes_when_public_content_changes() -> None:
    bundle = build_bundle(
        SEMANTIC,
        current_commit=COMMIT,
        on=ON,
        source_commits={"subscription_daily": COMMIT},
    )
    mutated = dict(bundle.public)
    stub = mutated["sessions"]
    assert isinstance(stub, PendingStub)
    mutated["sessions"] = PendingStub(
        name=stub.name,
        status="pending",
        missing_fields=("something.else",),
        owner=stub.owner,
    )
    assert compute_release_id(mutated, bundle.internal) != bundle.release_id


def test_serialisation_is_canonical_and_reproducible() -> None:
    bundle = build_bundle(
        SEMANTIC,
        current_commit=COMMIT,
        on=ON,
        source_commits={"subscription_daily": COMMIT},
    )
    first = serialise_public(bundle.public)
    second = serialise_public(dict(reversed(list(bundle.public.items()))))
    assert first == second, "key order must not affect the serialised bytes"
    assert json.loads(first)


def test_a_build_without_an_effective_policy_fails_closed() -> None:
    catalog = load_catalog(SEMANTIC)
    empty = replace(catalog, policies=())
    # No `source_commits` here, and the reason is the CALL ORDER rather than a guess about
    # this catalog: `build_bundle` calls `_effective_policy` before `derive_lifecycles`, so
    # this raises before the freshness path runs and the comparand is never reached. Stating
    # a commit would state one nothing reads.
    #
    # **The previous version of this claim was made by checking a directory that does not
    # exist**, which returned 'no approvals file' and was reported as a proof. That is why
    # this one names the control flow, which is checkable in the source.
    with pytest.raises(PolicyUnresolvableError):
        build_bundle(empty, current_commit=COMMIT, on=ON)


def test_a_build_dated_before_the_policy_fails_closed() -> None:
    # Same reason as above: the policy is unresolvable on this date, so it raises before
    # the freshness path.
    with pytest.raises(PolicyUnresolvableError):
        build_bundle(SEMANTIC, current_commit=COMMIT, on=date(2026, 8, 10))


# --- OD-124 (a): the release id covers the AUTHORED catalog, not only the public bundle --------
#
# Measured 2026-09-05 against a copy of `semantic/`, built with the commit the freshness approval
# names (`anomaly.py:349` reads the same one; with HEAD every metric is pending and the measurement
# is blind): **45 of 80 files could be deleted without moving the id** — every access tag, source,
# dimension, comparability rule, glossary term, reason message, definition approval and visibility
# approval. `release_state.py` refuses a repeated id as "the same content — nothing to publish", so
# an access-tag fix that flips ALLOW to DENY could not be published as the corrective release
# FR-075 demands. The nodes below are written with the two catalogs DIFFERING, and the last one is
# the instrument itself: no file the loader READS is silently deletable any more. READMEs and
# `examples/` are not loaded and stay outside the id on purpose.


def _production_commit(catalog: LoadedCatalog) -> str:
    approvals = catalog.freshness_approvals
    assert approvals is not None and approvals.approvals
    return approvals.approvals[0].source_commit


@pytest.fixture(scope="module")
def authored() -> LoadedCatalog:
    return load_catalog(SEMANTIC)


@pytest.mark.parametrize(
    "registry",
    [
        "access_tags",
        "approvals",
        "comparability_rules",
        "definition_approvals",
        "dimensions",
        "glossary_terms",
        "reason_messages",
        "sources",
    ],
)
def test_dropping_a_registry_the_public_bundle_never_shows_still_moves_the_release_id(
    authored: LoadedCatalog, registry: str
) -> None:
    """Each of these was deletable with the id unchanged on 2026-09-05; each is a decision input."""
    commit = _production_commit(authored)
    before = build_bundle(authored, current_commit=commit, on=date.today())
    empty: object = {} if isinstance(getattr(authored, registry), Mapping) else None
    after = build_bundle(
        replace(authored, **{registry: empty}), current_commit=commit, on=date.today()
    )
    assert getattr(authored, registry), registry  # the fixture must have something to drop
    assert after.release_id != before.release_id, registry


def test_an_access_tag_change_moves_the_id_while_the_public_bundle_stays_identical(
    authored: LoadedCatalog,
) -> None:
    """The exact shape the debt was found in: ALLOW to DENY with byte-identical public output."""
    commit = _production_commit(authored)
    before = build_bundle(authored, current_commit=commit, on=date.today())
    after = build_bundle(
        replace(authored, access_tags=None), current_commit=commit, on=date.today()
    )
    assert serialise_public(after.public) == serialise_public(before.public)
    assert after.release_id != before.release_id


def test_the_same_authored_catalog_still_rebuilds_to_the_same_id(authored: LoadedCatalog) -> None:
    """The first half of the contract survives the second: a rebuild is provably a no-op.

    This node measures idempotence INSIDE one process. The guarantee the ledger needs is across
    processes and hash seeds; that was measured by hand on 2026-09-05 (two interpreters, same
    ``serialise_authored`` sha, 117.448 bytes) and is not what this assertion covers.
    """
    commit = _production_commit(authored)
    first = build_bundle(authored, current_commit=commit, on=date.today())
    second = build_bundle(load_catalog(SEMANTIC), current_commit=commit, on=date.today())
    assert first.release_id == second.release_id
    assert serialise_authored(authored) == serialise_authored(second.internal)


def test_the_authored_serialisation_leaves_machine_paths_out(authored: LoadedCatalog) -> None:
    """``files`` holds absolute paths; an id that depended on them would differ per checkout."""
    text = serialise_authored(authored)
    assert str(SEMANTIC) not in text
    assert "files" not in json.loads(text)


def test_no_file_the_loader_reads_is_deletable_without_moving_the_id(
    authored: LoadedCatalog, tmp_path: Path
) -> None:
    """The instrument that found the debt, kept as a node.

    On 2026-09-05, 45 of the 80 files under ``semantic/`` were deletable with the id unchanged:
    36 of the 71 the loader reads, plus the 9 READMEs that are outside ``catalog.files`` and
    outside this claim. ZERO of 71 then, and ZERO of 72 since ``plan.yaml`` (2026-09-05).

    Deleting a loaded file must either break the build or move the id. Files the loader does not
    read (READMEs, ``examples/``) are outside ``catalog.files`` and outside this claim.
    """
    import shutil

    root = tmp_path / "semantic"
    shutil.copytree(SEMANTIC, root)
    commit = _production_commit(authored)
    base = build_bundle(root, current_commit=commit, on=date.today())
    loaded = sorted({p.resolve().relative_to(SEMANTIC.resolve()) for p in authored.files.values()})
    #: 72 since 2026-09-05: `semantic/dimensions/plan.yaml` (013 F5) joined the 71 measured that
    #: morning; 73 the same afternoon with `semantic/dimensions/gateway.yaml` (013 F6, OD-128).
    #: The nine READMEs are still the files the loader does not read.
    assert len(loaded) == 73, len(loaded)
    silent: list[str] = []
    for rel in loaded:
        path = root / rel
        data = path.read_bytes()
        path.unlink()
        try:
            rebuilt = build_bundle(root, current_commit=commit, on=date.today())
        except Exception:
            continue
        else:
            if rebuilt.release_id == base.release_id:
                silent.append(rel.as_posix())
        finally:
            path.write_bytes(data)
    assert silent == [], silent


def test_one_field_in_one_access_tag_moves_the_id_with_the_public_bundle_byte_identical(
    authored: LoadedCatalog,
) -> None:
    """Not a dropped registry — ONE field in ONE tag, the smallest authored change that flips a
    decision (a deprecated tag denies where it allowed). Written with the two catalogs DIFFERING."""
    assert authored.access_tags is not None and authored.access_tags.tags
    first, *rest = authored.access_tags.tags
    assert first.deprecated_from is None
    edited = first.model_copy(update={"deprecated_from": date(2026, 1, 1)})
    registry = authored.access_tags.model_copy(update={"tags": (edited, *rest)})
    commit = _production_commit(authored)
    before = build_bundle(authored, current_commit=commit, on=date.today())
    after = build_bundle(
        replace(authored, access_tags=registry), current_commit=commit, on=date.today()
    )
    assert serialise_public(after.public) == serialise_public(before.public)
    assert after.release_id != before.release_id
