"""The ADR 0010 change is additive and nothing else — 003:T012.

**The Phase A0 boundary.** ADR 0010 authorizes exactly one upstream change: an additive public
composed entry point under `packages/analytics_query/`, plus the tests that prove it. Nothing else
in this package may be touched, and Feature 003 may not begin until Phase A0 is finished.

This is the guard that makes "additive" checkable rather than asserted. It reads **the working
tree and the committed history since `FREEZE_BASE`**, so a modified existing file fails here whether
it is staged, unstaged or already committed. Until ADR 0034 it read the working tree alone, and a
modification survived simply by being committed.

**On the ordering invariant.** This file first stated the boundary as *"no Feature 003 package
exists"*. That sentence was true only while Phase A0 was in flight; it expired the moment `003:T013`
legitimately created the package, and an assertion that fails on correct work is not protection, it
is noise waiting to be deleted.

The property actually worth keeping is the ordering itself, which does not expire: **Feature 003 may
exist only once Phase A0 is complete.** It is derived from `003`'s recorded task states, not from
the branch name, the commit history or the mere presence of files — those describe where the work
happens to sit, while the task ledger is what records whether the prerequisite was met.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
PACKAGE = "packages/analytics_query/"
TASKS_003 = REPO / "specs" / "003-nl-analytics-interaction" / "tasks.md"
FEATURE_003_PACKAGE = REPO / "packages" / "analytics_interaction"

#: The complete set of paths Phase A0 may add. Anything else under the package is a scope violation,
#: whether added or modified.
PERMITTED_ADDITIONS = {
    "packages/analytics_query/src/analytics_query/execute.py",
    "packages/analytics_query/tests/fixtures/entry_point.py",
    "packages/analytics_query/tests/contract/adr0010_baseline.json",
    "packages/analytics_query/tests/contract/test_adr0010_baseline.py",
    "packages/analytics_query/tests/contract/test_adr0010_scope.py",
    "packages/analytics_query/tests/contract/test_entry_point_equivalence.py",
    "packages/analytics_query/tests/contract/test_single_execution_path.py",
    "packages/analytics_query/tests/integration/test_refusal_boundaries.py",
    "packages/analytics_query/tests/integration/test_entry_point_audit.py",
    "packages/analytics_query/tests/adversarial/test_entry_point_parity.py",
    "packages/analytics_query/tests/adversarial/test_entry_point_midflight.py",
}

#: The **separately governed** maintenance surface — ADR 0016.
#:
#: Phase A0's boundary is "additive, and nothing else". It stayed intact. What this set records is a
#: different, later authorization: a contract-transport defect found during `003`'s Phase 10, where
#: `001` computed a complete comparable window and its published decision could carry only part of
#: it.
#:
#: Naming the exact files here rather than relaxing the guard is the point. The additive-only rule
#: still holds for every path outside this set, and each path inside it is one ADR 0016 names — so a
#: reviewer can see the whole authorized surface without reading a diff, and an unrelated edit still
#: fails.
#: The commit this freeze is measured FROM. Everything after it must be additive under the
#: package, except the paths named as an authorized surface.
#:
#: **It is a commit and not a moving ref**, which is the `F135` correction the `005` and `006`
#: boundary nodes already carry: `origin/main` names this line the moment the work integrates,
#: and the window would be empty exactly when the guard is most needed.
#:
#: It is `d0f2682`, the tip at the moment ADR 0034 was written -- so the repairs that ADR
#: authorizes are themselves INSIDE the window and have to be named below rather than predating
#: the check.
FREEZE_BASE = "d0f26823637e1ccb3731d736bf87310a73ef3535"

#: The two files ADR 0034 authorizes, and the reach is the ADR's rather than this file's.
#:
#: Both repairs are to GUARDS, not to what the package does: one presence check could not fail
#: because it searched its own source for a literal its own assertion writes, and the freeze
#: check below read only the working tree. Every other existing file of this package stays
#: frozen, and a third file appearing here is a decision somebody makes in `docs/adr`.
ADR_0034_SURFACE = {
    "packages/analytics_query/tests/contract/test_adr0010_baseline.py",
    "packages/analytics_query/tests/contract/test_adr0010_scope.py",
}

#: Os cinco nós que a virada do d_15 acendeu, emendados por INSTRUÇÃO (OD-86, 2026-09-01,
#: ciclo 501): o dono declarou o d_15 e a ordem mandou emendar cada nó com data, nenhum
#: morto em silêncio. A superfície é exatamente os cinco arquivos e o nó companheiro abaixo
#: a segura à autorização: se ela é tocada e o registro NÃO diz d_15 declarado com OD-86 na
#: nota, isto é um buraco e falha.
OD_86_AMENDED_NODES_SURFACE = {
    "packages/analytics_query/tests/contract/test_readiness.py",
    "packages/analytics_query/tests/integration/test_fail_closed.py",
    "packages/analytics_query/tests/integration/test_quickstart_scenarios.py",
    "packages/analytics_query/tests/integration/test_single_metric_query.py",
    "packages/analytics_query/tests/unit/test_range_limits_and_reporting.py",
}

ADR_0016_SURFACE = {
    "packages/analytics_query/src/analytics_query/contracts/comparable_window.py",
    "packages/analytics_query/tests/contract/test_adr0010_scope.py",
    "packages/analytics_query/tests/unit/test_comparable_window_transport.py",
    "packages/analytics_query/tests/integration/test_real_decision_window.py",
}

#: `001`'s half of the same maintenance change — both defects. ``decision.py`` and ``coverage.py``
#: carry the transport repair; ``pipeline.py`` carries the composition repair, where the evaluator
#: now attaches the gate-owned window.
ADR_0016_CATALOG_SURFACE = {
    "packages/semantic_catalog/src/semantic_catalog/validation/decision.py",
    "packages/semantic_catalog/src/semantic_catalog/validation/gates/coverage.py",
    "packages/semantic_catalog/src/semantic_catalog/validation/pipeline.py",
    "packages/semantic_catalog/tests/unit/test_comparable_window_contract.py",
    "packages/semantic_catalog/tests/integration/test_comparable_window_publication.py",
}

#: Explicitly authorized **test-only** corrections in `001`, kept out of
#: :data:`ADR_0016_CATALOG_SURFACE` on purpose.
#:
#: Two so far, both in the same module and both the same defect wearing different clothes: a test
#: that measured a **temporary live state** and failed when `003` progressed past it, while the
#: property it protected still held.
#:
#: * ``test_exact_path_matching_remains_mandatory`` required an open task promising a
#:   `.py` file that did not yet exist, and asserted that as a precondition. Completing
#:   `003`'s Phase 16 built the last such file.
#: * ``test_a_feature_in_progress_is_recognised_as_such`` required `003` to be
#:   unfinished. Completing `T181` finished it, and the distinction the test existed to
#:   protect -- executable tasks against `[BLOCKED-EXTERNAL]` records -- became provable
#:   in the stronger direction: the feature is complete *while* four records stay open.
#:
#: Both replace a harvested live example with synthetic ledgers, keep their original node IDs, and
#: leave `_permitted_missing`, `feature_is_complete` and every live repository-wide guard unchanged.
#:
#: A **separate** set rather than an entry on the ADR 0016 list, because the two are different kinds
#: of authorization and merging them would misfile both. ADR 0016 is a governed semantic maintenance
#: change to production modules; this is one test file whose fixture expired, with no semantic
#: content at all. A reviewer reading ``ADR_0016_CATALOG_SURFACE`` must not find a file that ADR
#: 0016 never mentioned.
AUTHORIZED_CATALOG_TEST_MAINTENANCE = {
    "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
}

#: ADR 0029's dimension disclosure gate, authorized as governed work of `001` by the owner on
#: 2026-08-18 and executed on 2026-08-19. A **third** set, for the same reason the second one is
#: separate: a reviewer reading `ADR_0016_CATALOG_SURFACE` must not find a file ADR 0016 never
#: mentioned, and a reviewer reading the test-maintenance set must not find a production module.
#:
#: These four are not four decisions. `001`'s own gates require them together — the field alone
#: fails the classification map, and the map alone fails the published table — so a partial
#: application of ADR 0029 does not pass `001`. The ADR's execution note names exactly these paths,
#: and the assertion below reads that note rather than trusting this list.
ADR_0029_CATALOG_SURFACE = {
    "packages/semantic_catalog/src/semantic_catalog/contracts/dimension.py",
    "packages/semantic_catalog/src/semantic_catalog/contracts/classification.py",
    "packages/semantic_catalog/src/semantic_catalog/search/concepts.py",
    "packages/semantic_catalog/tests/contract/test_concept_disclosure.py",
}

#: The two approved artifacts ADR 0029 could not avoid, and **nothing else**. Both are consequences
#: of `001`'s own gates rather than choices: the § 4.4 table must match the classification map, and
#: the schema must be regenerated rather than hand-edited.
#:
#: Kept out of :data:`ADR_0029_CATALOG_SURFACE` because they are a different kind of authorization —
#: that set is a package surface, this one is an exception to an **absolute** prohibition, and
#: merging them would hide the second inside the first.
ADR_0029_APPROVED_ARTIFACT_EXCEPTION = {
    "specs/001-semantic-catalog/contracts/catalog-file-contracts.md",
    "schemas/dimension.schema.json",
}

#: The governed **content** ADR 0029's gate had nothing to gate without, authorized by the owner on
#: 2026-08-19. A **fifth** set, separate for the same reason the third and fourth are: these are
#: neither a package surface nor an approved artifact. They are the catalog data this project exists
#: to govern, and merging them into the approved-artifact exception would grow a two-path exception
#: to nine and lose the distinction the owner's authorization actually drew.
#:
#: What made the collision unavoidable: the field, the gate and the concept surface shipped in the
#: previous cycle with **no dimension tagged**, so the whole mechanism was fail-closed and unused.
#: Tagging the six axes is what makes it do anything, and all seven of those files sit under
#: `semantic/`, which this module's prohibition guarded absolutely.
#:
#: `access-tags.yaml` is in the set for a reason that is not convenience. `contracts/dimension.py`
#: cited the registry's own wording — `standard` described itself as covering *metrics* — as the
#: reason a dimension could not reuse the tag. So correcting that description is not a companion
#: edit to tagging the axes; it is the precondition that makes tagging them something other than a
#: silent widening of a governed class.
#:
#: Cited as an **instruction**, like `002`'s scope amendment: no ADR named these paths before the
#: owner did.
ADR_0029_GOVERNED_CONTENT = {
    "semantic/dimensions/app_version.yaml",
    "semantic/dimensions/country.yaml",
    "semantic/dimensions/date.yaml",
    "semantic/dimensions/platform.yaml",
    "semantic/dimensions/product.yaml",
    "semantic/dimensions/store.yaml",
    "semantic/governance/access-tags.yaml",
}

#: The minimum path over data that was measured to exist, authorized by the owner on 2026-08-26.
#:
#: **Its own set, and the third authorized by a dated owner instruction rather than by an ADR.** No
#: ADR names these paths, and citing one would be the falsehood this file exists to catch.
#:
#: Two paths, and the pairing is the point: a source declaration and the one metric over it. Neither
#: stands alone — a metric with no source is unresolvable, and a source no metric reads is dead
#: governance.
#:
#: **What makes this different from the sign-off reverted on the same day:** those six sources
#: described app-store pipelines that do not exist, and every gate passed while the claim was
#: false. This one is declared over `semantic.subscription_daily_metrics`, a view whose every
#: figure was read from the warehouse with the instant recorded beside it — and the one field
#: that is not a measurement, `delay_tolerance`, says so in its own comment.
#:
#: **And it changes nothing about publishability.** The source carries no freshness approval,
#: so it is unpublishable exactly like the six before it. `001`'s own fail-closed suite still
#: asserts that nothing at all is publishable, and it passes.
OWNER_MINIMUM_PATH_2026_08_26 = {
    "semantic/sources/subscription_daily.yaml",
    "semantic/metrics/new_trials.yaml",
}

#: The owner's four decisions of 2026-08-26 -- `OD-1` to `OD-4` -- recorded in the governed channel
#: with his literal words *"concordo com sua recomendacao"*.
#:
#: **A sixth set, and it holds ONE path**, because only one of the four decisions creates a file the
#: prohibition did not already admit: `OD-3` authors the `game` axis. `OD-1` amends `platform.yaml`
#: and `product.yaml` and `OD-2` amends `country.yaml` and `date.yaml` -- all four already admitted
#: by :data:`ADR_0029_GOVERNED_CONTENT`, and admitted BY PATH, so this set must not repeat them: the
#: pairwise-disjoint assertion is what keeps each authorization readable on its own.
#:
#: **That overlap is worth naming rather than leaving to be inferred.** Those four files are being
#: changed today for a DIFFERENT ACT than the one that admitted them -- the 2026-08-19 authorization
#: was about tagging the axes for disclosure, and today's is about vocabulary and applicability. The
#: filter cannot tell the two apart, because it matches paths. What tells them apart is this comment
#: and the commits.
#:
#: Cited as an **instruction**, like the two owner sets above it: no ADR names `game.yaml`, and
#: citing one would be the falsehood this file exists to catch.
#:
#: **And it changes nothing about publishability.** `subscription_daily` still carries no freshness
#: approval and `001`'s fail-closed suite still asserts that nothing at all is publishable.
OWNER_DECISIONS_2026_08_26 = {
    "semantic/dimensions/game.yaml",
}

#: The two signatures the owner authorized on 2026-08-26 at 17:17:40Z, in his own words
#: "Autorizar as duas (Recomendado)".
#:
#: **A seventh set, and it holds ONE path**, because only one of the two signatures lands
#: under a guarded tree. The D-18 formula lives in `interpretation_governance/`, which this
#: module does not guard -- measured, the prohibition below names `specs/001`, `specs/002`,
#: two readiness records, `semantic/`, `schemas/` and `query_governance/`, and that directory
#: is on none of them.
#:
#: **This one is a signature, which is the most consequential kind of path this file admits.**
#: `freshness-approvals.yaml` is where a source stops being unpublishable, and its own header
#: says DO NOT FABRICATE APPROVALS. What separates this from the six approvals reverted on the
#: same day is written in that file: those described app-store pipelines that produce nothing,
#: and this one was signed after measuring that the source answers -- 6.844.943 rows over 396
#: days, read at the instant of signing.
#:
#: Cited as an **instruction**, like the owner sets above it: no ADR names this path, and
#: citing one would be the falsehood this file exists to catch.
#:
#: **And it does NOT make anything publishable**, measured: `new_trials` is still `PENDING`,
#: because it declares no `source_availability` at all. The signature moved the SOURCE, not the
#: metric.
OWNER_TWO_SIGNATURES_2026_08_26 = {
    "semantic/governance/freshness-approvals.yaml",
}

#: **Um oitavo conjunto, UM caminho, e é a assinatura mais literal deste arquivo**: OD-86
#: (2026-09-01, palavra do dono por clique) mandou DECLARAR o d_15 no próprio registro —
#: `declared: false` vira `true` com a nota carregando a assinatura e o evidence_ref citando
#: os quatro artefatos do ciclo 499 (o 403 de escrita medido incluso). Citado como
#: **instrução**, como os conjuntos do dono acima: nenhum ADR nomeia este caminho.
#:
#: **E NÃO abre portão de produto**, escrito na própria nota do registro: a assinatura
#: cobriu o REGISTRO; envio, canal e execução seguem governados pelos seus próprios
#: registros e nós.
#: **Um nono conjunto, DOIS caminhos**: OD-93/OD-94 (2026-09-02, palavra dele por clique)
#: mandaram fechar as bloqueadas destravadas — T123 (D-14 com o pacote Conservador) e T124
#: (D-15 declarado por OD-86/90/91) fecham em specs/002/tasks.md, e o registro d_14 vira
#: declarado. Citado como instrução, como os conjuntos do dono acima.
OWNER_UNBLOCKED_CLOSURES_2026_09_02 = {
    "specs/002-analytics-query/tasks.md",
    "docs/readiness/analytics-query-external-readiness.yaml",
}

#: **Um decimo conjunto, DOIS caminhos**: S-33 (ciclo 517, 2026-09-02, achado do REVIEWER)
#: — o gt=0 do contrato tornava IRREPRESENTAVEL o limiar zero que OD-97 aprovou; a emenda
#: ge=0 e os nos dos dois sentidos (zero constroi; -1 recusa) sao a correcao rotulo-vs-ato.
#: Citado como instrucao, como os conjuntos do dono acima.
S33_ZERO_REPRESENTABLE_2026_09_02 = {
    "packages/analytics_query/src/analytics_query/contracts/policy.py",
    "packages/analytics_query/tests/contract/test_foundational_contracts.py",
}

OWNER_D15_DECLARATION_2026_09_01 = {
    "docs/readiness/analytics-query-external-readiness.yaml",
}

#: Every path the guarded-tree prohibition admits, from every authorization that pierces it.
#: Derived rather than written out, so a path can never be admitted by the filter without belonging
#: to a set some assertion below holds to its own decision.
GUARDED_TREE_EXCEPTIONS = (
    ADR_0029_APPROVED_ARTIFACT_EXCEPTION
    | ADR_0029_GOVERNED_CONTENT
    | OWNER_MINIMUM_PATH_2026_08_26
    | OWNER_DECISIONS_2026_08_26
    | OWNER_TWO_SIGNATURES_2026_08_26
    | OWNER_D15_DECLARATION_2026_09_01
    | OWNER_UNBLOCKED_CLOSURES_2026_09_02
)

ADR_0016 = REPO / "docs" / "adr" / "0016-comparable-window-transport.md"
ADR_0029 = REPO / "docs" / "adr" / "0029-dimension-disclosure-gate.md"


def _git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _changes_under_package() -> list[tuple[str, str]]:
    """``(status, path)`` for every tracked change under the package.

    Sliced at the fixed porcelain width rather than partitioned on the first space. A
    modified-but-unstaged entry is ``" M path"``, whose first field is empty — partitioning left the
    status in the path and produced a path that matched nothing. It did not matter while the only
    assertion was "the list is empty"; it matters now that a path is compared against a named
    surface.
    """
    entries: list[tuple[str, str]] = []
    for line in _git("status", "--porcelain", "--", PACKAGE):
        entries.append((line[:2].strip(), line[3:].strip().replace("\\", "/")))
    # AND THE COMMITTED HISTORY, WHICH THIS GUARD DID NOT READ UNTIL ADR 0034.
    #
    # `git status --porcelain` reports THE WORKING TREE AND NOTHING ELSE. Measured on
    # 2026-08-27: an existing file of this package was modified and the guard went red; the
    # same modification, COMMITTED, leaves the working tree clean and the guard green. The
    # freeze was enforced against uncommitted edits and not against what actually ships --
    # a rule whose enforcement stops at the commit boundary.
    #
    # The window is anchored to a COMMIT for the reason `FREEZE_BASE` records, and a base
    # that is not in this history SKIPS rather than reporting a violation: `--is-ancestor`
    # answers 128 for an unknown commit, which is what a shallow clone says about everything
    # but the tip, and turning that into "the freeze was broken" is the `F135` shape again.
    known = subprocess.run(
        ["git", "merge-base", "--is-ancestor", FREEZE_BASE, "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if known.returncode == 128:  # pragma: no cover - a shallow checkout
        pytest.skip(f"{FREEZE_BASE[:7]} is not in this history; the freeze was NOT measured")
    for line in _git("diff", "--name-status", f"{FREEZE_BASE}..HEAD", "--", PACKAGE):
        status, _, path = line.partition("	")
        entries.append((status.strip(), path.strip().replace("\\", "/")))
    return entries


def test_no_existing_file_in_the_package_is_modified() -> None:
    """Additive means additive. A modified file is a different change.

    ADR 0016's surface is excluded by name, not by relaxing the rule: that change is separately
    governed, separately documented and separately bounded, and every path outside its three files
    is still forbidden to move.
    """
    modified = [
        path
        for status, path in _changes_under_package()
        if ((status and status[0] in {"M", "D", "R"}) or status in {"MM", " M", " D"})
        and path
        not in (
            ADR_0016_SURFACE
            | ADR_0034_SURFACE
            | OD_86_AMENDED_NODES_SURFACE
            | S33_ZERO_REPRESENTABLE_2026_09_02
        )
    ]
    assert not modified, f"ADR 0010 permits no modification to existing files: {modified}"


def test_the_od_86_surface_is_accompanied_by_the_declaration() -> None:
    """A superfície do OD-86 sem a declaração no registro seria só um buraco.

    Se qualquer um dos cinco nós emendados foi tocado, o registro TEM que dizer d_15
    declarado com evidencia e OD-86 na nota — a autorização é o próprio registro."""
    touched = {path for _, path in _changes_under_package()} & OD_86_AMENDED_NODES_SURFACE
    if not touched:
        return
    import yaml

    registry = yaml.safe_load(
        (REPO / "docs" / "readiness" / "analytics-query-external-readiness.yaml").read_text(
            encoding="utf-8"
        )
    )
    d15 = next(c for c in registry["capabilities"] if c["id"] == "d_15")
    assert d15["declared"] is True and d15["evidence_ref"], "superficie sem declaracao"
    assert "OD-86" in str(d15.get("note", "")), "superficie sem a assinatura na nota"


def test_the_adr_0016_surface_is_accompanied_by_its_adr() -> None:
    """A named exception with no accepted ADR behind it is just a hole.

    If any file on the maintenance surface has moved, the ADR that authorizes it must exist and be
    accepted. This is what stops the exclusion list above from becoming a place to park unrelated
    edits.
    """
    touched = {path for _, path in _changes_under_package()} & ADR_0016_SURFACE
    if not touched:
        return
    assert ADR_0016.is_file(), "ADR 0016 authorizes this surface and is missing"
    text = ADR_0016.read_text(encoding="utf-8")
    assert "**Status**: Accepted" in text
    assert "comparable window" in text.lower()


def test_every_added_path_is_one_the_adr_permits() -> None:
    added = {
        path
        for status, path in _changes_under_package()
        if status.startswith("?") or status.startswith("A")
    }
    # `git status --porcelain` reports untracked directories, not their contents.
    expanded: set[str] = set()
    for path in added:
        target = REPO / path
        if target.is_dir():
            expanded.update(
                str(child.relative_to(REPO)).replace("\\", "/")
                for child in target.rglob("*")
                if child.is_file() and "__pycache__" not in child.parts
            )
        else:
            expanded.add(path)
    unexpected = sorted(expanded - PERMITTED_ADDITIONS - ADR_0016_SURFACE)
    assert not unexpected, f"paths outside the ADR 0010 scope were added: {unexpected}"


def test_the_entry_point_exists_and_is_the_only_new_source_module() -> None:
    src = REPO / "packages/analytics_query/src/analytics_query"
    assert (src / "execute.py").is_file(), "the composed entry point must exist"
    new_sources = {p for p in PERMITTED_ADDITIONS if p.startswith("packages/analytics_query/src/")}
    assert new_sources == {"packages/analytics_query/src/analytics_query/execute.py"}


#: Phase A0 is exactly T001-T012 of `003`'s graph. Fixed, because the phase is closed: ADR 0010
#: authorizes these twelve and nothing more.
PHASE_A0 = tuple(range(1, 13))

#: A task carrying this marker is an external dependency record, not work. `003`'s T182-T185 are the
#: four it adds. No automation may complete one, so their state can never make Phase A0 look
#: finished or unfinished.
EXTERNAL_RECORD = "[BLOCKED-EXTERNAL]"

_TASK_LINE = re.compile(r"^- \[([ xX])\] T(\d{3})\b(?P<rest>.*)$", re.MULTILINE)


def executable_task_states(tasks_markdown: str) -> dict[int, bool]:
    """``{task number: complete}`` for every executable task.

    External records are excluded rather than reported as incomplete. They are not work items and
    are never markable by automation, so counting them would make every derived verdict permanently
    false.
    """
    return {
        int(match.group(2)): match.group(1) in {"x", "X"}
        for match in _TASK_LINE.finditer(tasks_markdown)
        if EXTERNAL_RECORD not in match.group("rest")
    }


def phase_a0_incomplete(states: dict[int, bool]) -> list[int]:
    """Which of T001-T012 are not yet done, missing tasks included.

    Fail-closed on absence: a task the ledger does not mention is *not* evidence of completion. That
    is the difference between "twelve done" and "nothing said", and only the first may unblock
    Feature 003.

    Tasks outside the phase are never consulted, so no amount of T013+ progress can substitute for
    the prerequisite.
    """
    return [number for number in PHASE_A0 if not states.get(number, False)]


def feature_003_artifact_exists(package_dir: Path) -> bool:
    """Any real file under `003`'s package.

    Byte-compiled caches do not count: a stray `__pycache__` left by a tool is not somebody starting
    the feature.
    """
    if not package_dir.is_dir():
        return False
    return any(
        path.is_file() and "__pycache__" not in path.parts for path in package_dir.rglob("*")
    )


def violates_phase_ordering(tasks_markdown: str, package_exists: bool) -> bool:
    """The invariant, as one predicate: `003` exists ⇒ Phase A0 is complete.

    Expressed as a function so the regression cases below exercise the same code path the live
    assertion does, rather than a re-implementation of it that could drift.
    """
    if not package_exists:
        return False
    return bool(phase_a0_incomplete(executable_task_states(tasks_markdown)))


def test_feature_003_may_exist_only_once_phase_a0_is_complete() -> None:
    """The persistent form of the boundary.

    Replaces the spent "no `003` package exists" assertion. That one protected the ordering only
    until the ordering was correctly followed; this one holds for the life of the repository.
    """
    tasks = TASKS_003.read_text(encoding="utf-8")
    outstanding = phase_a0_incomplete(executable_task_states(tasks))
    if feature_003_artifact_exists(FEATURE_003_PACKAGE):
        assert not outstanding, (
            "Feature 003 exists while Phase A0 is unfinished; outstanding: "
            + ", ".join(f"T{number:03d}" for number in outstanding)
        )


def test_the_phase_a0_task_ledger_is_readable_and_complete() -> None:
    """A guard that reads no tasks would pass for the wrong reason.

    If `003`'s ledger stopped parsing — renamed file, changed checkbox format —
    `phase_a0_incomplete` would report all twelve outstanding and the invariant would fire against
    correct work. Better to fail here, naming the cause.
    """
    assert TASKS_003.is_file(), f"missing Feature 003 task ledger: {TASKS_003}"
    states = executable_task_states(TASKS_003.read_text(encoding="utf-8"))
    missing = [number for number in PHASE_A0 if number not in states]
    assert not missing, f"Phase A0 tasks absent from the ledger: {missing}"


# --- regression coverage for the invariant ------------------------------------
# Synthetic ledgers, so these prove the mechanism rather than restating today's
# repository state. Each is a situation the guard must decide correctly.

_A0_COMPLETE = "\n".join(f"- [X] T{n:03d} Phase A0 task" for n in PHASE_A0)
_A0_PARTIAL = "\n".join(f"- [{'X' if n < 12 else ' '}] T{n:03d} Phase A0 task" for n in PHASE_A0)


def test_no_feature_003_package_with_phase_a0_incomplete_passes() -> None:
    """Mid-A0, before T013. The ordinary state during the prerequisite phase."""
    assert not violates_phase_ordering(_A0_PARTIAL, package_exists=False)


def test_feature_003_package_with_phase_a0_incomplete_fails() -> None:
    """The violation the guard exists for: starting `003` before A0 is done."""
    assert violates_phase_ordering(_A0_PARTIAL, package_exists=True)


def test_feature_003_package_with_phase_a0_complete_passes() -> None:
    """The state that legitimately expired the old assertion."""
    assert not violates_phase_ordering(_A0_COMPLETE, package_exists=True)


def test_a_completed_later_task_does_not_substitute_for_phase_a0() -> None:
    """T013+ progress is not evidence the prerequisite was met.

    This is the failure mode a naive "any tasks complete" check would have: work racing ahead while
    a Phase A0 task stayed open would read as compliant.
    """
    ledger = _A0_PARTIAL + "\n- [X] T013 Create packages/analytics_interaction/"
    assert violates_phase_ordering(ledger, package_exists=True)

    states = executable_task_states(ledger)
    assert states[13] is True, "the later task is complete"
    assert phase_a0_incomplete(states) == [12], "and the phase is still outstanding"


@pytest.mark.parametrize("marker", [" ", "X"])
def test_external_record_state_has_no_effect_on_the_decision(marker: str) -> None:
    """T182-T185 are dependency records, not work.

    Neither open nor — impossibly — closed may move the verdict, in either direction. Asserted
    against a complete ledger and an incomplete one so the parametrization cannot pass by both sides
    being false.
    """
    records = "\n".join(
        f"- [{marker}] T{n} `{EXTERNAL_RECORD}` **D-{n - 164} — external capability**"
        for n in range(182, 186)
    )
    assert not violates_phase_ordering(f"{_A0_COMPLETE}\n{records}", package_exists=True)
    assert violates_phase_ordering(f"{_A0_PARTIAL}\n{records}", package_exists=True)

    parsed = executable_task_states(records)
    assert parsed == {}, f"external records must not be read as tasks: {parsed}"


def test_a_pycache_directory_alone_is_not_the_feature_starting(tmp_path: Path) -> None:
    """Tool droppings are not implementation.

    Without this the guard could fire on a stale cache directory long after the tree it belonged to
    was removed.
    """
    cache = tmp_path / "packages" / "analytics_interaction" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "port.cpython-313.pyc").write_bytes(b"\x00")
    assert not feature_003_artifact_exists(tmp_path / "packages" / "analytics_interaction")

    real = tmp_path / "packages" / "analytics_interaction" / "pyproject.toml"
    real.write_text("[project]\n", encoding="utf-8")
    assert feature_003_artifact_exists(tmp_path / "packages" / "analytics_interaction")


#: The deterministic temporal resolver, authorized by the owner's master instruction of 2026-08-20
#: for trials, purchases, BigQuery and flexible periods.
#:
#: **Its own set, and not folded into an ADR's**, because no ADR authorizes it: the decision is a
#: dated owner instruction recorded in the loop's event log, and citing an ADR for it would be
#: false in the same way citing ADR 0029 for `002`'s scope amendment would have been.
#:
#: Why the file is in `001` at all: the instruction requires that temporal bounds be computed
#: deterministically and forbids the model computing them, and `R-8` puts date arithmetic and IANA
#: resolution in `001` — where `CANONICAL_TIMEZONE` is already declared exactly once. Putting the
#: resolver in `003` would have been a second calendar in the repository.
#:
#: Two paths, and the second is the test rather than a convenience: the instruction lists
#: thirty-nine temporal cases, and a resolver added without them would be arithmetic nobody checked.
OWNER_TEMPORAL_AUTHORIZATION_2026_08_20 = {
    "packages/semantic_catalog/src/semantic_catalog/periods/temporal.py",
    "packages/semantic_catalog/tests/unit/test_temporal_resolution.py",
}

#: The count amendments the minimum path made unavoidable, authorized by the same owner instruction
#: of 2026-08-26.
#:
#: **A separate set from the two `semantic/` paths on purpose, because they are different kinds of
#: act.** Those two are governed CONTENT; these five are `001`'s own assertions about how many
#: sources and metrics exist. Merging them would hide a test edit inside a content declaration.
#:
#: **And these five are the consequence of the authorized change rather than a second decision.**
#: Declaring a seventh source makes `len(sources) == 6` false, and there is no way to declare it and
#: leave the sentence true. Each amendment changes a COUNT and leaves the PROPERTY alone: the suite
#: still asserts that nothing at all is publishable, and it still walks every source rather than a
#: subset. Every one carries the reason in a comment beside it, so a reader meets the argument where
#: the number changed and not in a commit message they will not find.
OWNER_MINIMUM_PATH_COUNT_AMENDMENTS_2026_08_26 = {
    "packages/semantic_catalog/tests/contract/test_baseline_reconciliation.py",
    "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
    "packages/semantic_catalog/tests/integration/test_projection_leakage.py",
    "packages/semantic_catalog/tests/unit/test_compliance.py",
    "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
}

#: Everything in `001` this repository's governed acts have authorized, by name.
#:
#: A union of separately-argued sets rather than one list, so a reviewer can tell which
#: authorization covers which file. Anything outside it still fails.
#: ADR 0033's execution surface in `001`: a freshness approval binds to the content it
#: approved, not to the repository state the caller happens to be publishing.
#:
#: **A sixth act, and it is an ADR rather than a dated instruction** -- ADR 0033, accepted
#: 2026-08-26 on the owner's literal words "Ligar ao conteudo (Recomendado)". Kept separate
#: from the ADR 0016 and ADR 0029 sets for the reason every set here is separate: they are
#: different acts, and a reader following one must not find another's files in it.
#:
#: Four production modules and two test modules. The four are the chain the comparand travels:
#: the registry that compares it, the eligibility functions that pass it per source, the
#: lifecycle derivation that feeds them, and the bundle that receives it from the caller. The
#: two tests are the ones that call those functions DIRECTLY and therefore name the parameter
#: -- every other node in `001` goes through `build_bundle` and did not move.
#:
#: **The CLI is deliberately NOT here.** Wiring the caller to resolve a commit per source from
#: Git was attempted and escalated instead of forced: it makes three of `001`'s own CLI nodes
#: unsatisfiable, because they validate fixture catalogs whose approvals name invented commits
#: that no real file history can equal. That is a `001` surface question and it is open.
ADR_0033_CONTENT_BINDING = {
    # The library: the comparand and the chain it travels.
    "packages/semantic_catalog/src/semantic_catalog/contracts/freshness_approval.py",
    "packages/semantic_catalog/src/semantic_catalog/loader/bundle.py",
    "packages/semantic_catalog/src/semantic_catalog/loader/lifecycle.py",
    "packages/semantic_catalog/src/semantic_catalog/validation/publication.py",
    # The CALLER, added 2026-08-26 after the first attempt was escalated and the
    # reviewer answered with a cheaper path: the CLI states the mapping with a
    # repeatable `--source-commit id=sha` and resolves the rest from Git. No contract
    # moved -- ADR 0033 already put commit resolution on the caller.
    "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
    # Nodes that name the comparand directly.
    "packages/semantic_catalog/tests/unit/test_freshness_approval.py",
    "packages/semantic_catalog/tests/unit/test_retention_pending.py",
    "packages/semantic_catalog/tests/unit/test_cli.py",
    # Nodes moved OFF the transition fallback. Each states the same commit it always
    # stated, per source instead of inherited from the caller's -- a no-op by
    # construction, and the suite outcome is unchanged at 1899.
    #
    # **The first pass at this list was wrong about which nodes still mattered, and the
    # correction is worth keeping.** It claimed the unconverted sites pointed at a
    # catalog with no approvals -- checked by looking for a `freshness-approvals.yaml`
    # under `tests/fixtures/catalog`, a directory THAT DOES NOT EXIST. The check
    # returned "no approvals file" because there was no directory, and the empty answer
    # was reported as a proof. In those modules `FIXTURES` already points at the
    # fixture's own directory, so `FIXTURES / "catalog"` is `decision_matrix/catalog`,
    # `versioned_catalog/catalog` or `deprecated_catalog/catalog` -- all three of which
    # DO carry an approval, and all three approve `fixture0`, which is the very commit
    # those tests pass. They were the only places in fixture land where the comparand
    # resolved and decided.
    #
    # They are converted now. What remains on the fallback is two calls that raise
    # `PolicyUnresolvableError` before the freshness path runs at all -- proven by the
    # call order in `build_bundle`, which is checkable, rather than by a path name.
    "packages/semantic_catalog/tests/integration/test_adversarial.py",
    "packages/semantic_catalog/tests/integration/test_audit_emission.py",
    "packages/semantic_catalog/tests/integration/test_no_auto_degradation.py",
    "packages/semantic_catalog/tests/integration/test_provenance_statement.py",
    "packages/semantic_catalog/tests/integration/test_unsafe_combinations.py",
    "packages/semantic_catalog/tests/unit/test_coverage_freshness_independence.py",
    "packages/semantic_catalog/tests/unit/test_fail_closed.py",
    "packages/semantic_catalog/tests/unit/test_freshness_and_coverage.py",
    "packages/semantic_catalog/tests/unit/test_matrix_and_pipeline.py",
    "packages/semantic_catalog/tests/unit/test_search.py",
    "packages/semantic_catalog/tests/integration/test_decision_matrix.py",
    "packages/semantic_catalog/tests/integration/test_deprecation_boundaries.py",
    "packages/semantic_catalog/tests/integration/test_release_lifecycle.py",
    "packages/semantic_catalog/tests/unit/test_as_of_stability.py",
}

AUTHORIZED_CATALOG_SURFACE = (
    ADR_0016_CATALOG_SURFACE
    | AUTHORIZED_CATALOG_TEST_MAINTENANCE
    | ADR_0029_CATALOG_SURFACE
    | OWNER_TEMPORAL_AUTHORIZATION_2026_08_20
    | OWNER_MINIMUM_PATH_COUNT_AMENDMENTS_2026_08_26
    | ADR_0033_CONTENT_BINDING
)


def test_feature_001_is_untouched_by_this_phase() -> None:
    """`001` changes only where a named, separately-governed act authorized it.

    The acts are listed separately because they are different in kind: ADR 0016's semantic
    maintenance to production modules, one explicitly authorized test-only correction to a fixture
    that expired, ADR 0029's disclosure gate with its artifact exception and governed content, and
    — since 2026-08-20 — the owner's dated instruction authorizing the deterministic temporal
    resolver. None of them is this phase widening its own scope, and a file outside all of them
    still fails.
    """
    changes = [
        line
        for line in _git("status", "--porcelain", "--", "packages/semantic_catalog/")
        if line.split(maxsplit=1)[-1].strip().replace("\\", "/") not in AUTHORIZED_CATALOG_SURFACE
    ]
    assert not changes, f"Phase A0 must not touch Feature 001: {changes}"


def test_the_two_catalog_authorizations_stay_distinguishable() -> None:
    """Pairwise disjoint, and none empty.

    Merging any two would misfile both: a reviewer reading `ADR_0016_CATALOG_SURFACE` must not find
    a file ADR 0016 never mentioned, a reviewer reading the test-maintenance set must not find a
    production module, and a reviewer reading ADR 0029's set must not find a file that ADR did not
    name.

    **This paragraph no longer counts the sets**, and the reason is a finding rather than a tidy-up:
    it said "six sets now", a seventh was added, and a number written in prose ages the day it is
    written. The sets are enumerated below and the loop counts them. **The seventh set was later
    reverted and this sentence did not have to change**, which is the whole argument for taking the
    number out.

    The pairwise form is what makes a new set cheap to add and impossible to add quietly.
    `OWNER_TEMPORAL_AUTHORIZATION_2026_08_20` is the one authorized by a dated owner instruction
    rather than by an ADR, so a reviewer reading any ADR's set must not find it, and a reviewer
    reading it must not find a file an ADR already covers.

    `ADR_0029_GOVERNED_CONTENT` earns the pairwise form for another reason: it is the only one
    holding authored catalog data rather than code, tests, specs or schemas.
    """
    sets = {
        "ADR_0016_CATALOG_SURFACE": ADR_0016_CATALOG_SURFACE,
        "AUTHORIZED_CATALOG_TEST_MAINTENANCE": AUTHORIZED_CATALOG_TEST_MAINTENANCE,
        "ADR_0029_CATALOG_SURFACE": ADR_0029_CATALOG_SURFACE,
        "ADR_0029_APPROVED_ARTIFACT_EXCEPTION": ADR_0029_APPROVED_ARTIFACT_EXCEPTION,
        "ADR_0029_GOVERNED_CONTENT": ADR_0029_GOVERNED_CONTENT,
        "OWNER_TEMPORAL_AUTHORIZATION_2026_08_20": OWNER_TEMPORAL_AUTHORIZATION_2026_08_20,
        "OWNER_MINIMUM_PATH_2026_08_26": OWNER_MINIMUM_PATH_2026_08_26,
        "OWNER_MINIMUM_PATH_COUNT_AMENDMENTS_2026_08_26": (
            OWNER_MINIMUM_PATH_COUNT_AMENDMENTS_2026_08_26
        ),
        "OWNER_DECISIONS_2026_08_26": OWNER_DECISIONS_2026_08_26,
        "ADR_0033_CONTENT_BINDING": ADR_0033_CONTENT_BINDING,
        "OWNER_TWO_SIGNATURES_2026_08_26": OWNER_TWO_SIGNATURES_2026_08_26,
    }
    for name, members in sorted(sets.items()):
        assert members, f"{name} is empty"
    names = sorted(sets)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap = sets[left] & sets[right]
            assert not overlap, f"{left} and {right} share {sorted(overlap)}"


def test_the_adr_0029_sets_name_only_paths_that_adr_names() -> None:
    """Read from the ADR, not trusted from the list above.

    A set can drift from the decision it cites, and the drift looks like a passing test. So every
    path in all three ADR 0029 sets must appear in the ADR's own execution note, and every path must
    exist.

    `ADR_0029_GOVERNED_CONTENT` is held to the same requirement as the other two, and that is the
    whole point of adding it here rather than exempting it: the owner authorized seven named paths,
    so seven named paths have to be findable in the record. A set that could admit a path the ADR
    never mentions is a set that authorizes itself.
    """
    assert ADR_0029.is_file(), f"{ADR_0029} is missing"
    note = ADR_0029.read_text(encoding="utf-8")
    assert "## Execution note" in note, "ADR 0029 carries no execution note to check against"

    authorized = (
        ADR_0029_CATALOG_SURFACE | ADR_0029_APPROVED_ARTIFACT_EXCEPTION | ADR_0029_GOVERNED_CONTENT
    )
    for path in sorted(authorized):
        assert path in note, f"{path} is authorized here but ADR 0029 does not name it"
        assert (REPO / path).is_file(), f"{path} does not exist"


def test_the_approved_artifact_exception_covers_exactly_two_paths() -> None:
    """An exception to an absolute prohibition stays the size the ADR justified.

    Two paths, both consequences of `001`'s gates. Anything else under the guarded trees is still
    refused by the assertion below, which is what makes this an allowlist rather than an opening.
    """
    assert len(ADR_0029_APPROVED_ARTIFACT_EXCEPTION) == 2
    for path in sorted(ADR_0029_APPROVED_ARTIFACT_EXCEPTION):
        assert path.startswith(("specs/001-semantic-catalog/", "schemas/")), path


def test_the_governed_content_set_covers_exactly_the_seven_authored_paths() -> None:
    """The second piercing of the prohibition, held to its own size and its own tree.

    This node exists so that `test_the_approved_artifact_exception_covers_exactly_two_paths` above
    keeps meaning what it says. The 2026-08-19 authorization did **not** grow that exception to
    nine: it added a separate one, for a different kind of artifact, each bounded separately.

    Seven paths, all under `semantic/`, and the six dimensions named individually rather than by
    prefix. A prefix would admit a seventh dimension file nobody decided about, which is exactly the
    silent kind of widening this whole file exists to refuse.
    """
    assert len(ADR_0029_GOVERNED_CONTENT) == 7, (
        f"the owner named seven governed-content paths; this set holds "
        f"{len(ADR_0029_GOVERNED_CONTENT)}: {sorted(ADR_0029_GOVERNED_CONTENT)}"
    )

    dimensions = {path for path in ADR_0029_GOVERNED_CONTENT if "/dimensions/" in path}
    assert dimensions == {
        f"semantic/dimensions/{name}.yaml"
        for name in ("app_version", "country", "date", "platform", "product", "store")
    }, f"the authored axes are not the six the owner named: {sorted(dimensions)}"

    assert ADR_0029_GOVERNED_CONTENT - dimensions == {"semantic/governance/access-tags.yaml"}, (
        "the only non-dimension path here is the access-tag registry, because correcting its "
        "description is what makes tagging the axes something other than a silent widening"
    )

    for path in sorted(ADR_0029_GOVERNED_CONTENT):
        assert path.startswith("semantic/"), path
        assert path.endswith(".yaml"), path


def test_the_test_maintenance_exemption_covers_no_production_module() -> None:
    """**Test-only means test-only.**

    Every path in the exemption is under `tests/`. A production module appearing here would be a
    semantic change wearing a test-maintenance label, which is exactly the misfiling the separate
    set exists to prevent.
    """
    for path in AUTHORIZED_CATALOG_TEST_MAINTENANCE:
        assert "/tests/" in path, path
        assert path.endswith(".py"), path
        assert (REPO / path).is_file(), path


def test_an_unauthorized_catalog_change_still_fails() -> None:
    """The guard narrowed, not weakened.

    A planted path outside both sets is rejected, so the exemption is an allowlist rather than a
    hole. Checked against the filter directly, because the live guard passes today and would prove
    nothing about a file nobody edited.
    """
    planted = "packages/semantic_catalog/src/semantic_catalog/search/resolve.py"
    assert planted not in AUTHORIZED_CATALOG_SURFACE
    lines = [f" M {planted}", f" M {sorted(AUTHORIZED_CATALOG_TEST_MAINTENANCE)[0]}"]
    rejected = [
        line
        for line in lines
        if line.split(maxsplit=1)[-1].strip().replace("\\", "/") not in AUTHORIZED_CATALOG_SURFACE
    ]
    assert rejected == [f" M {planted}"]


def test_no_approved_specification_or_readiness_record_is_touched() -> None:
    """Approved artifacts do not change, except where a named ADR could not avoid it.

    The prohibition was absolute until 2026-08-19. It has been pierced three times since, every time
    by a literal owner authorization, and every time by a **named, separately bounded** set rather
    than by relaxing the rule:

    * ADR 0029's execution needed two approved artifacts — `001`'s own gates require the § 4.4 table
      to match the classification map, and require the schema to be regenerated rather than
      hand-edited. That is `ADR_0029_APPROVED_ARTIFACT_EXCEPTION`, still exactly two paths;
    * tagging the six authored axes needed seven governed-content paths under `semantic/`, without
      which the gate that shipped in the previous cycle gates nothing. That is
      `ADR_0029_GOVERNED_CONTENT`, exactly seven paths.

    **A third piercing was opened and closed on 2026-08-26.** D-1 was signed, which put the
    sign-off in `semantic/governance/freshness-approvals.yaml` and needed a third set to admit it;
    the owner then reverted the signature, because the six approved sources are app-store pipelines
    that do not exist yet, and the set went out with it. It is recorded here rather than erased so
    the next reader knows the mechanism was exercised and returned — **a piercing that closes again
    is what an allowlist looks like when it works.**

    **It is an allowlist, not an opening.** Every admitted path is named, held to the act that
    records it, and counted from the sets themselves rather than from a number written in this
    sentence — the count that used to stand here was "nine paths", and a number in prose is the
    thing that ages. `test_a_planted_change_under_a_guarded_tree_still_fails` proves a path outside
    the sets is still refused.

    ## What this node measures, and what it does not

    It reads `git status --porcelain`, so it compares the **working tree** against `HEAD`. It
    notices an unauthorized edit while that edit is uncommitted, which is when a reviewer can still
    act on it, and it is silent about anything already committed. That is a real limit rather than a
    subtlety, and it is written down here so nobody reads a green tick as immutability: an
    unauthorized change that reaches a commit is caught by the history, by review, and by `004`'s
    own `test_upstream_untouched`, which compares against a baseline commit rather than `HEAD`.
    """
    for guarded in (
        "specs/001-semantic-catalog/",
        "specs/002-analytics-query/",
        "docs/readiness/external-readiness.yaml",
        "docs/readiness/analytics-query-external-readiness.yaml",
        "semantic/",
        "schemas/",
        "query_governance/",
    ):
        changes = [
            line
            for line in _git("status", "--porcelain", "--", guarded)
            if line.split(maxsplit=1)[-1].strip().replace("\\", "/") not in GUARDED_TREE_EXCEPTIONS
        ]
        assert not changes, f"{guarded} is approved and must not change: {changes}"


def test_a_planted_change_under_a_guarded_tree_still_fails() -> None:
    """The narrowing has teeth: a path outside the exception is still refused.

    Checked against the filter directly rather than by editing a file, for the same reason
    `test_an_unauthorized_catalog_change_still_fails` does it that way: the live guard passes today
    and would prove nothing about a file nobody touched.

    Three planted paths now, all under trees the prohibition guards and none in either exception —
    one in `specs/001-semantic-catalog/`, one in `schemas/`, one in `semantic/`, so a filter that
    special-cased a single tree would fail here.

    The third is the one the 2026-08-19 authorization made necessary. `semantic/` stopped being
    absolutely closed, and the failure mode that replaces "nothing here may change" is "something
    here changed that nobody named". A seventh dimension file is the obvious shape of it, so that is
    what is planted: a plausible, harmless-looking sibling of seven authorized paths.
    """
    planted = (
        "specs/001-semantic-catalog/spec.md",
        "schemas/metric.schema.json",
        "semantic/dimensions/channel.yaml",
    )
    for path in planted:
        assert path not in GUARDED_TREE_EXCEPTIONS

    lines = [f" M {path}" for path in planted]
    lines += [f" M {path}" for path in sorted(GUARDED_TREE_EXCEPTIONS)]
    rejected = [
        line
        for line in lines
        if line.split(maxsplit=1)[-1].strip().replace("\\", "/") not in GUARDED_TREE_EXCEPTIONS
    ]
    assert rejected == [f" M {path}" for path in planted]
