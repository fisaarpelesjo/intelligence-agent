"""What the approval binds to, and what still does not reach it — `F-F`, ADR 0033.

**This file asserted a defect. The defect was decided, and this is the re-derivation
the file itself demanded.** It used to say a failure here means *"the escalated
decision was taken"* — it was, on 2026-08-26T18:10Z, in the owner's words *"Ligar ao
conteudo (Recomendado)"*, and the node went red. Twice, once for each half.

## What changed, and it is the mechanism

`FreshnessApprovals.evaluate` no longer compares against the commit the caller is
publishing. It compares against **`source_content_commit`: the commit that last
modified the approved source's own file** — which is what
`semantic/governance/freshness-approvals.yaml` always promised `source_commit` meant.
`publishable_source_ids` takes a commit **per source**, because one shared commit
could not express "this source's content is unchanged" for seven sources at once.

The comparison is a **prefix in the safe direction**: the approved id must be a prefix
of the resolved one. A seven-character id is how a person writes a commit and is the
schema's own floor; demanding equality would have left every hand-written approval
inert through a second door.

## What has NOT changed, and it is the caller

**The production caller still does not supply the mapping**, so in the real system the
approval is still inert. Wiring the CLI to resolve a commit per source from Git was
attempted and **escalated instead of forced**: it makes three of `001`'s own CLI nodes
unsatisfiable, because they validate **fixture catalogs** whose approvals name invented
commits like `fixture0` that no real file history can ever equal. Making them pass would
need either a new way to say *"this catalog is not Git-backed"* — a `001` surface
decision — or a weaker binding. Neither is this feature's to take.

So `build_bundle` falls back to the caller's commit when no mapping is supplied, which
leaves every existing caller with **byte-for-byte the behaviour it already had**, and
that fallback is a declared transition rather than a design.

## What this file asserts now

1. the approval **resolves** when it is checked against the commit its own content is at
   — the positive half, so the negative half is not read as a broken approval;
2. it **does not resolve** against a commit that is not that one, with `commit_mismatch`
   named — the property that made binding-to-content worth deciding;
3. **the fallback is still what the real callers get**, asserted directly, so the
   transition cannot quietly become permanent without this file going red;
4. CI still passes `${GITHUB_SHA}`, read from the workflow rather than remembered.

A failure in 1 or 2 means the mechanism changed again. A failure in 3 means **the
escalation was resolved and the caller was wired** — which is the good outcome, and the
file says so rather than reading as a break.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest
from semantic_catalog.loader.bundle import load_catalog
from semantic_catalog.validation.publication import publishable_source_ids, source_eligibility

pytestmark = pytest.mark.integration

#: `tests/integration/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
ON = date(2026, 8, 26)

#: From `semantic/policies/`, written out rather than resolved: this node is about the
#: commit comparison, and a role list computed here would drag policy resolution into a
#: test that is not about policy.
PERMITTED_ROLES = frozenset({"data_governance", "product_analytics"})

#: The `--commit` default in `semantic_catalog/cli/main.py`. A literal string, and never
#: a commit id — which is the point.
CLI_DEFAULT_COMMIT = "workingtree"


def _catalog():
    return load_catalog(REPO / "semantic")


def _approval():
    approvals = _catalog().freshness_approvals
    assert approvals is not None and approvals.approvals, "no freshness approval is authored"
    return approvals.approvals[0]


def _head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_there_is_an_approval_to_reason_about() -> None:
    """**Read this before believing anything below.**

    Every assertion here is about one approval. With none authored, they would all pass
    vacuously — which is the failure mode this repository keeps closing.
    """
    approval = _approval()
    assert approval.source_id, "the approval names no source"
    assert approval.source_commit, "the approval names no commit"


def test_the_approval_resolves_under_the_commit_it_names() -> None:
    """The positive half, so the negative half below is not mistaken for a broken approval.

    The entry is well-formed and every other check passes: not rejected, not expired,
    role permitted, four values still matching the source. Under the commit it names it
    IS publishable — the source is the only one in the catalog that is.
    """
    approval = _approval()
    catalog = _catalog()
    eligibility = source_eligibility(
        catalog.sources[approval.source_id],
        catalog.freshness_approvals,
        source_content_commit=approval.source_commit,
        on=ON,
        permitted_roles=PERMITTED_ROLES,
    )
    assert eligibility.publishable, eligibility.denial
    assert publishable_source_ids(
        catalog,
        source_commits={approval.source_id: approval.source_commit},
        on=ON,
        permitted_roles=PERMITTED_ROLES,
    ) == frozenset({approval.source_id})


@pytest.mark.parametrize("caller", ["head", "cli_default"])
def test_the_approval_is_inert_under_what_the_callers_actually_pass(caller: str) -> None:
    """**The finding, asserted so it cannot go quiet.**

    `HEAD` stands in for the CI's `${GITHUB_SHA}` — both are a commit that is not the one
    the approval names, and the comparison is equality, so any such commit behaves the
    same. `workingtree` is the CLI default and is not a commit id at all.

    A failure here means the semantics changed, and that is exactly what it is for: it
    should be read as *"the escalated decision was taken"*, not as *"the test broke"*.
    """
    approval = _approval()
    catalog = _catalog()
    current = _head() if caller == "head" else CLI_DEFAULT_COMMIT
    assert current != approval.source_commit, (
        "the caller now passes the very commit the approval names, so this node's premise "
        "is gone and the escalated D-1 question has been answered somewhere"
    )

    eligibility = source_eligibility(
        catalog.sources[approval.source_id],
        catalog.freshness_approvals,
        source_content_commit=current,
        on=ON,
        permitted_roles=PERMITTED_ROLES,
    )
    assert not eligibility.publishable, (
        f"the approval now resolves under {caller}; the commit comparison changed meaning "
        "and every sentence written about this approval has to be re-measured"
    )
    assert eligibility.denial is not None
    assert eligibility.denial.value == "commit_mismatch", eligibility.denial

    assert (
        publishable_source_ids(
            catalog,
            source_commits=dict.fromkeys(catalog.sources, current),
            on=ON,
            permitted_roles=PERMITTED_ROLES,
        )
        == frozenset()
    ), "a source became publishable under a commit the approval does not name"


def test_the_ci_workflow_still_passes_a_commit_the_approval_cannot_match() -> None:
    """The other half of the finding, read from the workflow rather than remembered.

    The inertness above only matters because of what the caller passes. That is asserted
    against the file, so the day CI starts passing something else this node notices —
    and a reader does not have to trust a sentence in a docstring about a YAML.
    """
    workflow = (REPO / ".github" / "workflows" / "catalog.yml").read_text(encoding="utf-8")
    assert "--commit" in workflow, "the catalog workflow passes no commit at all"
    assert "${GITHUB_SHA}" in workflow, (
        "the catalog workflow no longer passes the run's sha; what it passes now decides "
        "whether the approval resolves, so this node has to be re-derived"
    )


def test_the_transition_fallback_is_still_what_a_caller_without_the_mapping_gets() -> None:
    """**Point 3 of the docstring, asserted rather than described.**

    `build_bundle` falls back to the caller's commit when no per-source mapping is
    supplied. That is a declared transition, and a transition nobody measures becomes
    permanent — so it is measured here.

    **Re-derived on 2026-08-27, and what it asserts now is the fallback's BEHAVIOUR
    rather than a blocker that stood in front of it.** It used to assert that no metric
    was publishable under either commit — true while `new_trials` declared no available
    source, and true for a reason that had nothing to do with the fallback. With the
    declaration written, the fallback is finally observable: it treats every source as
    being at the caller's commit, so the answer CHANGES with that commit.
    """
    from semantic_catalog.loader.bundle import build_bundle

    approval = _approval()
    matching = build_bundle(REPO / "semantic", current_commit=approval.source_commit, on=ON)
    assert matching.lifecycles["new_trials"].is_published, (
        "under the fallback with the approved commit the source is approved, so the "
        "metric that declares it must be published; if it is not, the fallback stopped "
        "applying the caller's commit to every source"
    )

    stranger = build_bundle(REPO / "semantic", current_commit="0" * 40, on=ON)
    assert not stranger.lifecycles["new_trials"].is_published, (
        "a commit the approval does not name published a metric anyway; the fallback "
        "is no longer binding the approval to content"
    )


def test_an_approved_source_publishes_its_own_metric_and_no_other() -> None:
    """**The limit ADR 0033 states, asserted now that a metric can actually reach it.**

    Binding to content makes a SOURCE publishable. It publishes no metric BY ITSELF —
    the metric must also declare that source available, and the metrics answered from
    unapproved sources stay unpublished however healthy this approval is.

    **This node asserted that NOTHING was publishable until 2026-08-27**, and it was
    right: `new_trials` declared no `source_availability`, so the approval could not
    publish anything and the ADR's limit was indistinguishable from the blocker. The
    blocker is gone — the coverage observation exists and the declaration was written —
    so the limit is asserted in the only form that separates it from an absence.

    **RE-DERIVED 2026-09-03 (OD-106).** It read `== ["new_trials"]` while that metric was
    the only one declaring the approved source. The owner's two clicks declared the
    nineteen served metrics on that same source, so the published set is now nineteen —
    and the property is UNCHANGED: the published set equals, exactly, the metrics that
    declare the APPROVED source available. Derived from the catalog rather than typed, so
    a twentieth declaration moves both sides together and a metric published on an
    UNAPPROVED source still fails here.
    """
    from semantic_catalog.loader.bundle import build_bundle

    approval = _approval()
    mapped = build_bundle(
        REPO / "semantic",
        current_commit=_head(),
        on=ON,
        source_commits={approval.source_id: approval.source_commit},
    )
    published = sorted(n for n, s in mapped.lifecycles.items() if s.is_published)

    # Quem DECLARA a fonte aprovada como disponivel — lido do catalogo mapeado, nunca
    # digitado: os dois lados se movem juntos quando uma declaracao nova nascer.
    declaring = sorted(
        metric_id
        for metric_id, metric in mapped.internal.metrics.items()
        for entry in metric.source_availability
        if entry.source == approval.source_id and entry.status.value == "available"
    )
    assert declaring, "nenhuma metrica declara a fonte aprovada; este no afirmaria o vazio"
    assert published == declaring, (
        f"under the content mapping exactly the metrics declaring the approved source "
        f"should be published; published={published} declaring={declaring}"
    )
    assert sorted(n for n in mapped.lifecycles if n not in set(declaring)), (
        "every metric in the catalog declares the approved source, so this asserts nothing "
        "about the metrics answered from sources the approval does not name"
    )

    # **The fallback at HEAD publishes NOTHING, and that is the ADR working.** With no
    # mapping every source is read as being at the caller's commit; HEAD is not the
    # commit the approval names, so the source is unapproved and the metric that
    # declares it cannot be published. The approval binds to CONTENT, not to whatever
    # the repository happens to be at.
    at_head = build_bundle(REPO / "semantic", current_commit=_head(), on=ON)
    assert not sorted(n for n, s in at_head.lifecycles.items() if s.is_published), (
        "the fallback published a metric at HEAD, so the approval is no longer bound "
        "to the content it approved"
    )
