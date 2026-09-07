"""The authored catalog itself must be fail-closed — T113 evidence.

The other tests prove the mechanism works on fixtures. This one points it at the
real `semantic/` tree and asserts the outcome that matters right now: while D-1,
D-2 and D-8 are open, **nothing is publishable**, and no unapproved business
value is reachable by a consumer.

If this test starts failing because something became publishable, that is either
a genuine approval landing in `freshness-approvals.yaml` — in which case update
the expectation deliberately — or a control that stopped working.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.loader.load import LoadedCatalog, load_catalog
from semantic_catalog.validation.l1_schema import validate_tree
from semantic_catalog.validation.l2_referential import validate_references
from semantic_catalog.validation.publication import (
    metric_eligibilities,
    publishable_source_ids,
    source_eligibility,
)

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[4]
SEMANTIC = REPO / "semantic"
CODEOWNERS = REPO / ".github" / "CODEOWNERS"

# Any commit id works: with an empty registry no approval is ever consulted.
ANY_COMMIT = "0000000"
TODAY = date(2026, 8, 11)


@pytest.fixture(scope="module")
def catalog() -> LoadedCatalog:
    return load_catalog(SEMANTIC)


def test_the_authored_tree_is_structurally_valid(catalog: LoadedCatalog) -> None:
    l1 = validate_tree(SEMANTIC)
    l2 = validate_references(catalog, codeowners=CODEOWNERS)
    assert l1.is_valid(), l1.render()
    assert l2.is_valid(), l2.render()


def test_the_freshness_registry_is_present_and_empty(catalog: LoadedCatalog) -> None:
    """**The registry stopped being empty on 2026-08-26, and this is the re-derivation.**

    It held zero approvals because `D-1` was open, and *"fabricating an approval would
    be inventing governance"*. The owner then signed one — `subscription_daily`, his
    literal words *"Autorizar as duas (Recomendado)"* recorded in the governed channel
    at 17:17:40Z — so the count changed and the **property did not**.

    The property was never *"the registry is empty"*. Empty was the shape the property
    took while nobody had signed. **What it protects is that no approval is invented**:
    every entry names a source that exists, a role the policy permits, and the commit
    whose content it approves. Those are asserted below, over every entry rather than
    over the one that exists today.

    The node keeps its name for the reason its sibling gives: ADR 0017's baseline
    admits zero renames, and buying an accurate name by weakening a gate is the trade
    this repository refused once already.
    """
    assert catalog.freshness_approvals is not None

    approvals = catalog.freshness_approvals.approvals
    assert len(approvals) == 1, (
        "one approval was signed on 2026-08-26; a different count is a governed decision "
        "that must be re-derived here rather than absorbed"
    )

    source_ids = frozenset(catalog.sources)
    # Annotated, and the empty branch is a `frozenset` rather than a `set`: the two arms had
    # different types, so the union was `frozenset[str] | set[Unknown]` and the membership tests
    # below were being made against something partially unknown. The behaviour is unchanged and
    # deliberately fail-closed -- no owners file means no role passes.
    owner_ids: frozenset[str] = (
        frozenset(owner.id for owner in catalog.owners.owners) if catalog.owners else frozenset()
    )
    for approval in approvals:
        assert approval.source_id in source_ids, approval.source_id
        assert approval.approved_by_role in owner_ids, approval.approved_by_role
        assert len(approval.source_commit) >= 7, approval.source_commit


def test_all_six_sources_are_unpublishable(catalog: LoadedCatalog) -> None:
    # SEVEN sources and TWELVE metrics since 2026-08-26, not six and eleven.
    # `subscription_daily` and `new_trials` were declared over
    # `semantic.subscription_daily_metrics`, the first view in this repository
    # built over data that was measured to exist. **The count is amended and the
    # PROPERTY is untouched**: the seventh source carries no freshness approval,
    # so it is unpublishable exactly like the six before it, and the assertion
    # below still walks every source rather than a subset.
    #
    # The node keeps its name: ADR 0017's baseline admits zero renames, and
    # buying an accurate name by weakening that gate is the trade this
    # repository refused once already.
    #
    # **AND ONE SOURCE NOW CARRIES AN APPROVAL, WHICH THIS NODE STILL FINDS
    # UNPUBLISHABLE — say why, or the next reader reads a lucky pass.**
    # `subscription_daily` was signed on 2026-08-26, and it is refused here
    # because `ANY_COMMIT` is not the commit the approval names: an approval binds
    # to the content it approved, so it does not leak to an arbitrary commit. That
    # is the assertion this node is now making, and it is a stronger statement than
    # the one it made while the registry was empty.
    assert len(catalog.sources) == 7
    for source_id, model in sorted(catalog.sources.items()):
        eligibility = source_eligibility(
            model,
            catalog.freshness_approvals,
            source_content_commit=ANY_COMMIT,
            on=TODAY,
        )
        assert not eligibility.publishable, source_id
        assert eligibility.denial is not None
        assert not eligibility.may_participate_in_decisions
        assert not eligibility.may_disclose_delay_tolerance
        assert not eligibility.contributes_to_fingerprint

    assert (
        publishable_source_ids(
            catalog,
            source_commits=dict.fromkeys(catalog.sources, ANY_COMMIT),
            on=TODAY,
        )
        == frozenset()
    )


def test_every_metric_is_unpublishable_while_its_sources_are(catalog: LoadedCatalog) -> None:
    results = metric_eligibilities(
        catalog,
        source_commits=dict.fromkeys(catalog.sources, ANY_COMMIT),
        on=TODAY,
    )
    # TWELVE since 2026-08-26. `new_trials` is the twelfth, and it is
    # unpublishable for the same reason as the eleven: its source has no
    # approval. The assertion that NOTHING is publishable is unchanged.
    #: RE-DERIVADO em 2026-08-30, nao apagado. Era `== 12`, e doze era a metade fraca: a
    #: `T829` trouxe os dezenove KPIs da view e o total foi para 31, e vai mover de novo.
    #: A propriedade nunca dependeu do numero -- ela e que isto cobre TODAS as metricas --,
    #: entao a contagem e lida do catalogo. Um catalogo vazio nao satisfaz mais nada aqui.
    assert results, "no metric was evaluated; an empty sweep forbids nothing"
    assert len(results) == len(catalog.metrics)
    publishable = sorted(name for name, r in results.items() if r.publishable)
    assert not publishable, publishable


def test_the_three_retention_metrics_remain_pending_by_construction(
    catalog: LoadedCatalog,
) -> None:
    expected = ("retention.cohort_timezone", "retention.eligible_event", "retention.identity_rule")
    for window in (1, 7, 30):
        metric = catalog.metrics[f"retention_rate_d{window}"]
        assert metric.unset_required_fields() == expected


def test_no_authored_content_claims_authority_before_the_project_existed(
    catalog: LoadedCatalog,
) -> None:
    """Governance inception. A policy, tag or message effective before it was
    authored fabricates the history a decision would later be evaluated against.
    """
    inception = date(2026, 8, 11)
    for policy in catalog.policies:
        assert policy.effective_from >= inception, policy.policy_id
    assert catalog.access_tags is not None
    for tag in catalog.access_tags.tags:
        assert tag.effective_from >= inception, tag.id
    assert catalog.reason_messages is not None
    for message in catalog.reason_messages.messages:
        assert message.effective_from >= inception, message.reason_code
    for name, metric in sorted(catalog.metrics.items()):
        for version in metric.versions:
            assert version.effective_from >= inception, f"{name} v{version.version}"


def test_the_access_tag_registry_holds_only_referenced_tags(catalog: LoadedCatalog) -> None:
    """Production governance data is not a place to exercise a capability.

    Deprecated-tag and replacement behaviour is proven by the T017 unit fixtures.
    A tag here that nothing references is either dead governance or imported
    example history.
    """
    assert catalog.access_tags is not None
    declared = {tag.id for tag in catalog.access_tags.tags}
    referenced = {metric.access for metric in catalog.metrics.values()}
    assert declared == referenced, f"declared={sorted(declared)} referenced={sorted(referenced)}"
    assert all(tag.deprecated_from is None for tag in catalog.access_tags.tags)


def test_the_pending_visibility_registry_is_present_and_empty(catalog: LoadedCatalog) -> None:
    assert catalog.approvals is not None
    assert catalog.approvals.approvals == ()
