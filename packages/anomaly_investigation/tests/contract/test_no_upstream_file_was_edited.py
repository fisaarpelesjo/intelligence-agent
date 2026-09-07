"""Every upstream edit is named — T033 (`FR-008`, standing constraint 1).

**THIS FILE SAID "ZERO, AND THE CLAIM IS MEASURED RATHER THAN PROMISED" AND THE CLAIM
WAS FALSE EXACTLY WHERE IT SAID IT WAS MEASURED.** `F-1`, found by the reviewer on
2026-08-27 and measured: fourteen commits on this branch edit an upstream package or
governed content, seventy-five file-touches in all, and this node saw **none of them**
while reporting twelve passing checks.

## The two questions were sharing one window, and only one of them was right

The window came from ``git log BASE..HEAD -- FEATURE_ROOTS``, so the files judged came
from **the commits that touch this feature's roots**. A commit that touches ONLY
upstream, or only governed content, has no root of ours in it and was therefore
invisible — to the very checks whose whole purpose is to catch it.

Two questions, and they need two windows:

*"which commits are MINE"* — **attribution**, and the root filter is right: after the
merge the range holds other people's commits, and judging our boundary by their diff
would fail this feature for somebody else's edit.

*"did I edit upstream"* — **prohibition**, and the root filter is exactly wrong: it
asks the accused to define the evidence.

**And the irony is the lesson.** This node already carried the `F135` correction on the
window's TIME axis — anchored to a commit rather than to a ref that moves. The SCOPE
axis stayed broken underneath it, and a fix to one axis reads like a fix to the window.

## What replaced the false claim: naming, never filtering

The prohibition checks now read the **whole** of ``BASE..HEAD``. Every crossing that is
legitimate is named **by full sha**, with the exact paths it touched recorded beside it,
so a commit that later reaches further **fails** instead of inheriting the same name. A
pattern would excuse every future crossing for free; a sha excuses one commit, and a
name for a commit that is not in the window is **dead weight pretending to be a
decision** and is asserted as such.

**The list is long, and its length is the point.** It is the measure of this branch's
debt to upstream, and the reviewer's instruction was that it must APPEAR rather than be
hidden. Fourteen commits, and every one of them was authorised in a governed cycle.

**And the window had an expiry date, and the date was the merge — F135.** The
first version compared ``origin/main...HEAD``. That names the window by a *ref
that moves*, and the ref moves to exactly this branch the moment the feature is
integrated. Measured then, without touching anything:

===============================================  ==========
comparison                                       files
===============================================  ==========
``origin/main...HEAD`` (before the merge)                53
``origin/main...origin/main`` (after it)                  0
===============================================  ==========

With zero files the emptiness guard below does not skip — **it fails**. The node
would have gone red on main at the worst possible moment: the one where the
integration happens. Not when git breaks; **when the work succeeds.**

The window is now anchored to a **recorded commit**, and a commit does not move.
``BASE`` is the parent of this feature's first commit, so ``BASE..HEAD`` still
names this feature's commits after they are on main, after a squash, and after a
rebase that keeps the same base. **The path filter is the other half:** commits
inside the range that touch none of this feature's roots are foreign work that
merged alongside us, and judging our boundary by their diff would fail this
feature for somebody else's edit.

Measured after the change: 18 commits, **53 files, the identical set to the window
it replaces** — same measurement, no expiry date.

**That paragraph is about the ATTRIBUTION window and it is left standing as written**,
because the correction it records is real and still holds. What it did not say — and
what `F-1` cost a cycle to find — is that the same window was answering the prohibition
question too, where its root filter made fourteen crossings invisible.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]

#: The four packages this feature reads and must not change.
UPSTREAM = ("semantic_catalog", "analytics_query", "analytics_interaction", "channel_integration")

#: The parent of this feature's first commit, recorded once and measured with
#: ``git rev-parse $(git log --format=%H --reverse origin/main..HEAD | head -1)^``.
#: It equalled ``origin/main`` on the day it was recorded, which is precisely the
#: point: **it is that commit, not that ref.** The ref will move; this will not.
BASE = "646385695dd8be2bb4870f0324a2a75556f7ef18"

#: What this feature owns. Not an allowlist of untouched files -- a declaration of
#: which commits are ours, used to *exclude* foreign commits from the range.
#: `spec.md` lives under the second root and predates this branch, so the ``BASE``
#: anchor is what keeps the commit that created it out of the window.
FEATURE_ROOTS = (
    "packages/anomaly_investigation",
    "specs/005-anomaly-investigation",
    ".github/workflows/anomaly-investigation.yml",
)

#: Everything the three prohibitions below watch, as path prefixes.
WATCHED_PREFIXES = (
    *(f"packages/{package}/" for package in UPSTREAM),
    "semantic/",
    "channel_governance/",
)

#: **Every commit on this branch that crosses into upstream or governed content, named
#: by full sha with the exact paths it touched.**
#:
#: Recorded rather than filtered, and recorded WITH ITS REACH, so a commit that later
#: touches one more file fails here instead of inheriting the name it already has. A
#: pattern — "ignore commits whose subject starts with `feat(001)`" — would excuse every
#: future crossing for free.
#:
#: **The length is the measure of this branch's debt to upstream**, and it is meant to be
#: read. Every entry was authorised in a governed cycle: the `D-1` signature and its
#: revert, the three owner decisions `OD-1`, `OD-2` and `OD-3`, ADR 0033 and the caller
#: that binds to content, the `F-F` and `F-G` corrections, the minimum path, the coverage
#: observation, and the draft-definition scan that only held while nothing was
#: publishable.
AUTHORIZED_CROSSINGS: dict[str, tuple[str, ...]] = {
    # OD-154: o vigia dos ficheiros respeita o gitignore
    "5c2c09abcdf59227a31abe5c3e472fdef0cb2b7d": (
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
    ),
    # ciclo 565: DECLARAR e ele proprio uma travessia. O 42447a6 declarou os dois commits
    # anteriores nas tres guardas, e para isso editou a 004, que vive em channel_integration --
    # pacote que ESTA guarda vigia. A corrente segue para a 006 e termina la, porque ninguem
    # vigia insights_prioritisation. Apanhado pelo portao de push, nao por leitura.
    "42447a6505bee4b97162aa13a9386096d2e871c6": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 565 (catalog vermelho ha 17 runs): o pyright estrito do catalog.yml nao resolvia
    # `from google.cloud import bigquery` porque o pin morava no analytics_query e o runner
    # instala SO este pacote. O manifesto passa a declarar o que o pacote importa, e o no novo
    # afirma essa propriedade alcancando import dentro de corpo de funcao.
    "11398b2add9beda0f0605083dadb1501b5ba6856": (
        "packages/semantic_catalog/pyproject.toml",
        "packages/semantic_catalog/tests/contract/test_the_package_declares_what_it_imports.py",
    ),
    # ciclo 565 (o 2o vermelho, que o 1o escondia): a particao de skips do catalog.yml nomeava
    # um arquivo so, e o 472763b acrescentou um segundo com o motivo JA tolerado. O no deriva a
    # lista viva da fonte e falha nomeando a particao. O catalog.yml nao e caminho vigiado.
    "32a7e505c5df87de86a5ed41bce7c58bc02599eb": (
        "packages/semantic_catalog/tests/contract/test_the_declared_skip_partition_is_current.py",
    ),
    # ciclo 545: a assinatura de frescor re-vinculada (a9e6f12 -> 1ed945f, o cofre do D-1 que o
    # commit do D-2 esqueceu) e a travessia do no da direcao declarada na vigia por PATH.
    "08b286bf51511ce20d285e9cae410aaef5e6b134": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "semantic/governance/freshness-approvals.yaml",
    ),
    # ciclo 545 (D-1303/T1311): o bump SCHEMA_VERSION 2->3 do 472763b renomeou
    # test_t023_unsupported_schema_version_is_refused[3] para [4] -- a parametrizacao e
    # SCHEMA_VERSION + 1 e ja era derivada. O baseline do T106 guardava o id velho; o
    # teste do 001 estava certo. Mesma forma do 2cf88c2, que fez [2]->[3] pela mesma causa.
    "2ba29241ea96f79830a521f5882ce51d823ba78d": (
        "packages/channel_integration/tests/fixtures/upstream_node_ids.json",
    ),
    # ciclo 545 (S-39-2a): cofre re-vinculado; os 51 yamls do catalogo sobem para v3.
    "1ed945f5eaa6f7d724a16a7e3c38192e421c2b21": (
        "packages/semantic_catalog/tests/unit/test_cli_exit_codes.py",
        "semantic/comparability/android_app_vs_ios_app.yaml",
        "semantic/comparability/android_app_vs_website.yaml",
        "semantic/comparability/apple_app_store_vs_galaxy_store.yaml",
        "semantic/comparability/downloads_vs_installs.yaml",
        "semantic/comparability/downloads_vs_new_users.yaml",
        "semantic/comparability/google_play_vs_apple_app_store.yaml",
        "semantic/comparability/google_play_vs_galaxy_store.yaml",
        "semantic/comparability/ios_app_vs_website.yaml",
        "semantic/comparability/sessions_vs_active_users.yaml",
        "semantic/content/reason-messages.pt-BR.yaml",
        "semantic/dimensions/app_version.yaml",
        "semantic/dimensions/country.yaml",
        "semantic/dimensions/date.yaml",
        "semantic/dimensions/game.yaml",
        "semantic/dimensions/platform.yaml",
        "semantic/dimensions/product.yaml",
        "semantic/dimensions/store.yaml",
        "semantic/glossary/active_user.yaml",
        "semantic/glossary/additivity.yaml",
        "semantic/glossary/cohort.yaml",
        "semantic/glossary/cohort_maturity.yaml",
        "semantic/glossary/delay_tolerance.yaml",
        "semantic/glossary/exact_day_retention.yaml",
        "semantic/glossary/pending_metric.yaml",
        "semantic/glossary/reporting_timezone.yaml",
        "semantic/glossary/session.yaml",
        "semantic/glossary/source_availability.yaml",
        "semantic/governance/access-tags.yaml",
        "semantic/governance/definition-approvals.yaml",
        "semantic/governance/freshness-approvals.yaml",
        "semantic/governance/pending-visibility-approvals.yaml",
        "semantic/metrics/active_users.yaml",
        "semantic/metrics/average_rating.yaml",
        "semantic/metrics/crash_rate.yaml",
        "semantic/metrics/downloads.yaml",
        "semantic/metrics/installs.yaml",
        "semantic/metrics/new_users.yaml",
        "semantic/metrics/retention_rate_d1.yaml",
        "semantic/metrics/retention_rate_d30.yaml",
        "semantic/metrics/retention_rate_d7.yaml",
        "semantic/metrics/review_count.yaml",
        "semantic/metrics/sessions.yaml",
        "semantic/owners.yaml",
        "semantic/policies/catalog-policy.yaml",
        "semantic/sources/android_app.yaml",
        "semantic/sources/apple_app_store.yaml",
        "semantic/sources/galaxy_store.yaml",
        "semantic/sources/google_play.yaml",
        "semantic/sources/ios_app.yaml",
        "semantic/sources/subscription_daily.yaml",
        "semantic/sources/website.yaml",
    ),
    # ciclo 545 (D-1303/T1311): a polaridade sai da view e passa ao contrato da metrica.
    "472763bcb89f832f26568b6c8d0f5cf0db98f147": (
        "packages/semantic_catalog/src/semantic_catalog/contracts/_base.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/classification.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/metric.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/upgrade.py",
        "packages/semantic_catalog/tests/contract/test_the_declared_direction_matches_the_source.py",
        "semantic/metrics/cac_brl.yaml",
        "semantic/metrics/cancellations_qty.yaml",
        "semantic/metrics/cancellations_rate.yaml",
        "semantic/metrics/chargeback_qty.yaml",
        "semantic/metrics/chargeback_rate.yaml",
        "semantic/metrics/ltv_months.yaml",
        "semantic/metrics/ltv_usd.yaml",
        "semantic/metrics/mau.yaml",
        "semantic/metrics/mrr_usd.yaml",
        "semantic/metrics/new_trials.yaml",
        "semantic/metrics/not_renewed_qty.yaml",
        "semantic/metrics/not_renewed_rate.yaml",
        "semantic/metrics/paid_subscribers.yaml",
        "semantic/metrics/plan_share_annual.yaml",
        "semantic/metrics/plan_share_monthly.yaml",
        "semantic/metrics/plan_share_quarterly.yaml",
        "semantic/metrics/plan_share_semiannual.yaml",
        "semantic/metrics/revenue_usd.yaml",
        "semantic/metrics/sales_qty.yaml",
        "semantic/metrics/trial_conversion_rate.yaml",
    ),
    # ciclo 545 (D-1303, bump v3): a prosa que o D-1303 e o bump para v3 deixaram falsa.
    "62422cf034778a93ddb2064a7315a8058f5bd618": (
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/_base.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/load.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/upgrade.py",
    ),
    # ciclo 542 (OD-110): tipos do pacote no diff do S-41; termina na 006.
    "5512268e61a7527a7bc2e3de8d5900c7337f0250": (
        "packages/semantic_catalog/tests/contract/test_the_fixture_step_asserts_the_refusal.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
    ),
    # ciclo 542 (S-41): ausencia nao e resposta -- a regra da classe no script; termina na 006.
    "899c09ef64fe1229f14ac3fc07484cc98dae39e3": (
        "packages/semantic_catalog/tests/contract/test_the_fixture_step_asserts_the_refusal.py",
    ),
    # ciclo 542 (OD-110): load_readiness endurecido, a classe uma camada abaixo; termina na 006.
    "efab0b5623c580d8ff10b8190eb890d5fcc91c9c": (
        "packages/semantic_catalog/src/semantic_catalog/compliance/readiness.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
    ),
    # ciclo 542 (OD-110): vigia da 004, razao re-derivada; termina na 006.
    "cf9d9389822de9b1d2d12370bd19f68b234dc0d5": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 542 (S-40): vigia da 004; termina na 006.
    "9a24db9b6f473b818d3079898f6a49855877ffb8": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 542 (S-40): os 3 passos de fixture afirmam a recusa; termina na 006.
    "9d010fae2ee6d21f9418561fcde9b74f252a3da9": (
        "packages/semantic_catalog/tests/contract/test_the_fixture_step_asserts_the_refusal.py",
    ),
    # ciclo 542 (S-39): re-vinculo do cofre + no da distincao; termina na 006.
    "0ee378017a2950d213bb005cf6e7b724030736f4": (
        "packages/semantic_catalog/tests/contract/test_definition_approvals_current.py",
        "semantic/governance/definition-approvals.yaml",
    ),
    # ciclo 542 (OD-106): d_12 declara; termina na 006.
    "2cea55e78a74f7f3ed39bf11d71f50f863b2dd2d": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 542 (OD-106): d_12 declara; termina na 006.
    "1bbaa031759db5c5be9b1091151cc11b530ebabc": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 542 (OD-106): d_12 declara; termina na 006.
    "b43857806e92c64b904b5b63365278da2bbb3bd3": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py",
    ),
    # ciclo 542 (OD-106): d_12 declara; termina na 006.
    "e21d65b5bae35360506ebf72a040c3f866bdac46": (
        "packages/semantic_catalog/src/semantic_catalog/contracts/classification.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/metric.py",
        "packages/semantic_catalog/src/semantic_catalog/validation/l3_reconciliation.py",
        "packages/semantic_catalog/tests/fixtures/coverage/observed.yaml",
        "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py",
        "packages/semantic_catalog/tests/unit/test_l3_l4_validation.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
        "semantic/metrics/active_users.yaml",
        "semantic/metrics/average_rating.yaml",
        "semantic/metrics/cancellations_qty.yaml",
        "semantic/metrics/cancellations_rate.yaml",
        "semantic/metrics/chargeback_qty.yaml",
        "semantic/metrics/chargeback_rate.yaml",
        "semantic/metrics/crash_rate.yaml",
        "semantic/metrics/downloads.yaml",
        "semantic/metrics/installs.yaml",
        "semantic/metrics/ltv_months.yaml",
        "semantic/metrics/ltv_usd.yaml",
        "semantic/metrics/mau.yaml",
        "semantic/metrics/mrr_usd.yaml",
        "semantic/metrics/new_trials.yaml",
        "semantic/metrics/new_users.yaml",
        "semantic/metrics/not_renewed_qty.yaml",
        "semantic/metrics/not_renewed_rate.yaml",
        "semantic/metrics/paid_subscribers.yaml",
        "semantic/metrics/plan_share_annual.yaml",
        "semantic/metrics/plan_share_monthly.yaml",
        "semantic/metrics/plan_share_quarterly.yaml",
        "semantic/metrics/plan_share_semiannual.yaml",
        "semantic/metrics/retention_rate_d1.yaml",
        "semantic/metrics/retention_rate_d30.yaml",
        "semantic/metrics/retention_rate_d7.yaml",
        "semantic/metrics/revenue_usd.yaml",
        "semantic/metrics/review_count.yaml",
        "semantic/metrics/sales_qty.yaml",
        "semantic/metrics/sessions.yaml",
        "semantic/metrics/trial_conversion_rate.yaml",
    ),
    # ciclo 539 (S-38): credencial injetada; termina na 006.
    "ec8c24f8f41f5e826487723d97fb5b035e11ba83": (
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/freshness/warehouse_read.py",
        "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py",
    ),
    # ciclo 539 (T109): condicoes 2-5 do D-12; termina na 006.
    "45c3b1c1d9bb2e6f5647bc16ace3b21624e1a71e": (
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/freshness/warehouse_read.py",
        "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py",
    ),
    # ciclo 539: allowlist do 004; termina na 006.
    "4a9468e252e81b3fe639a0a091d286f94e69d0a0": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 537: canal fora do sink + twenty-seven; termina na 006.
    "4f0ac462c89e61ba759f3be08aef16788b8111c5": (
        "packages/channel_integration/tests/contract/test_release_record_counts.py",
        "packages/semantic_catalog/src/semantic_catalog/provenance/file_archive.py",
    ),
    # ciclo 537 (OD-103): o sink do D-13 na 001; termina na 006.
    "c66f0c35e337691644fde14fe08da984933fa072": (
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/provenance/file_archive.py",
        "packages/semantic_catalog/tests/contract/test_operational_audit_archive.py",
    ),
    # ciclo 537 (OD-103): d_10/ext_b declarados; termina na 006.
    "40390c10f597fa8a82f780343d3e52dd108ef327": (
        "packages/semantic_catalog/src/semantic_catalog/compliance/readiness.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
    ),
    # ciclo 537: onda dos NOVE nos agregados; termina na 006.
    "e8da15093102a96ef28f2e3a50816e4bc2271064": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
    ),
    # ciclo 537: allowlist do 004; termina na 006.
    "c3d783161e0bffc28d3906835db0d276277e3e2d": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 533: declaracao no vigia do 004; termina na 006.
    "798c6f16a5251f82773f8df53df3afc8bccedb79": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 533 (OD-104): o D-18 inteiro; termina na 006.
    "ec6a7ca02bc5cc6de17d037532dcc50010bc2487": (
        "packages/analytics_interaction/README.md",
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fixture_containment.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_no_readiness_claim.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
        "packages/analytics_interaction/tests/unit/test_governance_resolution.py",
        "packages/analytics_interaction/tests/unit/test_period_governance.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
    ),
    # ciclo 527: declaracao no vigia do 004; termina na 006.
    "04964a7f379d4b10bb5b2baaf5025e524117d04b": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 527 (OD-101): o selo do D-21 — interact.py aprende seal ausente; termina na 006.
    "664f91a72c82df11eee0cfa9195b469a4dc01961": (
        "packages/analytics_interaction/src/analytics_interaction/interact.py",
    ),
    # ciclo 527 (OD-101): d_21 declarado + T185; onda de 46 emendas datadas; termina na 006.
    "2ea1234f85c4a3938ba46bdf763077f787dc32c6": (
        "packages/analytics_interaction/README.md",
        "packages/analytics_interaction/tests/adversarial/test_seal_tampering.py",
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_no_readiness_claim.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_clarification_zero_calls.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
    ),
    # ciclo 525: allowlist/re-derivacao do 004 para o cofre do D-2.
    "75e62b3ece5659a0fb1692a0503e419bf4a85df4": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 525 (varredura): cofre do D-2 + ondas.
    "5a58e1f164f39d410ed795784173c6d04411bef4": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
    ),
    # ciclo 525 (varredura): cofre do D-2 + ondas.
    "f8713808603215d11c4c19231240e3bcccb5f28c": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/semantic_catalog/src/semantic_catalog/compliance/readiness.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/definition_approval.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/load.py",
        "packages/semantic_catalog/tests/contract/test_definition_approvals_current.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
        "semantic/governance/definition-approvals.yaml",
    ),
    # ciclo 523 (OD-100): definicoes decididas nos 19 yamls do semantic.
    "768f471979bde1212a9fef5469cd10b2f95fb8a7": (
        "semantic/metrics/cac_brl.yaml",
        "semantic/metrics/cancellations_qty.yaml",
        "semantic/metrics/cancellations_rate.yaml",
        "semantic/metrics/chargeback_qty.yaml",
        "semantic/metrics/chargeback_rate.yaml",
        "semantic/metrics/ltv_months.yaml",
        "semantic/metrics/ltv_usd.yaml",
        "semantic/metrics/mau.yaml",
        "semantic/metrics/mrr_usd.yaml",
        "semantic/metrics/not_renewed_qty.yaml",
        "semantic/metrics/not_renewed_rate.yaml",
        "semantic/metrics/paid_subscribers.yaml",
        "semantic/metrics/plan_share_annual.yaml",
        "semantic/metrics/plan_share_monthly.yaml",
        "semantic/metrics/plan_share_quarterly.yaml",
        "semantic/metrics/plan_share_semiannual.yaml",
        "semantic/metrics/revenue_usd.yaml",
        "semantic/metrics/sales_qty.yaml",
        "semantic/metrics/trial_conversion_rate.yaml",
    ),
    # ciclo 499 (T0): o allowlist do 004 ganhou a entrada do arquivo acima e a
    # frase-copia foi a 70/18/52.
    "3b8db05111667982347cbf54fab0f1472f19f6ca": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 501 (OD-86, terceira onda): nomes fincados restaurados (baseline do 004 le
    # rename como remocao) + 2 nos de readiness do 004 emendados + rewrap de lint.
    "f14741489f6ab4cf658ffda784a38812868c31b0": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_query/tests/contract/test_readiness.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 517: allowlist/re-derivacao do 004 (350140d).
    "350140dc4e93faf3d5d5b765935eb772ab8627e6": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 521 (S-34): no da assinatura re-derivado pelo caminho publico.
    "ad476027c1c227510e31732a04ed5c5ad60c5f42": (
        "packages/semantic_catalog/tests/contract/test_freshness_signature_current.py",
    ),
    # ciclo 519 (varredura da janela): commit de guards/rewrap tocou vigiados.
    "5f781d2d1bd0cdb302ef472101b65de7973e84c9": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 519 (varredura da janela): commit de guards/rewrap tocou vigiados.
    "41ce503046709bfbf34fe1b4bff19dbbc346ce4c": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 519 (2a onda de guards): allowlist do 004 + conjunto nomeado re-derivado.
    "61d4c08b029f1cae8ab557082c7dc03a8a92323d": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 519 (leitores): enum do 001 += D_1; 003 aceita declared_by_role; guard node.
    "a260781f34da8b9a3324c3ca5c86aad531e2a1e3": (
        "packages/analytics_interaction/src/analytics_interaction/compliance/readiness.py",
        "packages/semantic_catalog/src/semantic_catalog/compliance/readiness.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
    ),
    # ciclo 519 (OD-99): escopo real do D-1, frescor reassinado, d_1 declarado; ondas.
    "ec30718f65ed89ecfc50501a5f8be188d6ac303a": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/semantic_catalog/tests/contract/test_freshness_signature_current.py",
        "semantic/governance/freshness-approvals.yaml",
    ),
    # ciclo 517 (S-33): ge=0 no contrato do QueryPolicy — o zero do OD-97 representavel.
    "1f366c4412276a3ab65d443ea7c4c97e601361bb": (
        "packages/analytics_query/src/analytics_query/contracts/policy.py",
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/analytics_query/tests/contract/test_foundational_contracts.py",
    ),
    # ciclo 515 (OD-97): d_16 declarado — ondas do trio em 002/003/004.
    "52e461f829948a0b1b3905732cca8d7229206c52": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
        "packages/analytics_query/tests/contract/test_readiness.py",
        "packages/analytics_query/tests/integration/test_fail_closed.py",
        "packages/analytics_query/tests/integration/test_quickstart_scenarios.py",
        "packages/analytics_query/tests/integration/test_single_metric_query.py",
        "packages/analytics_query/tests/unit/test_range_limits_and_reporting.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
    ),
    # ciclo 513 (segunda onda): nos da 001 aprendem o fecho datado; marcador de volta na 002.
    "fa2f2c46923c1f34731dad9c7e49f6234cdc0572": (
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
    ),
    # ciclo 513 (OD-93/94): T123/T124/T158 fechadas, D-14 governada; ondas emendadas em
    # 002/003/004 (padrao das viradas de registro).
    "14afd9de74d028c39f126c3c99134bd9be28d958": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/analytics_query/tests/contract/test_readiness.py",
        "packages/analytics_query/tests/integration/test_fail_closed.py",
        "packages/analytics_query/tests/integration/test_quickstart_scenarios.py",
        "packages/analytics_query/tests/integration/test_single_metric_query.py",
        "packages/analytics_query/tests/unit/test_range_limits_and_reporting.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
    ),
    # ciclo 510 (OD-91): o d_34 foi declarado — nos do 004 emendados para o conjunto
    # {d_24,d_34}; CLOSED_LOCKS derivado perdeu o param (1395->1393, derivacao).
    "9d41b6533bbe6a96f241f4c2e17f6136c7cdc070": (
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/channel_integration/tests/integration/test_readiness_locks.py",
    ),
    # ciclo 501 (OD-86): a virada acendeu 11 nos do 003 (agregado-NENHUM -> d_15 exato).
    "3e5ca49d077d4e43bf7aab5b88f5908cdf0a0ed2": (
        "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py",
        "packages/analytics_interaction/tests/contract/test_baseline_deviation.py",
        "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py",
        "packages/analytics_interaction/tests/contract/test_fr_coverage.py",
        "packages/analytics_interaction/tests/contract/test_readiness.py",
        "packages/analytics_interaction/tests/contract/test_sc_coverage.py",
        "packages/analytics_interaction/tests/contract/test_terminal_convergence.py",
        "packages/analytics_interaction/tests/eval/test_grader_regression.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py",
        "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py",
    ),
    # ciclo 501 (OD-86): allowlist do 004 ganhou os 11 caminhos; frase-copia 86/18/68.
    "86bace4c21b755580d1b9d58ada5881a13a13a96": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 501 (OD-86): a declaracao do d_15 acendeu 6 nos do 002 (emendas datadas,
    # oitavo conjunto perfurado + superficie dos cinco com no companheiro).
    "30f9c160845456dec568ab4a469f59d602fb5146": (
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/analytics_query/tests/contract/test_readiness.py",
        "packages/analytics_query/tests/integration/test_fail_closed.py",
        "packages/analytics_query/tests/integration/test_quickstart_scenarios.py",
        "packages/analytics_query/tests/integration/test_single_metric_query.py",
        "packages/analytics_query/tests/unit/test_range_limits_and_reporting.py",
    ),
    # ciclo 501 (OD-86): o allowlist do 004 ganhou as 5 entradas + 5a emenda do scope;
    # frase-copia 75/18/57.
    "61c464d8ed868dbcc80624d4e9dbfd30e0570dbf": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 499 (T0): o no runner-temp do 003 distingue leitura do mapa de renames
    # (.github/upstream-node-renames.txt) de escrita; redirect ao workspace proibido.
    "b6ca95604cb2f919ab28fa2dcefab06ff3f77ca6": (
        "packages/analytics_interaction/tests/contract/test_workflow_node_id_guard.py",
    ),
    # ciclo 495: a fixture _unsupported_version do semantic seguiu a v2 (alvo ":2" + assert
    # de presenca), senao o no de exit 99 media um catalogo valido.
    "5becd366b1dafb36df0b506dc2141762ad0f5eb5": (
        "packages/semantic_catalog/tests/unit/test_cli_exit_codes.py",
    ),
    # ciclo 495: allowlist do vigia do channel ganhou a entrada da propria fixture
    # (M, 2026-09-01) e a frase-copia foi a 69/18/51.
    "d4a6e8facae5d6158053b2059bf8fb7385d77624": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # catalog v1->2: bump mecanico dos 50 yamls (ciclo 495).
    "a9e6f12242c54b5b87e39c71a03308b27c8d438d": (
        "semantic/comparability/android_app_vs_ios_app.yaml",
        "semantic/comparability/android_app_vs_website.yaml",
        "semantic/comparability/apple_app_store_vs_galaxy_store.yaml",
        "semantic/comparability/downloads_vs_installs.yaml",
        "semantic/comparability/downloads_vs_new_users.yaml",
        "semantic/comparability/google_play_vs_apple_app_store.yaml",
        "semantic/comparability/google_play_vs_galaxy_store.yaml",
        "semantic/comparability/ios_app_vs_website.yaml",
        "semantic/comparability/sessions_vs_active_users.yaml",
        "semantic/content/reason-messages.pt-BR.yaml",
        "semantic/dimensions/app_version.yaml",
        "semantic/dimensions/country.yaml",
        "semantic/dimensions/date.yaml",
        "semantic/dimensions/game.yaml",
        "semantic/dimensions/platform.yaml",
        "semantic/dimensions/product.yaml",
        "semantic/dimensions/store.yaml",
        "semantic/glossary/active_user.yaml",
        "semantic/glossary/additivity.yaml",
        "semantic/glossary/cohort.yaml",
        "semantic/glossary/cohort_maturity.yaml",
        "semantic/glossary/delay_tolerance.yaml",
        "semantic/glossary/exact_day_retention.yaml",
        "semantic/glossary/pending_metric.yaml",
        "semantic/glossary/reporting_timezone.yaml",
        "semantic/glossary/session.yaml",
        "semantic/glossary/source_availability.yaml",
        "semantic/governance/access-tags.yaml",
        "semantic/governance/freshness-approvals.yaml",
        "semantic/governance/pending-visibility-approvals.yaml",
        "semantic/metrics/active_users.yaml",
        "semantic/metrics/average_rating.yaml",
        "semantic/metrics/crash_rate.yaml",
        "semantic/metrics/downloads.yaml",
        "semantic/metrics/installs.yaml",
        "semantic/metrics/new_users.yaml",
        "semantic/metrics/retention_rate_d1.yaml",
        "semantic/metrics/retention_rate_d30.yaml",
        "semantic/metrics/retention_rate_d7.yaml",
        "semantic/metrics/review_count.yaml",
        "semantic/metrics/sessions.yaml",
        "semantic/owners.yaml",
        "semantic/policies/catalog-policy.yaml",
        "semantic/sources/android_app.yaml",
        "semantic/sources/apple_app_store.yaml",
        "semantic/sources/galaxy_store.yaml",
        "semantic/sources/google_play.yaml",
        "semantic/sources/ios_app.yaml",
        "semantic/sources/subscription_daily.yaml",
        "semantic/sources/website.yaml",
    ),
    # OD-79: as referencias vivas seguem o endereco; o sweep da prosa segue junto.
    "382f10dd8616f104ba9769fba90e8d2d016e0248": (
        "packages/channel_integration/tests/contract/test_claim_classes.py",
    ),
    "be5e40a7de9dc5e05b44fe41e68853315e59bccb": (
        "packages/channel_integration/tests/contract/test_the_prose_does_not_assert_the_old_world.py",
    ),
    # a declaracao do commit de tipos atualizou o why no guarda da 004.
    "fd464cb4d186e31613d2b2b760576d60f5f0647c": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # tipos estritos do CI local (OD-73 preparando o merge): o espiao do OD-69 ganhou a
    # assinatura do protocolo -- comportamento identico, suites verdes.
    "c8d2ae1e0e5fb0fe9bd1ae066013957bd25df7db": (
        "packages/analytics_interaction/tests/integration/test_stateless_clarification.py",
    ),
    # a entrada que o move deixou stale saiu do allowlist da 004 -- diff liquido zero.
    "45317aaba8c7c52302c7964955782ca40ce94b5e": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # a declaracao do OD-70/71 nos tres vigias tambem tocou o guarda da 004.
    "7e89f97899d36ee4a2d9b027339441762dd7eef2": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 459, a frase-copia da allowlist do channel seguindo a lista (68, 18, 50) --
    # commit que nasceu DEPOIS da medicao daquele ciclo e ficou sem nome ate agora.
    "e080c16f3f0cb8ebe307bee963d2bccb8cfa52f7": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # o move do OD-70: para estes _files_of o rename e delete+add, e o caminho velho conta.
    "c2434f564c14525f6f1b117a59122d7ff921aacf": ("semantic/report/section_order.yaml",),
    # a declaracao do OD-70/71 tocou o guarda da 004.
    "8d3e7a6df8654c903a4bc6475546d7d29188f940": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # a mudanca de chao do OD-70: o yaml sai de semantic/ (chao do catalogo, medido com 131
    # UnknownKindError) para report_governance/, arvore governada propria do relatorio.
    # `OD-70`/`OD-71`: a ordem das secoes vira DADO GOVERNADO em semantic/report/ (dois scans
    # da 008 proibem o atalho de escrever nomes da view no pacote), e MRR/Revenue ganham as
    # duas moedas da MESMA linha da view.
    "2af36b99abfca7037207babeb9d9031b34296c44": ("semantic/report/section_order.yaml",),
    # `OD-69`: a declaracao da emenda tocou o guarda da 004; e o ajuste de linha idem.
    "a2380e84de2f30c837c02a36734823095a666d25": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "20fe58b317a46af9554a2f1e5eef2c7992436c57": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # `OD-69`, 2026-08-31: o dono emendou a fronteira do 003 -- a memoria da 011 alcanca o
    # resume PELO contrato (ConversationMemory), nunca por caminho proprio, nunca texto cru.
    # Os guards do 003 foram REESCRITOS para vigiar a regra nova; toda outra persistencia
    # segue proibida.
    "5ec2d761e79fe560b77212a2fb1fe1cfec606abd": (
        "packages/analytics_interaction/src/analytics_interaction/clarification/future_store.py",
        "packages/analytics_interaction/src/analytics_interaction/clarification/resume.py",
        "packages/analytics_interaction/tests/contract/test_no_persistence.py",
        "packages/analytics_interaction/tests/integration/test_stateless_clarification.py",
        "packages/analytics_interaction/tests/unit/test_clarification_lifecycle.py",
    ),
    # `008` OD-40: o CAC ganha declaracao de INATIVO no proprio contrato -- status
    # unavailable, com razao e data -- porque ele mandou tirar da lista. A omissao do
    # relatorio e DERIVADA dessa declaracao, nunca de um nome escrito em codigo.
    "26e79b78a53ba29e27c17d042f31128048902719": ("semantic/metrics/cac_brl.yaml",),
    # `008`: a declaracao da travessia da T829, e ela e ela mesma uma travessia -- nomear um
    # cruzamento e trabalho que cruza. Termina aqui: o proximo commit nao toca arquivo
    # vigiado por este guarda.
    "2cf88c2d00f03de6b8611789678faba8902b20e4": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/channel_integration/tests/fixtures/upstream_node_ids.json",
    ),
    # `008` T829: os dezenove KPIs entram no catalogo. Cruza a `001` porque o campo do
    # `FR-806` nasce no modelo e o `FR-808` move a versao de esquema junto com ele.
    "3222492d1e048770c55343fbca219b7137942465": (
        "packages/semantic_catalog/src/semantic_catalog/contracts/_base.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/classification.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/metric.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/upgrade.py",
        "packages/semantic_catalog/tests/contract/test_published_table_consistency.py",
        "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
        "packages/semantic_catalog/tests/integration/test_projection_leakage.py",
        "packages/semantic_catalog/tests/unit/test_classification_and_export.py",
        "packages/semantic_catalog/tests/unit/test_compliance.py",
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
        "semantic/metrics/cac_brl.yaml",
        "semantic/metrics/cancellations_qty.yaml",
        "semantic/metrics/cancellations_rate.yaml",
        "semantic/metrics/chargeback_qty.yaml",
        "semantic/metrics/chargeback_rate.yaml",
        "semantic/metrics/ltv_months.yaml",
        "semantic/metrics/ltv_usd.yaml",
        "semantic/metrics/mau.yaml",
        "semantic/metrics/mrr_usd.yaml",
        "semantic/metrics/new_trials.yaml",
        "semantic/metrics/not_renewed_qty.yaml",
        "semantic/metrics/not_renewed_rate.yaml",
        "semantic/metrics/paid_subscribers.yaml",
        "semantic/metrics/plan_share_annual.yaml",
        "semantic/metrics/plan_share_monthly.yaml",
        "semantic/metrics/plan_share_quarterly.yaml",
        "semantic/metrics/plan_share_semiannual.yaml",
        "semantic/metrics/revenue_usd.yaml",
        "semantic/metrics/sales_qty.yaml",
        "semantic/metrics/trial_conversion_rate.yaml",
    ),
    # `008`: S-5, the prose that kept asserting the world `OD-18` ended. The guard it adds
    # sweeps every package, so it lives in `004` beside the readiness vocabulary it reads.
    "bbd42c4a635175f441c0e5c961ff1898937e30c2": (
        "packages/channel_integration/src/channel_integration/cli/main.py",
        "packages/channel_integration/tests/adversarial/test_fixture_substitution.py",
        "packages/channel_integration/tests/contract/test_the_prose_does_not_assert_the_old_world.py",
    ),
    # `008`: S-4, the record created and never enumerated
    "1279b55846790e8c14e9e54748ed869e44e9310c": (
        "packages/channel_integration/src/channel_integration/cli/main.py",
        "packages/channel_integration/src/channel_integration/compliance/readiness.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/channel_integration/tests/contract/test_the_split_key_is_asked_by_its_callers.py",
        "packages/channel_integration/tests/integration/test_readiness_locks.py",
    ),
    # `008`: the split key repointed at its eight callers, and the CLI word corrected
    "4a6b3f47486da71c047764bc7846bfce6c87db5f": (
        "packages/channel_integration/src/channel_integration/adapters/generic/delivery.py",
        "packages/channel_integration/src/channel_integration/adapters/slack/delivery.py",
        "packages/channel_integration/src/channel_integration/adapters/telegram/delivery.py",
        "packages/channel_integration/src/channel_integration/adapters/whatsapp/delivery.py",
        "packages/channel_integration/src/channel_integration/cli/main.py",
        "packages/channel_integration/src/channel_integration/compliance/readiness.py",
        "packages/channel_integration/tests/adversarial/test_fixture_substitution.py",
        "packages/channel_integration/tests/contract/test_cli.py",
        "packages/channel_integration/tests/contract/test_the_split_key_is_asked_by_its_callers.py",
    ),
    # `008`: four more nodes asserting the old world, harness guard included
    "266b37144ebb48c92c4adbc6c784e7dc24f15240": (
        "packages/channel_integration/tests/contract/test_fifth_channel.py",
    ),
    # `008`: OD-20-A splits the key, and 24 nodes across seven files re-derived
    "9fc3b62188d6b8878fe15b704f9d2fcc733575e1": (
        "packages/channel_integration/src/channel_integration/compliance/readiness.py",
        "packages/channel_integration/src/channel_integration/inbound/verify.py",
        "packages/channel_integration/tests/adversarial/test_fixture_substitution.py",
        "packages/channel_integration/tests/contract/test_cli.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/channel_integration/tests/contract/test_replay_defence_bound.py",
        "packages/channel_integration/tests/integration/test_readiness_locks.py",
        "packages/channel_integration/tests/integration/test_refusal_paths.py",
        "packages/channel_integration/tests/integration/test_round_trip.py",
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
    ),
    # `008` Phase E: the replay gate's count proxy re-derived; d_24 declaration withdrawn
    "f6bd047124f188e7ee66759852b32bc1d49b65ca": (
        "packages/channel_integration/tests/contract/test_replay_defence_bound.py",
    ),
    "73088752285d82ac965d9c800dca631d3b27476f": (  # ADR 0034 recorded in 004's allowlist
        # The gate said what to do rather than only that something was wrong, and this is the
        # doing: the ADR names the change, so the allowlist records it with the ADR cited.
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "0c619d0780cae6894e99f5ee3486156d9c4b73a6": (  # ADR 0034: two guard repairs
        # Both defects were IN THE GUARDS: one presence check searched its own source for a
        # literal its own assertion writes, and the freeze check read only the working tree,
        # so a modification survived by being committed. The crossing is the repair reaching
        # the frozen package, and its scope is the ADR's table rather than this list's.
        "packages/analytics_query/tests/contract/test_adr0010_baseline.py",
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
    ),
    "33d99f85a69dd6cdd35e761a4942f941b901507e": (  # the 77 strict errors, ordered by the cycle
        # ONE OF THESE WAS A LIVE DEFECT AND NOT A TYPING COMPLAINT: `cli/main.py` read a
        # `yaml.safe_load` document whose values were untyped, and the same class of read in
        # `figures_port` -- this feature's own file, not a crossing -- was calling an attribute
        # that does not exist, so every governed refusal it carried raised `AttributeError`.
        # The crossing is the repair reaching where the untyped read lives.
        "packages/analytics_interaction/tests/contract/test_fixture_containment.py",
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
    ),
    "162c22fb906fd16e680c8cf068a15607e0e5b09d": (  # D-1 signed on his word
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
        "semantic/governance/freshness-approvals.yaml",
    ),
    "b4b4996c602036fc1da08fba42dac4e2dbd2e4a5": (  # D-1 unsigned, same day, his decision
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
        "semantic/governance/freshness-approvals.yaml",
    ),
    "7c5e57705c51697fea7815cc441bbff16a43c80e": (  # the minimum path: one source, one metric
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/semantic_catalog/tests/contract/test_baseline_reconciliation.py",
        "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
        "packages/semantic_catalog/tests/integration/test_projection_leakage.py",
        "packages/semantic_catalog/tests/unit/test_compliance.py",
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
        "semantic/metrics/new_trials.yaml",
        "semantic/sources/subscription_daily.yaml",
    ),
    "959bb92e0ca3c2efa8576633a62cc7c74a1c9c7f": (  # the allowlist 004's gate was owed
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "bd035b097b43382238d16888bd748c302d185608": (  # OD-2, the axes declared NOT APPLICABLE
        "semantic/dimensions/country.yaml",
        "semantic/dimensions/date.yaml",
    ),
    "5418291b1dde5e012d253464c4d9ffac7bca9590": (  # OD-1, the product is Windows-only
        "semantic/dimensions/platform.yaml",
        "semantic/dimensions/product.yaml",
    ),
    "78900ccf04e0d5e860cbcfa8d0b39138201400e0": (  # OD-3, the game axis
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/semantic_catalog/tests/contract/test_concept_disclosure.py",
        "semantic/dimensions/game.yaml",
        "semantic/metrics/new_trials.yaml",
    ),
    "5f33ffc3b544c37331710ec6261a898125dc365b": (  # the two signatures he authorized
        "packages/analytics_interaction/tests/contract/test_fixture_containment.py",
        "packages/analytics_interaction/tests/unit/test_governance_resolution.py",
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
        "semantic/governance/freshness-approvals.yaml",
    ),
    "74ff8cfb9374fa7e23f02c42c2f08b7345189ab7": (  # F-F written into the file itself
        "semantic/governance/freshness-approvals.yaml",
    ),
    "7ebd309932858fc505f43b093866dbada3519c16": (  # ADR 0033 executed in the library
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/freshness_approval.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/bundle.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/lifecycle.py",
        "packages/semantic_catalog/src/semantic_catalog/validation/publication.py",
        "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
        "packages/semantic_catalog/tests/unit/test_freshness_approval.py",
        "packages/semantic_catalog/tests/unit/test_retention_pending.py",
    ),
    "cb1c976383b24b6f99b2909d41a26541a950340d": (  # the caller binds to content
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/tests/contract/test_concept_disclosure.py",
        "packages/semantic_catalog/tests/integration/test_adversarial.py",
        "packages/semantic_catalog/tests/integration/test_audit_emission.py",
        "packages/semantic_catalog/tests/integration/test_no_auto_degradation.py",
        "packages/semantic_catalog/tests/integration/test_projection_leakage.py",
        "packages/semantic_catalog/tests/integration/test_provenance_statement.py",
        "packages/semantic_catalog/tests/integration/test_unsafe_combinations.py",
        "packages/semantic_catalog/tests/unit/test_cli.py",
        "packages/semantic_catalog/tests/unit/test_compliance.py",
        "packages/semantic_catalog/tests/unit/test_coverage_freshness_independence.py",
        "packages/semantic_catalog/tests/unit/test_fail_closed.py",
        "packages/semantic_catalog/tests/unit/test_freshness_and_coverage.py",
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
        "packages/semantic_catalog/tests/unit/test_matrix_and_pipeline.py",
        "packages/semantic_catalog/tests/unit/test_search.py",
    ),
    "6f50a737c4bf1a91671848283163c9657be30e8c": (  # F-G, the vacuous check
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/semantic_catalog/tests/integration/test_comparable_window_publication.py",
        "packages/semantic_catalog/tests/integration/test_decision_matrix.py",
        "packages/semantic_catalog/tests/integration/test_deprecation_boundaries.py",
        "packages/semantic_catalog/tests/integration/test_release_lifecycle.py",
        "packages/semantic_catalog/tests/unit/test_as_of_stability.py",
        "packages/semantic_catalog/tests/unit/test_fail_closed.py",
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
    ),
    "197275d23a1ac513295c353faa8373fc3e4ff746": (  # the coverage observation
        "packages/semantic_catalog/tests/fixtures/coverage/observed.yaml",
        "semantic/governance/freshness-approvals.yaml",
        "semantic/metrics/new_trials.yaml",
    ),
    "261fde74ce707ff7ec2b9632a3289565c32e0c58": (  # the draft-definition scan, authorised in 359
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/compliance/leakage_scan.py",
        "packages/semantic_catalog/tests/unit/test_compliance.py",
    ),
    "d4381e2ed6578afb5a87915312cde2077dc656ae": (  # the allowlist a widened push gate found red
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "ddfbd510af30649cc5d44ad9beada78fa968c28b": (  # SC-001 met: available_from follows the view
        "semantic/metrics/new_trials.yaml",
    ),
    "1f8a0a44bd731aa2b21cfe9ac470fea178a4eaa0": (  # OD-124 (c): the vault, read at bundle build
        "packages/semantic_catalog/src/semantic_catalog/loader/lifecycle.py",
        "packages/semantic_catalog/tests/unit/test_a_signed_definition_that_changed_is_refused.py",
    ),
    "77446ab1c44dc3bca2cdff4484f5b8ec15948816": (  # `004`'s allowlist naming the (c) test
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "344496521656598582b1f2b9bfc32d41b59195b3": (  # `004`'s docstring count, 108 to 109
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "4cf4e63b43cf96832476ddbe0c78ff5d52d72d4e": (  # OD-124 (a): the id covers the authored catalog
        "packages/semantic_catalog/src/semantic_catalog/loader/bundle.py",
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
    ),
    "bc33a8488120afe0aa248cbcf444d4d03a591461": (  # S-55: the instrument's docstring says 36 of 71
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
    ),
    "ff03b6bfa540307b76c24fed93a149a148ebb6c6": (  # 013 F5: the plan axis, no source carries it
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
        "semantic/dimensions/plan.yaml",
    ),
    "b99bc7103219d0709866775d53ab3b48c795f660": (  # 013 F5: access map re-derived for 8 axes
        "packages/semantic_catalog/tests/contract/test_concept_disclosure.py",
    ),
    "72c7aa16d38abbbbfead71e415c2108f6a849670": (  # 013 F6: the gateway axis, no source carries it
        "packages/semantic_catalog/tests/contract/test_concept_disclosure.py",
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
        "semantic/dimensions/gateway.yaml",
    ),
    "688ac78421b3725250d392143af3a186b2129144": (  # portao: particao de skip vira MOTIVO
        "packages/semantic_catalog/tests/contract/test_the_declared_skip_partition_is_current.py",
        "packages/semantic_catalog/tests/contract/test_the_fixture_step_asserts_the_refusal.py",
    ),
    "80b801014db5a8f51df1597b247fbc1c01baaee7": (  # portao: skipped julgado, nao vetado
        "packages/channel_integration/tests/contract/test_upstream_node_ids.py",
    ),
    "6a22b8fe14594e4c1a29424f555209fd8f4392d8": (  # portao: xpassed vetado, duas direcoes
        "packages/channel_integration/tests/contract/test_upstream_node_ids.py",
        "packages/semantic_catalog/tests/contract/test_the_declared_skip_partition_is_current.py",
    ),
    "901c0358e1781b7caf7e941dda3fd0dcaaca6ee5": (  # registo ve 789 linhas, nao 739
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
    ),
}


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        pytest.skip(f"git unavailable or base missing: {result.stderr.strip()[:120]}")
    return result.stdout


def _feature_commits() -> list[str]:
    """The commits of this feature: inside the range **and** touching a root."""
    out = _git("log", "--format=%H", f"{BASE}..HEAD", "--", *FEATURE_ROOTS)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _files_of(sha: str) -> list[str]:
    out = _git("show", "--name-only", "--format=", "--no-renames", sha)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _changed_files() -> list[str]:
    """Every file those commits touched, whatever else they touched alongside.

    **The ATTRIBUTION window.** Used where the question is *"which commits are ours"*,
    and never where the question is *"did we edit upstream"* — see the module docstring.
    """
    touched: set[str] = set()
    for sha in _feature_commits():
        touched.update(_files_of(sha))
    return sorted(touched)


def _all_commits() -> list[str]:
    """**The PROHIBITION window: every commit in the range, filtered by nothing.**

    A commit that touches only upstream has no root of ours in it, which is precisely
    why the root filter must not stand between this branch and the checks that forbid
    upstream edits.
    """
    return [
        line.strip()
        for line in _git("log", "--format=%H", f"{BASE}..HEAD").splitlines()
        if line.strip()
    ]


def _crossings_of(sha: str) -> tuple[str, ...]:
    """What one commit touched under the watched prefixes, in a stable order."""
    return tuple(sorted(path for path in _files_of(sha) if path.startswith(WATCHED_PREFIXES)))


def _unnamed_crossings(named: Mapping[str, tuple[str, ...]] | None = None) -> list[str]:
    """Every watched path touched by a commit that is NOT a named crossing.

    This is what the three prohibitions below assert is empty. A legitimate crossing
    leaves the set by being named with its reach recorded; nothing leaves it by being
    filtered.

    ``named`` is a parameter and not a constant read, and that is `G-1`: it is what lets
    a node **drive this function** with one name withheld and assert that the withheld
    crossing comes back. A node that reads the two windows and compares them proves only
    that both exist — the defect was never that one window was missing, it was which one
    this function consumed.
    """
    names = AUTHORIZED_CROSSINGS if named is None else named
    touched: set[str] = set()
    for sha in _all_commits():
        if sha in names:
            continue
        touched.update(_crossings_of(sha))
    return sorted(touched)


def _files_in_the_prohibition_window() -> set[str]:
    """Every file any commit in the range touched, named or not.

    The `spec.md` check reads this: no crossing authorises rewriting the requirement it
    was granted under, so that one has no exemption at all. Extracted into a function so
    a node can drive it the same way it drives `_unnamed_crossings` — see `G-1`.
    """
    return {path for sha in _all_commits() for path in _files_of(sha)}


# --------------------------------------------------------------------------- #
# The window itself, and the failure it used to carry
# --------------------------------------------------------------------------- #


def test_the_diff_is_readable_and_not_empty() -> None:
    """**A comparison that found no changes at all would pass by doing nothing.**

    This feature has changed files; if the window were empty the assertions below
    would be vacuously true, which is the defect this repository keeps closing.
    """
    changed = _changed_files()
    assert changed, "no changes measured against the base -- the check would be vacuous"


def test_the_base_is_a_commit_and_not_a_moving_reference() -> None:
    """**The whole of F135 in one assertion.**

    A ref resolves to whatever it points at today. ``BASE`` must resolve to
    itself, which only a commit id does -- and that is what makes the window
    immune to the merge this feature is heading for.

    **This one holds even where the object is absent**, measured in a shallow
    checkout: ``git rev-parse`` echoes a well-formed id back without proving it
    exists. That is exactly the claim being made here and no more -- *the base is
    spelled as a commit* -- and the test below is what asks whether it is present.
    """
    assert _git("rev-parse", BASE).strip() == BASE


def test_the_base_is_still_an_ancestor_of_head() -> None:
    """Otherwise ``BASE..HEAD`` is empty and every refusal here is vacuous.

    Asserted rather than assumed, because a rebase onto a different base is the
    one operation that would silently empty the window without breaking git.

    **The three exit codes are not the same thing, and treating them alike was a
    defect of the first version of this file.** ``--is-ancestor`` answers ``1``
    for *no*, but ``128`` for *I have never heard of that commit* -- which is what
    a shallow checkout says about every commit but the tip. Measured in a
    ``--depth 1`` clone: the base object is absent, the range is invalid, the ten
    tests around this one skip, and this one **failed**. That is the F135 shape
    again: a boundary node going red for something that is not a boundary
    violation. Absence skips, with the same declared word as everything else here;
    only a real answer of *no* fails.
    """
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE, "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        pytest.skip(f"git unavailable or base missing: {result.stderr.strip()[:120]}")
    assert result.returncode == 0, f"{BASE[:7]} is no longer an ancestor of HEAD"


def test_the_window_does_not_empty_when_the_base_reference_catches_up() -> None:
    """The old mechanism in its post-merge shape, beside the new one.

    ``origin/main...HEAD`` becomes ``origin/main...origin/main`` once this branch
    is on main, and that comparison is **empty by construction** -- the emptiness
    guard above would fail on it. The anchored window is measured over the same
    repository at the same instant and is not empty. **The defect is asserted,
    not merely described in a comment.**
    """
    post_merge_shape = [
        line.strip() for line in _git("diff", "--name-only", "HEAD...HEAD").splitlines()
    ]
    assert not [line for line in post_merge_shape if line], (
        "premise failed: a self-comparison should be empty"
    )
    assert _changed_files(), "the anchored window emptied where the old one did"


def test_foreign_commits_in_the_range_are_not_judged_as_ours() -> None:
    """After the merge the range may hold other people's commits, and the filter
    is what keeps their files out of our boundary claim.

    Asserted as a property of every commit in the window rather than as a count,
    so it keeps meaning the same thing on a branch shaped differently.
    """
    roots = tuple(FEATURE_ROOTS)
    for sha in _feature_commits():
        assert any(path.startswith(roots) for path in _files_of(sha)), (
            f"{sha[:7]} entered the window without touching a feature root"
        )


# --------------------------------------------------------------------------- #
# The boundary
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("package", UPSTREAM)
def test_no_file_of_an_upstream_package_was_changed(package: str) -> None:
    """Any path under `packages/<upstream>/` is an edit, whatever its content.

    Including a test: `FR-008` says the boundary is not widened, and adding a test
    to an upstream suite is changing that package.

    **Measured over the WHOLE range**, because this is a prohibition and the root filter
    would let the accused define the evidence — `F-1`, and the module docstring says how
    it hid fourteen commits.
    """
    prefix = f"packages/{package}/"
    touched = [path for path in _unnamed_crossings() if path.startswith(prefix)]
    assert not touched, f"{package} was edited by a commit nobody named: {touched}"


def test_no_governed_content_was_changed() -> None:
    """`semantic/` is the governed catalog and `channel_governance/` is the
    capability matrix. Neither is this feature's to write.

    Over the whole range, for the same reason as above.
    """
    touched = [
        path
        for path in _unnamed_crossings()
        if path.startswith(("semantic/", "channel_governance/"))
    ]
    assert not touched, f"governed content was edited by a commit nobody named: {touched}"


def test_the_spec_and_its_requirements_were_not_rewritten() -> None:
    """The `FR` and `SC` numbers are the authority this feature is bounded by.

    Its own `tasks.md`, `research.md`, `plan.md` and contracts **may** change --
    those record what was measured. `spec.md` may not.

    **This one reads every commit in the range and is not narrowed by the named list.**
    No crossing authorises rewriting the requirement it was granted under, so `spec.md`
    is checked against the whole window with no exemption at all.
    """
    touched = sorted(
        path
        for path in _files_in_the_prohibition_window()
        if path.endswith("specs/005-anomaly-investigation/spec.md")
    )
    assert not touched, "spec.md was edited"


def test_every_named_crossing_is_still_in_the_window() -> None:
    """**A name for a commit that is not there is dead weight pretending to be a decision.**

    It would sit in this file looking like a considered exception while excusing nothing,
    and the day a rebase or a rewrite moves those shas the list must SAY SO rather than
    quietly shrink. The `005` history was rewritten once already, on his word, and every
    sha on this branch changed with it.
    """
    in_range = set(_all_commits())
    dead = sorted(sha for sha in AUTHORIZED_CROSSINGS if sha not in in_range)
    assert not dead, f"named crossings that are not in {BASE[:7]}..HEAD: {dead}"


@pytest.mark.parametrize("sha", sorted(AUTHORIZED_CROSSINGS))
def test_a_named_crossing_reaches_exactly_as_far_as_recorded(sha: str) -> None:
    """**The exemption is bounded by measurement, not taken on trust.**

    Excusing a commit wholesale is the shape that hides a real violation, so what it
    touched under the watched prefixes is asserted file by file. A commit amended to
    reach one directory further fails here instead of inheriting the name it already
    has.
    """
    assert _crossings_of(sha) == AUTHORIZED_CROSSINGS[sha], (
        f"{sha[:7]} no longer touches what its entry records"
    )


def _invisible_to_the_attribution_window() -> list[str]:
    """Named crossings the root-filtered window cannot see. The probes below use these."""
    ours = set(_feature_commits())
    return sorted(sha for sha in AUTHORIZED_CROSSINGS if sha not in ours)


def test_the_prohibition_actually_consumes_the_unfiltered_window() -> None:
    """**`G-1`: the guard that announced the fix did not hold the fix down.**

    The reviewer reintroduced the original defect in ONE line — ``for sha in
    _all_commits()`` became ``for sha in _feature_commits()`` inside the function that
    feeds all three prohibitions — and the suite stayed green. Two nodes existed
    precisely to stop that. Neither did, because **both asserted that two windows
    EXIST**, and the defect was never a missing window: it was **which window the
    prohibition consumed**. The regression walked between them while the guard announced
    it could not.

    So this drives the function instead of describing it. One named crossing that the
    attribution window **cannot see** is withheld from the list, and its paths must come
    back out. Under the filtered window that commit is not walked at all, nothing comes
    back, and this goes red — which is the whole point.
    """
    invisible = _invisible_to_the_attribution_window()
    assert invisible, (
        "every named crossing also touches a feature root, so this probe cannot tell the "
        "two windows apart and proves nothing"
    )

    probe = invisible[0]
    withheld = {sha: reach for sha, reach in AUTHORIZED_CROSSINGS.items() if sha != probe}
    exposed = set(_unnamed_crossings(withheld))
    recorded = set(AUTHORIZED_CROSSINGS[probe])
    assert recorded, f"{probe[:7]} records no path, so withholding it exposes nothing"
    assert recorded <= exposed, (
        f"withholding {probe[:7]} exposed {sorted(recorded - exposed)} nowhere: the "
        "prohibition is reading the root-filtered window, which is the F-1 defect back"
    )


def test_the_spec_check_also_consumes_the_unfiltered_window() -> None:
    """The same binding for the one prohibition that has no exemption at all.

    `spec.md` is checked against every commit in the range, so a file touched ONLY by a
    commit the attribution window cannot see must be visible to it. Reading the filtered
    window instead would make the check quietly narrower than its own docstring.
    """
    invisible = _invisible_to_the_attribution_window()
    assert invisible
    reachable = _files_in_the_prohibition_window()
    for sha in invisible:
        assert set(_files_of(sha)) <= reachable, (
            f"{sha[:7]} is in the range and its files are not in the window the spec "
            "check reads; that check is narrower than it says it is"
        )


def test_the_prohibition_window_is_wider_than_the_attribution_one() -> None:
    """**A necessary condition, and it is NOT the proof — that is the `G-1` lesson.**

    If both windows held the same commits, the prohibition checks would be reading the
    root-filtered set again under a new name. But equal windows are not the failure this
    file suffered: the windows differed and the prohibition consumed the wrong one
    anyway. This stays as the cheap structural check; the two nodes above are what hold
    the behaviour down.
    """
    everything = set(_all_commits())
    ours = set(_feature_commits())
    assert ours <= everything
    assert len(everything) > len(ours), (
        "every commit in the range touches a feature root, so the prohibition window "
        "and the attribution window are the same set and the fix asserts nothing"
    )


def test_the_prohibition_window_sees_the_crossings_the_old_one_missed() -> None:
    """**Non-vacuity, and it is the assertion that would have caught `F-1` on day one.**

    A window that names no crossing at all would make every refusal above vacuously
    true. This branch DOES cross — fourteen commits of it, every one authorised — so the
    named list must be non-empty and every one of its members must be a commit the old
    root-filtered window could not see.
    """
    assert AUTHORIZED_CROSSINGS, "no crossing is named, so the prohibitions cannot bite"
    ours = set(_feature_commits())
    invisible = [sha for sha in AUTHORIZED_CROSSINGS if sha not in ours]
    assert invisible, (
        "every named crossing also touches a feature root, so the old window would have "
        "caught them all and this file is measuring the wrong thing again"
    )


def test_this_feature_did_change_something_of_its_own() -> None:
    """The mirror of the checks above.

    If nothing under this package changed, every refusal here would be true for a
    branch that did nothing at all -- and would keep being true after this feature
    stopped existing.
    """
    ours = [
        path
        for path in _changed_files()
        if path.startswith(("packages/anomaly_investigation/", "specs/005-anomaly-investigation/"))
    ]
    assert ours, "this feature changed nothing of its own"
