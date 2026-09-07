"""No upstream file was edited — T019 (`FR-008`).

This feature has **zero** authorized upstream additions, and the claim is measured
rather than promised.

**Both `F135` lessons are inherited rather than rediscovered**, which is what the
ledger asks for. They cost `005` a cycle each and neither is obvious from outside.

## Lesson one: the window is anchored to a COMMIT, not to a moving ref

The obvious window is ``origin/main...HEAD``. It names the range by a ref that **moves
to exactly this branch the moment the feature is integrated** — so after the merge the
window is empty, the emptiness guard fires, and the node goes red **when the work
succeeds** rather than when a boundary is crossed.

`BASE` is the parent of this feature's first commit. A commit does not move, so
``BASE..HEAD`` still names this feature's work after a merge, after a squash, and after
a rebase that keeps the same base.

**The path filter is the other half.** Commits inside the range that touch none of this
feature's roots are foreign work that happened alongside — and this branch has a great
deal of it, because it was cut from `005`'s line. Judging our boundary by their diff
would fail this feature for somebody else's edit.

## Lesson two: absence of history SKIPS, a real answer of *no* FAILS

``git merge-base --is-ancestor`` answers ``1`` for *no* and ``128`` for *I have never
heard of that commit* — which is what a shallow checkout says about every commit but
the tip. Asserting ``returncode == 0`` turns **absent history** into **boundary
violation**: the `F135` shape wearing different clothes, a node going red for something
that is not the thing it guards.

## And `005` is upstream HERE, which is the difference from `005`'s own version

`insights_prioritisation` imports `anomaly_investigation` — that is why this branch
could not be cut from `main`. So `anomaly_investigation` joins the four packages `005`
watches: **five upstream packages, not four**. Consulting `005` through its exported
surface is exactly as required as consulting `001`'s, and it is the one most likely to
be widened by accident, because the two features are being written by the same hands on
the same day.
"""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]

#: The five packages this feature reads and must not change.
#:
#: `anomaly_investigation` is here and is not in `005`'s equivalent, for the reason the
#: module docstring gives: this feature imports it, and that import is what forced this
#: branch to be cut from `005`'s line rather than from `main`.
UPSTREAM = (
    "semantic_catalog",
    "analytics_query",
    "analytics_interaction",
    "channel_integration",
    "anomaly_investigation",
)

#: The parent of this feature's first commit, measured with
#: ``git log --format=%H --reverse -- <roots>`` and then ``^`` on the first line.
#:
#: **It is that commit, not that ref**, which is the whole `F135` correction. It was
#: `origin/main` on the day it was recorded and will not be tomorrow.
#:
#: **It has moved twice, and each move is written down rather than noticed later.**
#:
#: First when the `005` history was rewritten on his word -- *"force push!"* -- to drop the
#: three `006` content commits it was carrying, which changed every sha on that line.
#:
#: Then when this branch was **updated from the `005` line it was cut from**, because the
#: shared pre-push gate runs `005`'s suite and the copy of it on this branch predated the
#: fix that skips on an expired credential. The anchor is the parent of this branch's first
#: commit, so bringing `005` forward moved it: it is `005`'s tip at the moment of the LAST
#: rebase. **Measured, and with the guard that decides whether the rebase was honest: the
#: files of THIS feature are byte-identical across it** -- `git diff` over
#: `packages/insights_prioritisation` and `specs/006-insights-and-prioritisation` came back
#: empty.
BASE = "a48ecf1695a615986d70a622370f29fad58574b1"

#: What this feature owns. Not an allowlist of untouched files — a declaration of which
#: commits are OURS, used to exclude foreign ones from the window.
#:
#: This branch carries `005`'s entire history behind it, so without this filter every
#: `005` commit in the range would read as this feature editing upstream.
FEATURE_ROOTS = (
    "packages/insights_prioritisation",
    "specs/006-insights-and-prioritisation",
)


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        pytest.skip(f"git unavailable or base missing: {result.stderr.strip()[:120]}")
    return result.stdout


def _feature_commits() -> list[str]:
    """The commits of this feature: inside the range and touching one of its roots.

    **Nothing is excused.** An earlier version of this file named one sha -- `005`'s
    minimum path, which edited this feature's `spec.md` while doing `005`'s work -- and
    excluded it, with its reach under our roots asserted so the exemption could not
    quietly widen. The rewrite removed the entanglement at the source: that commit no
    longer touches anything of ours, so the exclusion had nothing left to exclude and
    the node that guarded it said so by failing.

    It was deleted rather than emptied. An exclusion set that is empty is a mechanism
    waiting to be used again; with no mechanism, a foreign commit that touches these
    roots fails the boundary node instead of being named out of it.
    """
    out = _git("log", "--format=%H", f"{BASE}..HEAD", "--", *FEATURE_ROOTS)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _files_of(sha: str) -> list[str]:
    out = _git("show", "--name-only", "--format=", sha)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _changed_files() -> list[str]:
    """Every file those commits touched, **whatever else they touched alongside**.

    Deliberately not narrowed to the roots: a commit that edits an upstream package
    beside a feature file is exactly what this node exists to catch, and filtering the
    diff by root would hide it.
    """
    touched: set[str] = set()
    for sha in _feature_commits():
        touched.update(_files_of(sha))
    return sorted(touched)


#: Everything the prohibitions below watch, as path prefixes. Derived from `UPSTREAM` so a
#: sixth upstream package cannot be watched in one place and forgotten in the other.
WATCHED_PREFIXES = (
    *(f"packages/{package}/" for package in UPSTREAM),
    "semantic/",
    "interpretation_governance/",
    "channel_governance/",
)

#: **Every commit in the window that crosses into upstream or governed content, named by
#: full sha with the exact paths it touched.**
#:
#: This did not exist until 2026-08-27, and its absence was a real hole rather than a
#: missing convenience. The prohibitions iterated `_feature_commits()` -- the ROOT-FILTERED
#: window -- so a commit that touched ONLY upstream had no root of this feature in it, was
#: never walked, and edited `src/` of two upstream packages **unseen by every node in this
#: file**. That is `F-1` from cycle 358 again: *the prohibition window filtered by the
#: accused*.
#:
#: Recorded WITH ITS REACH, so a commit that later touches one more watched file fails here
#: instead of inheriting the name it already has. A pattern -- "ignore commits whose subject
#: starts with `fix(types)`" -- would excuse every future crossing for free.
AUTHORIZED_CROSSINGS: dict[str, tuple[str, ...]] = {
    # ciclo 569, S-63: o perdao do ciclo passa a ter prazo. O `row_written < source_rebuilt`
    # da primeira versao e tao verdadeiro para uma hora como para um ano, e uma linha escrita
    # ha um ano nao esta a espera da vez -- esta abandonada. Duas copias paradas a
    # concordarem uma com a outra e o F-4 que aquele ficheiro existe para nomear.
    # Mesmo ficheiro, mesmo alcance de um so caminho: entra so aqui.
    "46b5ca87c36ce501fcdb68915b0395adc314c3d5": (
        "packages/anomaly_investigation/tests/integration/"
        "test_the_recorded_coverage_still_matches_the_view.py",
    ),
    # ciclo 569: a cobertura passa a comparar contra o INSTANTE. O portao de push ficava
    # vermelho UMA HORA POR DIA porque a view e reconstruida primeiro e a linha de
    # disponibilidade so segue ~uma hora depois -- push das 05:37Z passou, o das 06:08Z
    # falhou, mesma arvore. Autorizado pelo reviewer com quatro condicoes de forma.
    # Toca SO um ficheiro, e ele esta no alcance vigiado desta guarda: a conta e a mesma
    # nas duas listas, entao entra so aqui.
    "2b1db7e87a3ddba91aa0496bfbcee4667229fbbe": (
        "packages/anomaly_investigation/tests/integration/"
        "test_the_recorded_coverage_still_matches_the_view.py",
    ),
    # OD-154: o vigia dos ficheiros respeita o gitignore
    "5c2c09abcdf59227a31abe5c3e472fdef0cb2b7d": (
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
    ),
    # a 005 declara o de cima
    "0ed71c36a16910dd26a95648126560048baea43b": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 567: o registo de tarefas ve as 789 linhas, nao 739. ESTE SHA ESTA NOS DOIS
    # dicionarios de proposito: a verificacao de travessia le SO este, com o alcance
    # VIGIADO; a proibicao de spec le os dois, e o no do alcance do FOREIGN_WORK exige o
    # commit inteiro. Duas contas diferentes sobre o mesmo commit, cada uma na sua lista.
    "901c0358e1781b7caf7e941dda3fd0dcaaca6ee5": (
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
    ),
    # ciclo 567: a 005 declara o 901c035
    "5560f4c935c43115c5487fb5030f4f91634679aa": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 565: A CORRENTE DE DECLARAR, e ela termina aqui. O 42447a6 declarou os dois
    # commits do conserto do catalog nas tres guardas e, ao faze-lo, editou a 004 (em
    # channel_integration) e a 005 (em anomaly_investigation) -- os dois vigiados por ESTA.
    # O a930c0b declarou o 42447a6 na 005 e tocou so em anomaly_investigation.
    # Este commit toca so em insights_prioritisation, que ninguem vigia: fim da corrente.
    #
    # Apanhado pelo PORTAO e nao por leitura: job 34, 1 failed de 40, push recusado.
    "42447a6505bee4b97162aa13a9386096d2e871c6": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "a930c0b975995a7bb621e5460e8532e5dec302c5": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # ciclo 545: declarar a travessia do 08b286b tocou o arquivo da 006, e a 005 vigia esse
    # pacote -- entao o proprio commit que declarava virou travessia. Corrente termina AQUI:
    # este commit toca so o arquivo da 005, que a 006 nao vigia.
    "ea0ba48071d6c426fc25f29cde03bc7036b8043a": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 545: a assinatura de frescor re-vinculada (a9e6f12 -> 1ed945f, o cofre do D-1 que o
    # commit do D-2 esqueceu) e a travessia do no da direcao declarada na vigia por PATH.
    "08b286bf51511ce20d285e9cae410aaef5e6b134": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "semantic/governance/freshness-approvals.yaml",
    ),
    # ciclo 545 (D-1303/T1311): o bump SCHEMA_VERSION 2->3 do 472763b renomeou
    # test_t023_unsupported_schema_version_is_refused[3] para [4] -- a parametrizacao e
    # SCHEMA_VERSION + 1 e ja era derivada. O baseline do T106 guardava o id velho.
    "2ba29241ea96f79830a521f5882ce51d823ba78d": (
        "packages/channel_integration/tests/fixtures/upstream_node_ids.json",
    ),
    # ciclo 545: a declaracao da travessia acima, e nomear um cruzamento e trabalho que cruza.
    # Termina aqui: este commit toca so o arquivo da 006, que a 005 nao vigia.
    "c8677206f2ac8b44b1350c6ad12286ea954a240f": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # ciclo 545 (D-1303, bump v3): a prosa que o D-1303 e o bump para v3 deixaram falsa.
    "62422cf034778a93ddb2064a7315a8058f5bd618": (
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/_base.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/load.py",
        "packages/semantic_catalog/src/semantic_catalog/loader/upgrade.py",
    ),
    # ciclo 545 (D-1303/T1311): a polaridade sai da view e vai para o contrato da metrica.
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
    # ciclo 542 (OD-110): tipos do pacote no diff do S-41; termina na 006.
    "5512268e61a7527a7bc2e3de8d5900c7337f0250": (
        "packages/semantic_catalog/tests/contract/test_the_fixture_step_asserts_the_refusal.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
    ),
    # ciclo 542 (OD-110): vigia da 005; termina na 006.
    "267a8817b55f2d9ad41e6131e5fa7e3b8fccfdb2": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # ciclo 542 (S-41/OD-110): vigia da 005; termina na 006.
    "ddcb2a28721b7b2429032270bd8e9859525b78a2": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 542 (S-40): vigia da 004; termina na 006.
    "9a24db9b6f473b818d3079898f6a49855877ffb8": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 542 (S-40): vigia da 005 declarando a 004; termina na 006.
    "6456ba2f1733d79b462c42b8eb1f67d32bb30e58": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 542 (S-40): os 3 passos de fixture afirmam a recusa; termina na 006.
    "9d010fae2ee6d21f9418561fcde9b74f252a3da9": (
        "packages/semantic_catalog/tests/contract/test_the_fixture_step_asserts_the_refusal.py",
    ),
    # ciclo 542 (S-40): vigia da 005; termina na 006.
    "d830fb7e15bcd3c626163a6a54e06280fa05ca0a": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 542 (OD-106): no da 005 re-derivado; termina na 006.
    "efec11bfdf36002fcb1b3c6be22c2901f8bfa924": (
        "packages/anomaly_investigation/tests/integration/test_the_approval_is_inert_where_it_is_evaluated.py",
    ),
    # ciclo 542 (S-39): re-vinculo do cofre + no da distincao.
    "0ee378017a2950d213bb005cf6e7b724030736f4": (
        "packages/semantic_catalog/tests/contract/test_definition_approvals_current.py",
        "semantic/governance/definition-approvals.yaml",
    ),
    # ciclo 542: vigia da 005; termina na 006.
    "8f6643f0e40e372335775cb52c5af75d00651939": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 542 (OD-106): d_12 declara; termina na 006.
    "ba115a980e8fa86fabd3126181768dd161245e9a": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # ciclo 539 (S-38): credencial injetada.
    "ec8c24f8f41f5e826487723d97fb5b035e11ba83": (
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/freshness/warehouse_read.py",
        "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py",
    ),
    # ciclo 539: vigia da 005; termina na 006.
    "71565e347482f6132b210e85040b610658aedfb8": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 539 (T109): condicoes 2-5 do D-12.
    "45c3b1c1d9bb2e6f5647bc16ace3b21624e1a71e": (
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/freshness/warehouse_read.py",
        "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py",
    ),
    # ciclo 539: allowlist do 004; termina na 006.
    "4a9468e252e81b3fe639a0a091d286f94e69d0a0": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 539: vigia da 005; termina na 006.
    "79b8a028121df0010874b3503fbe53c548d759b8": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 537: canal fora do sink + twenty-seven.
    "4f0ac462c89e61ba759f3be08aef16788b8111c5": (
        "packages/channel_integration/tests/contract/test_release_record_counts.py",
        "packages/semantic_catalog/src/semantic_catalog/provenance/file_archive.py",
    ),
    # ciclo 537: vigia da 005; termina na 006.
    "5d2160b20803034de346922764a885a056ec2527": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 537 (OD-103): o sink do D-13 na 001.
    "c66f0c35e337691644fde14fe08da984933fa072": (
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/provenance/file_archive.py",
        "packages/semantic_catalog/tests/contract/test_operational_audit_archive.py",
    ),
    # ciclo 537 (OD-103): d_10/ext_b declarados; quickstart consertado.
    "40390c10f597fa8a82f780343d3e52dd108ef327": (
        "packages/semantic_catalog/src/semantic_catalog/compliance/readiness.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
    ),
    # ciclo 537: onda dos NOVE nos agregados.
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
    # ciclo 537: vigia da 005; termina na 006.
    "b69cacb6e3faaf786c0bfd2d57e5637fe0a399d5": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 533: declaracao no vigia da 005; termina na 006.
    "603369c660e62026f7b303a423b9993dd48fa8d7": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 533 (OD-104): o D-18 inteiro.
    "ec6a7ca02bc5cc6de17d037532dcc50010bc2487": (
        "interpretation_governance/claim-classes.yaml",
        "interpretation_governance/period-vocabulary.yaml",
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
    # ciclo 533: declaracoes nos vigias 004/005; termina na 006.
    "798c6f16a5251f82773f8df53df3afc8bccedb79": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 527: declaracao no vigia da 005; termina na 006.
    "6ce9fd3bbfd02f2f84d39b8fbf6877a864809c2d": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # ciclo 527: declaracoes nos vigias 004/005; termina na 006.
    "04964a7f379d4b10bb5b2baaf5025e524117d04b": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 525: o commit-declaracao tocou a 005; termina na 006.
    "075c0f7b8797a7ade60383b5814fa0bbbfc7b3f4": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 525: allowlist/re-derivacao do 004 para o cofre do D-2.
    "75e62b3ece5659a0fb1692a0503e419bf4a85df4": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 525: o commit da varredura tocou a 005; termina na 006.
    "cf3c1358a49fa05e94d88bd1ed3ca0b3e33d2d69": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # ciclo 523: o commit da varredura tocou a 005; termina na 006.
    "13394869dd6684ecc76bd823198647677b3f780d": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # ciclo 517: o commit-declaracao 3f9c625 tocou o vigia da 005; termina na 006.
    "3f9c6254ddbdbe66cd6719a87e78a431ae00d92b": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 517: allowlist/re-derivacao do 004 (350140d) e a declaracao anterior (HEAD).
    "350140dc4e93faf3d5d5b765935eb772ab8627e6": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "c5b459d6dc1ee7c2d864ee6734900f950f2d3480": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 519: o commit de guards (allowlist 004 + declaracoes) tocou 004 e 005.
    "41ce503046709bfbf34fe1b4bff19dbbc346ce4c": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 521: o commit-declaracao tocou a 005; termina na 006.
    "0161d4562c32d69f174f83ddc3c70aa67a2a1dbd": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 521 (S-34): no da assinatura re-derivado pelo caminho publico.
    "ad476027c1c227510e31732a04ed5c5ad60c5f42": (
        "packages/semantic_catalog/tests/contract/test_freshness_signature_current.py",
    ),
    # ciclo 519: o commit da varredura tocou a 005; termina na 006.
    "2ecab0240776efd9c263d48c9cece99583ee024d": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 519 (varredura da janela).
    "5f781d2d1bd0cdb302ef472101b65de7973e84c9": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # ciclo 519 (2a onda de guards): tocou 004 e 005; termina na 006.
    "61d4c08b029f1cae8ab557082c7dc03a8a92323d": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # ciclo 515: a declaracao de 52e461f tocou o vigia da 005; corrente termina na 006.
    "38bfe6b0c4b858f5de8bfc10bddc37a8d06ad12b": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 513 (segunda onda): a declaracao de fa2f2c4 tocou o vigia da 005; corrente
    # termina na 006.
    "61e28362068fc233026ec48ef0124ec3ca6f7895": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 513: a declaracao de 14afd9d tocou o vigia da 005; corrente termina na 006.
    "8030eb8a6238dc2a07770775a077fa632912af5d": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 510 (OD-91): a declaracao de 9d41b65 tocou o vigia da 005; corrente termina
    # na 006 (este arquivo, que a 005 nao vigia).
    "1885711b2ce9bc39e293092d7ba4e7d3a09ba311": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 501 (OD-86, terceira onda): a declaracao de f147414 tocou o vigia da 005;
    # corrente termina na 006 (este arquivo, que a 005 nao vigia).
    "dad56ff993b0d916bfa560953e8817b7318a02f2": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 501 (OD-86, segunda onda): a declaracao de 3e5ca49/86bace4 tocou o vigia da
    # 005; corrente termina na 006 (este arquivo, que a 005 nao vigia).
    "83db0eaf699f98a56a976c6966bcc80055cd4c7f": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 501 (OD-86): a declaracao de 30f9c16/61c464d tocou o vigia da 005; corrente
    # termina na 006 (este arquivo, que a 005 nao vigia).
    "0fd981cb107edf64de1b6bd624a55c2cf9366662": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 499 (T0): a declaracao de b6ca956/3b8db05 tocou o vigia da 005; corrente
    # termina na 006 (este arquivo, que a 005 nao vigia).
    "58dab2ff9fb735e961544bd0813c3ea7c408c4d0": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 495: a declaracao de 5becd36/d4a6e8f tocou o vigia da 005; corrente termina
    # na 006 (este arquivo, que a 005 nao vigia).
    "27edc988b5c9256d417508df8edb86f6241dafd7": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # a declaracao tocou o vigia da 005; corrente termina na 006.
    "f1586adb5b614b021da9e8c481320d9bcc9d4908": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # a declaracao do move tocou o vigia da 005; a corrente termina na 006.
    "45f5f6b73eaed2339f2b78518ba0ed893cf8974b": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # OD-79: as referencias vivas (vigiados: 004) e o sweep.
    "382f10dd8616f104ba9769fba90e8d2d016e0248": (
        "packages/channel_integration/tests/contract/test_claim_classes.py",
    ),
    "be5e40a7de9dc5e05b44fe41e68853315e59bccb": (
        "packages/channel_integration/tests/contract/test_the_prose_does_not_assert_the_old_world.py",
    ),
    # a nomeacao no vigia da 005; a corrente termina AQUI, na 006, que ninguem vigia.
    "522ba5e39228af56bd0d71788893ad189bfb7184": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # a declaracao acima tocou os guardas da 004 e da 005; a corrente termina AQUI,
    # no arquivo da 006, que ninguem vigia.
    "fd464cb4d186e31613d2b2b760576d60f5f0647c": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # tipos estritos do CI local (OD-73): o espiao do OD-69 com a assinatura do protocolo,
    # e o formatador passou no guarda da 005.
    "c8d2ae1e0e5fb0fe9bd1ae066013957bd25df7db": (
        "packages/analytics_interaction/tests/integration/test_stateless_clarification.py",
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # a declaracao acima tocou o guarda da 005; a corrente termina AQUI, no arquivo
    # da 006, que ninguem vigia.
    "57f3a17d73d28ee7e9c28c4368c84e28e4890319": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # a entrada que o move deixou stale saiu do allowlist da 004 -- diff liquido zero.
    "45317aaba8c7c52302c7964955782ca40ce94b5e": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # a nomeacao acima tocou o guarda da 005; a corrente desta declaracao termina AQUI,
    # no arquivo da 006, que ninguem vigia.
    "a06fb08e273fff7a31026bf54e09cafbcc592334": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # ciclo 459, a frase-copia da allowlist do channel seguindo a lista (68, 18, 50) --
    # commit que nasceu DEPOIS da medicao daquele ciclo e ficou sem nome ate agora.
    "e080c16f3f0cb8ebe307bee963d2bccb8cfa52f7": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # o ajuste tocou o guarda da 005.
    "ecc6c2a7c148410528db51f4c312f2db86f6e8e6": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # e a corrente desta declaracao tambem termina na 006.
    "8d3e7a6df8654c903a4bc6475546d7d29188f940": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # a mudanca de chao do OD-70: o yaml sai de semantic/ (chao do catalogo, medido com 131
    # UnknownKindError) para report_governance/, arvore governada propria do relatorio.
    # a declaracao da declaracao termina aqui, no arquivo da 006.
    "7e89f97899d36ee4a2d9b027339441762dd7eef2": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # `OD-70`/`OD-71`: a ordem das secoes vira DADO GOVERNADO em semantic/report/ (dois scans
    # da 008 proibem o atalho de escrever nomes da view no pacote), e MRR/Revenue ganham as
    # duas moedas da MESMA linha da view.
    "2af36b99abfca7037207babeb9d9031b34296c44": ("semantic/report/section_order.yaml",),
    # `OD-69`: as declaracoes da emenda tocaram os guardas da 004 e da 005, e a corrente da
    # declaracao termina AQUI, no arquivo da 006, que ninguem vigia.
    "a2380e84de2f30c837c02a36734823095a666d25": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "20fe58b317a46af9554a2f1e5eef2c7992436c57": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "bc9cbe1aec27e73b61fddb899a4bf23672a9cc65": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # `OD-62`: as mensagens de skip de credencial da 005 apontam o remedio novo. O alcance aqui
    # e SO o vigiado -- os dois arquivos de anomaly_investigation; o resto do commit esta nomeado
    # em AUTHORIZED_FOREIGN_WORK, porque _unnamed_crossings consulta ESTE dicionario e a
    # proibicao de spec consulta os dois.
    "0529cef53b7f4367d3e60b85015f549567bf592d": (
        "packages/anomaly_investigation/tests/integration/test_candidate_against_the_real_warehouse.py",
        "packages/anomaly_investigation/tests/integration/test_the_recorded_coverage_still_matches_the_view.py",
    ),
    # `008` OD-48: o rotulo do KPI em negrito, e a marcacao SAI do pacote para o transporte.
    "26e6317ac603c7aa1250feda36f2a1043c3aa7b8": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # `008` OD-40: o CAC ganha declaracao de INATIVO no proprio contrato -- status
    # unavailable, com razao e data -- porque ele mandou tirar da lista. A omissao do
    # relatorio passa a ser DERIVADA dessa declaracao e nunca de um nome escrito em codigo.
    "26e79b78a53ba29e27c17d042f31128048902719": ("semantic/metrics/cac_brl.yaml",),
    # `008`: a declaracao da declaracao. Ela toca o guarda da 006, que esta feature vigia,
    # e o proximo passo toca SO o arquivo desta 005 -- que esta feature nao vigia contra si
    # mesma. E ai a recursao termina, no mesmo lugar em que terminou em todos os ciclos.
    "ee76b1af6a990f8bdbc65a85bb05afd75b7968ee": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # `008`: a declaracao da travessia da T829, e ela e ela mesma uma travessia -- nomear um
    # cruzamento e trabalho que cruza. Termina aqui: o proximo commit nao toca arquivo
    # vigiado por este guarda.
    "2cf88c2d00f03de6b8611789678faba8902b20e4": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/channel_integration/tests/fixtures/upstream_node_ids.json",
    ),
    # `008` T829: os dezenove KPIs entram no catalogo com a metade derivada escrita e a
    # metade de negocio como lacuna nomeada. Cruza a `001` porque o `FR-806` precisa do
    # campo `value_column` no modelo e o `FR-808` move `catalog_schema_version` com ele.
    # Assinatura ampla do proprietario, 2026-08-30, transcrita no `OD-26`.
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
    # `008` S-5: a prosa que seguia afirmando o mundo anterior ao `OD-18`, em tres modulos
    # vivos, e o guarda que a le. NAO ESTAVA DECLARADO AQUI ATE 2026-08-30, e o motivo e
    # meu: nos ciclos 395 a 399 eu rodei as suites VIZINHAS e nao TODAS, entao a 005 nunca
    # foi consultada. O guarda estava certo o tempo todo; ninguem o perguntou.
    "bbd42c4a635175f441c0e5c961ff1898937e30c2": (
        "packages/channel_integration/src/channel_integration/cli/main.py",
        "packages/channel_integration/tests/adversarial/test_fixture_substitution.py",
        "packages/channel_integration/tests/contract/test_the_prose_does_not_assert_the_old_world.py",
    ),
    # `008` OD-22-A: a cobertura declarada deixa de ser data medida contra uma janela que
    # desliza, e passa a ser dita contra a borda de retencao observada.
    "0493f89a8123f81b4b974cb7f3aa554d08abb820": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/anomaly_investigation/tests/integration/test_the_recorded_coverage_still_matches_the_view.py",
    ),
    # `008` S-6: o no re-derivado respondia vinte vezes sem comparar uma data e nao dizia.
    "299127c684cd1ee041629bcfe0c769ea4e19eb79": (
        "packages/anomaly_investigation/tests/integration/test_the_recorded_coverage_still_matches_the_view.py",
    ),
    # The declaration of the crossing above, itself a crossing into 005.
    "1731b4b3d08c946fe21e271b90b062d7af2544d9": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # `008`: S-4, the record created and never enumerated
    "1279b55846790e8c14e9e54748ed869e44e9310c": (
        "packages/channel_integration/src/channel_integration/cli/main.py",
        "packages/channel_integration/src/channel_integration/compliance/readiness.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/channel_integration/tests/contract/test_the_split_key_is_asked_by_its_callers.py",
        "packages/channel_integration/tests/integration/test_readiness_locks.py",
    ),
    # The declaration of the crossing above, itself a crossing into 005.
    "a100b955d5ab99af81cb54b189bab6c5498ba3e2": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # The declaration of the crossing above, itself a crossing into 005.
    "1e4ebfc575741f445c45210daaeef7eccaa5fcf9": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # `008`: four more nodes asserting the old world, harness guard included
    "266b37144ebb48c92c4adbc6c784e7dc24f15240": (
        "packages/channel_integration/tests/contract/test_fifth_channel.py",
    ),
    # The declaration of the crossing above, which is itself a crossing into 005.
    "da3fbe65e496d2ec02b1dcde622a6e9261beef22": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    # The declaration of the crossing above, which is ITSELF a crossing: it writes 005's
    # allowlist. The cascade is the mechanism working -- naming a commit is an edit, and an
    # edit to an upstream package is what this list exists to record.
    "a742b31e96a363e292a35224f10c702cb9b22e14": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # `008` Phase E: the replay gate's count proxy re-derived; d_24 declaration withdrawn
    "f6bd047124f188e7ee66759852b32bc1d49b65ca": (
        "packages/channel_integration/tests/contract/test_replay_defence_bound.py",
    ),
    "0310d704e01e4c8a847b2f887116e27e3d5bd434": (  # 005's own crossing list, named there
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    "73088752285d82ac965d9c800dca631d3b27476f": (  # ADR 0034 recorded in 004's allowlist
        # The gate said what to do rather than only that something was wrong, and this is the
        # doing: the ADR names the change, so the allowlist records it with the ADR cited.
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "0c619d0780cae6894e99f5ee3486156d9c4b73a6": (  # ADR 0034: two guard repairs
        "packages/analytics_query/tests/contract/test_adr0010_baseline.py",
        "packages/analytics_query/tests/contract/test_adr0010_scope.py",
    ),
    "3f0d953f64b6c9b95f989edb1975e0d52d573bf3": (  # the crossing list of 005
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    "33d99f85a69dd6cdd35e761a4942f941b901507e": (  # the 77 strict errors, ordered by cycle 371
        # Repository-wide type repair, and one of the errors was a LIVE DEFECT: `figures_port`
        # read an attribute that does not exist, so every governed refusal it carried raised
        # `AttributeError`. The crossing is that repair reaching where the untyped reads live.
        "packages/analytics_interaction/tests/contract/test_fixture_containment.py",
        "packages/anomaly_investigation/src/anomaly_investigation/ports/figures_port.py",
        "packages/anomaly_investigation/tests/integration/test_an_upstream_refusal_reaches_the_caller.py",
        "packages/anomaly_investigation/tests/integration/test_candidate_against_the_real_warehouse.py",
        "packages/anomaly_investigation/tests/integration/test_the_recorded_coverage_still_matches_the_view.py",
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/tests/integration/test_authored_catalog_is_fail_closed.py",
    ),
    "0b56e3c79641e3164791e15014dd0d844e39a44c": (  # `005`'s own crossing list, named there
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    "71f2bb2f1c8ee7aa24858aca252607b3f1d0bd4b": (  # the guard that could not fail
        # It read its own file and searched for a literal its own assertion writes, so
        # emptying the prose left it green. It reads `__doc__` now.
        "packages/anomaly_investigation/tests/integration/test_an_upstream_refusal_reaches_the_caller.py",
    ),
    "2d050251761f5f9040bcb0c2c264eb4e47130924": (  # the node that said "every refusal path"
        # It drove two of the seven sites and claimed all of them. Two are driven now and the
        # three unreachable ones name `pyright` as their guard instead of being claimed.
        "packages/anomaly_investigation/tests/integration/test_an_upstream_refusal_reaches_the_caller.py",
    ),
    "1f8a0a44bd731aa2b21cfe9ac470fea178a4eaa0": (  # OD-124 (c): the vault, read at bundle build
        "packages/semantic_catalog/src/semantic_catalog/loader/lifecycle.py",
        "packages/semantic_catalog/tests/unit/test_a_signed_definition_that_changed_is_refused.py",
    ),
    "bf083b9b59d94dddbbbbcdd65524f357e2242fec": (  # `005`'s crossing list naming the vault consumer
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    "77446ab1c44dc3bca2cdff4484f5b8ec15948816": (  # `004`'s allowlist naming the (c) test
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "7eb9ef362e0be769eb957ad85d80a59f4c89a68c": (  # `005`'s crossing list naming that entry
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    "344496521656598582b1f2b9bfc32d41b59195b3": (  # `004`'s docstring count, 108 to 109
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    "97149a55bdb340bb86d05b5e1a986cfc889cd14d": (  # `005`'s crossing list naming that count
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    "4cf4e63b43cf96832476ddbe0c78ff5d52d72d4e": (  # OD-124 (a): the id covers the authored catalog
        "packages/semantic_catalog/src/semantic_catalog/loader/bundle.py",
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
    ),
    "d1606c40872043dc8896b5940876e8014972574d": (  # `005`'s list naming the release-id work
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    "bc33a8488120afe0aa248cbcf444d4d03a591461": (  # S-55: the instrument's docstring says 36 of 71
        "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py",
    ),
    "885a3d9848f70003b3416fe5e8993776414d9ada": (  # `005`'s list naming the S-55 docstring
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    "3dbadc425374e4611d600ea719756b53f69733a4": (  # `005`'s list naming the gateway axis
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    "5bb99a0a91be1ec05fc8ced570bf76263c845c12": (  # `005`'s list naming the plan axis
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
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
    "78e88754336ad4c23d31c91f6e10ffe8e9a09c53": (  # 005 declara os tres de cima
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
}


#: **Foreign work this feature's window can see, named with its reach.**
#:
#: `AUTHORIZED_CROSSINGS` above is about WATCHED CONTENT -- upstream packages and governed
#: trees -- and its three nodes compare each declaration against `_crossings_of`, which
#: narrows to those prefixes. `specs/` is deliberately not among them, so a foreign commit
#: touching another feature's documents cannot be recorded there: the declaration would name
#: paths the crossing check cannot see, and two of those nodes said so by failing.
#:
#: **That was a design error made when the list was introduced** -- ONE exemption mechanism
#: wired to TWO prohibitions with different subjects. This list is the second subject's own.
#:
#: It exists because the prohibition window is UNFILTERED by design: `007` is cut from this
#: line, so a `007` commit sits inside `BASE..HEAD` and the spec prohibition sees it.
#: Filtering the window by "is it ours" would be the `F-1` defect the unfiltered window was
#: restored to fix; naming the foreign commit WITH ITS REACH is the honest alternative.
AUTHORIZED_FOREIGN_WORK: dict[str, tuple[str, ...]] = {
    # ciclo 571: a T1332 fecha por OBSERVACAO de producao, nao por teste. O timer semanal
    # disparou pela primeira vez as 09:00:06 -03 e o jornal foi de 3 para 6 linhas -- tres novas
    # com closed_day 2026-09-06, uma por destinatario, todas refused, zero sent. A marcacao leva
    # os quatro numeros porque sem eles seria palavra. Toca a spec da 013 e mais nada: um
    # ficheiro, e o que o traz aqui e so a proibicao de spec.
    "43bc6be866f181c07c8958cfb796bfd06ff81605": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 570, OD-139: as tres citacoes a E8 na spec da 007 passam a dizer a razao
    # substantiva. E8 nao existia -- medido com git grep sobre os 1441 ficheiros
    # versionados, sem filtro de extensao: as unicas tres ocorrencias eram as proprias
    # citacoes, e nao ha serie E nenhuma. Nao toca pacote vigiado: o que traz o commit
    # aqui e SO a proibicao de spec, e o commit inteiro e um arquivo.
    "39f1e799a30464a1e19a9604e99993acd84cdbb5": ("specs/007-proactive-distribution/tasks.md",),
    # ciclo 567: o registo de tarefas ve as 789 linhas, nao 739. Toca pacote vigiado E a
    # spec da 013, entao vem para aqui: a proibicao de spec consulta os dois dicionarios,
    # e o no do alcance desta lista exige o commit INTEIRO e nao so o arquivo vigiado.
    "901c0358e1781b7caf7e941dda3fd0dcaaca6ee5": (
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 565: a T1336 (SC-1308, silencio auditavel) fecha. apps/ nao e prefixo
    # vigiado; o que traz o commit a esta lista e SO a proibicao de spec -- mas o no do
    # alcance exige o commit INTEIRO, entao vao os seis.
    "97f5db1b69daeb8183129f6dabcc40aa8b0b91a3": (
        "apps/telegram-bot/deliver_daily_report.py",
        "apps/telegram-bot/distribute_findings.py",
        "apps/telegram-bot/tests/test_a_quiet_day_records_what_it_withheld.py",
        "apps/telegram-bot/tests/test_t714_distribution.py",
        "apps/telegram-bot/withheld.py",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 565: onze correcoes medidas na tasks.md (T1320 pendurado, byte 0x08,
    # cinco "37", citacao a arquivo que nao existe em rev-list --all). Um arquivo so.
    "63ce519433a5a9df398e2606dcfd2ff803d34524": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 565: `T828` em prosa era referencia pendurada criada por MIM dentro do
    # commit que corrigia as alheias -- qualificada para `008:T828`. Traz tambem o mapa
    # OD-79 e a guarda do .venv para as tres perguntas de plano.
    "14931a3629f8d31e4f7585e756d05061931bf1af": (
        ".github/upstream-node-renames.txt",
        "specs/013-dimensional-analysis/tasks.md",
        "tools/git-hooks/pre-push",
    ),
    # ciclo 565: a T1336 (SC-1308, silencio auditavel) fecha. Commit de apps/ + a caixa na
    # spec da 013 -- apps/ nao e prefixo vigiado, entao o que traz o commit aqui e SO a
    # ciclo 565: onze correcoes medidas na tasks.md (T1320 pendurado, byte 0x08, cinco "37",
    # ciclo 565: `T828` em prosa era referencia pendurada criada por MIM dentro do commit que
    # corrigia as alheias -- qualificada para `008:T828`. Mesmo commit traz o mapa OD-79 e a
    # `013` T1324/T1325/T1329: as tres caixas fecham pelo run REAL das 08:00 de 06/09,
    # lido na VM por mim -- `bytes: 3784` prova o envio unico, `escopo do diario: 3 de 19`
    # prova o corte, e `- por plano` / `- por gateway` duas vezes cada provam as recusas.
    # Commit de UM arquivo so, e e uma spec de outra feature: por isso vem aqui em vez de
    # AUTHORIZED_CROSSINGS -- a proibicao de spec consulta os dois dicionarios.
    "138ef9bead7cc37bdd95f4d644c22b37d1794d00": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 552 (OD-127, 013 F5): as caixas da T1313 e da T1317 fecham com os carimbos do run
    # REAL das 08:00 de 05/09 (tres relatorios, tres alertas, sha 3c05428 na VM). So tasks da 013.
    # Entrou primeiro em AUTHORIZED_CROSSINGS, que nao ve specs/ -- o no da reach acusou e a
    # entrada mudou de lista, como o cabecalho acima manda.
    "1a64a23a034c2070fa8d14b89d9ef3f9fadc8228": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 552 (OD-127, 013 F5): a T1323 registra a metade da recusa feita (shas, linha do --dry,
    # mutacoes) e a metade da quebra bloqueada na T1326; a T1324 registra o que aguarda. So tasks
    # da 013.
    "555f36e87568178fbf3df2e39d2e32e525ccaac6": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 553 (OD-128): T1325, a metade da recusa de gateway entregue (72c7aa1, adf7e7a); caixa
    # aberta ate o run de 06/09. So tasks da 013.
    "024d11eff8e81b5b3e4e8af6b48bbdf3c0897f93": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 555 (OD-131): a descricao do diario virou 'Ontem contra anteontem' e empurrou
    # AUTHORED_WORDS sete linhas; spec.md :39 e plan.md :48 citavam o intervalo antigo. So 013.
    "ed3e8a9deb100ab2d5233ad4f7b06b38ce735e34": (
        "specs/013-dimensional-analysis/plan.md",
        "specs/013-dimensional-analysis/spec.md",
    ),
    # ciclo 554 (OD-129/OD-130): T1329, metade do diario da F7 entregue (92350b5) -- o 08:00 so com
    # os tres indicadores, por dado governado. So tasks da 013.
    "e5fb7b211a126ff7c4a1a0ad9e1a19092edf978c": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 558 (T1332): a unit passa a dizer por que o systemd vai pinta-la de vermelho --
    # achado num ensaio manual na VM; a recusa sai com codigo 1 por desenho.
    "bd94a22c3f6b330355f9664d5e7e08452e4e5275": (
        "apps/telegram-bot/tests/test_the_monday_caller_refuses_until_the_record_names_it.py",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-weekly.service",
    ),
    # ciclo 557 (OD-133): a T1332 fica ABERTA na tasks -- metade entregue, faltando a VM e a
    # recusa gravada na segunda. So tasks da 013.
    "be5ee36aa49c50c23356dd4e41f59e17bd3438ad": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 557 (OD-133): T1332 -- a SEGUNDA as 09:00 passa a existir e o chamador RECUSA,
    # citando o ADR 0036 por ORIGINATION_NOT_NAMED_BY_THE_ADR; nada e enviado. O par
    # timer/service mora no vm/ da 012 porque e la que as outras cinco units moram.
    "06fb1447deb9016ddd9e5a08658ba927e86a01ac": (
        "apps/telegram-bot/run_weekly.py",
        "apps/telegram-bot/tests/test_the_monday_caller_refuses_until_the_record_names_it.py",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-weekly.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-weekly.timer",
    ),
    # ciclo 555 (OD-129/OD-131): T1330 fechada -- o SNAPSHOT e o ultimo dia (1756d11) e a
    # mensagem marca o nivel com frase governada (4a32be8). So tasks da 013.
    "a77ff54e39c4afe34b5321c9edef344f54fbf82c": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 550 (OD-125): igualar o p90 DISPARA -- a spec 008 ganha a frase ao lado de "only on a
    # crossing", porque nenhuma linha dela colocava o caso exato, e o no do alerta no
    # daily_reporting passa a AFIRMAR a igualdade. Spec da 008 mais um teste de pacote nao vigiado.
    "a9daba2356910133a94de1fe4d42a161ebeb1011": (
        "packages/daily_reporting/tests/unit/test_every_boundary_is_decided_by_the_written_rule.py",
        "specs/008-daily-report-and-rule-alerts/spec.md",
    ),
    # ciclo 548: a caixa da T1320b fecha com os shas que a sustentam e com a DIVERGENCIA DE
    # FORMA escrita dentro dela, que e o que o OD-122 exige -- caixa fechada sobre divergencia
    # que o dono nao ve e caixa que mente. So tasks da 013.
    "ba32578a05d9bb80531341997588c4202eabfe1b": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 546 (T1319/T1320a): a caixa da T1319 fecha com o sha que a sustenta, a T1320 parte
    # nas duas metades que ela tem -- o pre-requisito entrou, o compositor nao -- e o buraco do
    # TOTAL SILENCIOSO ganha nota com o no que o segura, porque nao existe FR nem SC que o nomeie.
    # O plan.md perde a frase do tipo de `game`, derrubada por medicao na abertura da F4.
    "55fd603f9a67d9aa9d23fcccbb05f35683cbc295": (
        "specs/013-dimensional-analysis/plan.md",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 546 (T1318): a F4 abre e a PRIMEIRA tarefa fecha sem escrever codigo -- o campo
    # `dimensions` ja estava em AnalyticsQuery desde antes da 013, e `order_by`/`limit` nunca
    # foram recusados por condicao escrita: quem recusa e `extra="forbid"`. A tarefa citava
    # `request.py:167-171` como se fosse codigo, e aquilo e docstring. So tasks da 013, mais o
    # `.gitignore` da raiz, que este guarda nao vigia.
    "ffd4e94a758da2ffc8eaa15e17a08066cb59f181": (
        ".gitignore",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 545: a entrega da F2+F3 na VM e o placar da 013 deixando de mentir (onze caixas com
    # commit e a frase "None is decided here" sobre quatro decisoes ja tomadas). So specs da 013.
    "1372e75d54b2f6f6213108229b3115830c3ae4b9": (
        "specs/013-dimensional-analysis/spec.md",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 545 (T1316/FR-1308-1310): o bloco APARECE no diario e no alerta -- trabalho da 013,
    # tasks.md da 013.
    "dc6cc7714bdf6f603056d9a2319ba6096ec4c177": (
        "apps/telegram-bot/deliver_daily_report.py",
        "apps/telegram-bot/tests/test_the_alert_is_judged_with_the_reports_vocabulary.py",
        "packages/daily_reporting/src/daily_reporting/report/contribution.py",
        "packages/daily_reporting/tests/unit/test_the_block_appears_and_a_quiet_day_says_so.py",
        "packages/daily_reporting/tests/unit/test_the_block_is_governed_and_the_refusal_holds.py",
        "packages/daily_reporting/tests/unit/test_who_pulled_it_reconciles_or_refuses.py",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 545 (T1315/FR-1309): a reconciliacao e RECUSA -- trabalho da 013, tasks.md da 013.
    "4f3c12b607ba3c9cbdb869d944c585d6ade502df": (
        "packages/daily_reporting/src/daily_reporting/report/contribution.py",
        "packages/daily_reporting/tests/unit/test_the_block_is_governed_and_the_refusal_holds.py",
        "report_governance/contribution.yaml",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 545 (T1314/FR-1308-1310): motor de contribuicao -- trabalho da 013, tasks.md da 013.
    "0af85e82af1dfa5bc53e9d57250d3c60c48d0eac": (
        "packages/daily_reporting/src/daily_reporting/report/contribution.py",
        "packages/daily_reporting/tests/security/test_no_composed_prose_and_nothing_originates.py",
        "packages/daily_reporting/tests/unit/test_who_pulled_it_reconciles_or_refuses.py",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 545 (013-medicao): o bloco cabe (2.494 de 4096) -- so o tasks.md da 013.
    "2c19cbd0e59d271c0f15d2d92161bb54a0c284a7": ("specs/013-dimensional-analysis/tasks.md",),
    # ciclo 545 (013/006-guard): travessias declaradas; toca este arquivo e o tasks.md da 013.
    "b3c49a109bbeeee5b2f141812f983b7ae48b398f": (
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 545 (T1322): a medicao que corrige a spec da 013 -- plano/gateway fora da fonte.
    "8eb642d56185917c345a69915d3c1a135f9b3cdd": (
        "specs/013-dimensional-analysis/spec.md",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 543 (S-43): o token pendurado do papel da 013, mesma razao da entrada acima.
    "6eb5e8d3a01ca6e1fabe259e04fd90129bb0c46d": (
        "specs/013-dimensional-analysis/spec.md",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 543 (OD-109): o PAPEL da 013 nasce numa branch da 013 -- spec, plan e tasks.
    # NAO e travessia: specs/ nao esta em WATCHED_PREFIXES, entao _crossings_of devolve
    # vazio e a lista de travessias recusaria a declaracao. E a proibicao de spec le OS
    # DOIS dicionarios, que e o que faz esta ser a lista certa.
    "fc6765d6b8194c89476b8b76171a22af000c9d39": (
        "specs/013-dimensional-analysis/plan.md",
        "specs/013-dimensional-analysis/spec.md",
        "specs/013-dimensional-analysis/tasks.md",
    ),
    # ciclo 542 (OD-106): d_12 declara; termina na 006.
    # Alcance inteiro (exigencia do no de exatidao).
    "b43857806e92c64b904b5b63365278da2bbb3bd3": (
        "docs/readiness/external-readiness.yaml",
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
        "specs/001-semantic-catalog/quickstart.md",
        "specs/001-semantic-catalog/tasks.md",
    ),
    # ciclo 542 (OD-106): d_12 declara; termina na 006.
    # Alcance inteiro (exigencia do no de exatidao).
    "e21d65b5bae35360506ebf72a040c3f866bdac46": (
        "packages/semantic_catalog/src/semantic_catalog/contracts/classification.py",
        "packages/semantic_catalog/src/semantic_catalog/contracts/metric.py",
        "packages/semantic_catalog/src/semantic_catalog/validation/l3_reconciliation.py",
        "packages/semantic_catalog/tests/fixtures/coverage/observed.yaml",
        "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py",
        "packages/semantic_catalog/tests/unit/test_l3_l4_validation.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
        "schemas/metric.schema.json",
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
        "specs/001-semantic-catalog/contracts/catalog-file-contracts.md",
    ),
    # ciclo 539 (T109): condicoes 2-5 do D-12. Alcance inteiro (exigencia do no de exatidao).
    "45c3b1c1d9bb2e6f5647bc16ace3b21624e1a71e": (
        ".github/workflows/catalog.yml",
        "packages/semantic_catalog/src/semantic_catalog/cli/main.py",
        "packages/semantic_catalog/src/semantic_catalog/freshness/warehouse_read.py",
        "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py",
        "specs/001-semantic-catalog/tasks.md",
    ),
    # ciclo 537 (OD-103): d_10/ext_b declarados; quickstart consertado.
    # Alcance inteiro (exigencia do no de exatidao); termina na 006.
    "40390c10f597fa8a82f780343d3e52dd108ef327": (
        "docs/readiness/external-readiness.yaml",
        "packages/semantic_catalog/src/semantic_catalog/compliance/readiness.py",
        "packages/semantic_catalog/tests/unit/test_readiness_guard.py",
        "specs/001-semantic-catalog/quickstart.md",
        "specs/001-semantic-catalog/tasks.md",
        "specs/002-analytics-query/tasks.md",
    ),
    # ciclo 535 (OD-105): a chave certa na conferencia 3 da 007.
    # Alcance inteiro (exigencia do no de exatidao); termina na 006.
    "8c83171693ecf06b328acfeea3ed40ccfc21fdec": (
        "docs/adr/0035-proactive-distribution-supersedes-fr-062-for-item-8-only.md",
        "packages/proactive_distribution/src/proactive_distribution/distribute/__init__.py",
        "packages/proactive_distribution/src/proactive_distribution/distribute/conditions.py",
        "packages/proactive_distribution/src/proactive_distribution/distribute/recipient.py",
        "packages/proactive_distribution/tests/unit/test_the_recipient_is_derived.py",
        "packages/proactive_distribution/tests/unit/test_the_three_conditions_are_each_load_bearing.py",
        "specs/007-proactive-distribution/spec.md",
    ),
    # ciclo 535 (OD-105): T714 fecha; o envio atras das 3 conferencias.
    # Alcance inteiro (exigencia do no de exatidao); termina na 006.
    "55857c5bbf5415c230df3397336ced642e3c4a2b": (
        "apps/telegram-bot/deliver_daily_report.py",
        "apps/telegram-bot/distribute_findings.py",
        "apps/telegram-bot/tests/test_t714_distribution.py",
        "docs/adr/0036-daily-report-and-rule-alerts-supersede-fr-062-for-two-named-products.md",
        "docs/roadmap-capacidade-de-negocio.md",
        "specs/007-proactive-distribution/tasks.md",
        "specs/008-daily-report-and-rule-alerts/spec.md",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # ciclo 533 (OD-104): o D-18 inteiro. Alcance inteiro (exigencia do no de exatidao).
    "ec6a7ca02bc5cc6de17d037532dcc50010bc2487": (
        "apps/telegram-bot/tests/test_no_governance_change.py",
        "docs/readiness/nl-analytics-external-readiness.yaml",
        "docs/release/nl-analytics-release-state.md",
        "interpretation_governance/claim-classes.yaml",
        "interpretation_governance/period-vocabulary.yaml",
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
        "specs/003-nl-analytics-interaction/tasks.md",
    ),
    # ciclo 533 (S-37): units entregam a chave ao usuario do bot.
    # Alcance inteiro (exigencia do no de exatidao); termina na 006.
    "e362b31167e14ed77ccc05bad497234b0fa0a524": (
        "apps/telegram-bot/tests/test_s37_rotation_units_hand_the_key_to_the_bot_user.py",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-key-rotation.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-seal-rotation.service",
    ),
    # ciclo 527 (OD-101): o selo do D-21 — interact.py aprende seal ausente.
    # Alcance inteiro (exigencia do no de exatidao); termina na 006.
    "664f91a72c82df11eee0cfa9195b469a4dc01961": (
        "apps/telegram-bot/.env.example",
        "apps/telegram-bot/compose.py",
        "apps/telegram-bot/config.py",
        "apps/telegram-bot/rotate_seal_key.py",
        "apps/telegram-bot/run.py",
        "apps/telegram-bot/seal_adapter.py",
        "apps/telegram-bot/tests/test_d21_key_scope.py",
        "apps/telegram-bot/tests/test_d21_seal_adapter.py",
        "apps/telegram-bot/tests/test_seal_key_rotation.py",
        "docs/readiness/evidence/clarification-seal-custody.yaml",
        "packages/analytics_interaction/src/analytics_interaction/interact.py",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-seal-rotation.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-seal-rotation.timer",
    ),
    # ciclo 527 (OD-101): d_21 declarado + T185; onda de 46 emendas datadas.
    # Alcance inteiro (exigencia do no de exatidao); termina na 006.
    "2ea1234f85c4a3938ba46bdf763077f787dc32c6": (
        "docs/readiness/nl-analytics-external-readiness.yaml",
        "docs/release/nl-analytics-release-state.md",
        "docs/release/nl-analytics-spec-revision-notes.md",
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
        "specs/003-nl-analytics-interaction/tasks.md",
    ),
    # ciclo 525: T116 fechado; alcance inteiro.
    "f8713808603215d11c4c19231240e3bcccb5f28c": (
        "docs/readiness/external-readiness.yaml",
        "docs/release/multichannel-internal-validation.md",
        "docs/release/multichannel-release-state.md",
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
        "specs/001-semantic-catalog/tasks.md",
    ),
    # ciclo 523 (OD-100): T116 re-escopado, T829 desmarcado, DEP-5; alcance inteiro.
    "768f471979bde1212a9fef5469cd10b2f95fb8a7": (
        "apps/telegram-bot/run.py",
        "apps/telegram-bot/tests/test_boot_calls_the_deployment_guard.py",
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
        "specs/001-semantic-catalog/tasks.md",
        "specs/002-analytics-query/spec.md",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # ciclo 519 (OD-99): alcance inteiro (specs/001 + registros + release docs + testes).
    "ec30718f65ed89ecfc50501a5f8be188d6ac303a": (
        "docs/readiness/external-readiness.yaml",
        "docs/release/multichannel-internal-validation.md",
        "docs/release/multichannel-release-state.md",
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
        "specs/001-semantic-catalog/tasks.md",
    ),
    # ciclo 517 (OD-98): T126 fechado como decisao documentada; d_17 segue false.
    "a32782003dbe38e28dd427af9832d452b188d286": (
        "docs/readiness/analytics-query-external-readiness.yaml",
        "specs/002-analytics-query/tasks.md",
    ),
    # ciclo 515 (OD-97): alcance inteiro (registro + specs/002 + testes + vigias).
    "52e461f829948a0b1b3905732cca8d7229206c52": (
        "apps/telegram-bot/tests/test_d16_zero_threshold.py",
        "docs/readiness/analytics-query-external-readiness.yaml",
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
        "specs/002-analytics-query/tasks.md",
    ),
    # ciclo 513 (segunda onda): alcance inteiro (specs/002 + teste da 001 + este vigia).
    "fa2f2c46923c1f34731dad9c7e49f6234cdc0572": (
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
        "specs/002-analytics-query/tasks.md",
    ),
    # ciclo 513: T158 recupera o marcador (record fechado e grafo-externo) e a linha-
    # claim do registro re-declara 157 of 166; alcance inteiro.
    "591539cb6c1e6883f47849affc11ceae650bca3a": (
        "docs/release/multichannel-internal-validation.md",
        "specs/004-multichannel-integration/tasks.md",
    ),
    # ciclo 513 (OD-93/94): specs alheias (002/004 tasks.md) fechadas por instrucao;
    # alcance INTEIRO do commit (o no de exatidao exige).
    "14afd9de74d028c39f126c3c99134bd9be28d958": (
        "apps/telegram-bot/bigquery_backend.py",
        "apps/telegram-bot/tests/test_d14_governed_limits.py",
        "docs/readiness/analytics-query-external-readiness.yaml",
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
        "specs/002-analytics-query/tasks.md",
        "specs/004-multichannel-integration/tasks.md",
    ),
    # ciclo 504 (2026-09-02): o exit 1 das 07:40 — as tres units da 012 ganham o
    # Environment= da credencial (igual ao hotfix instalado) + no T504 + desenho do d_34.
    "ff74ae9d61d726cf91c25f3cecaa16e67712cb5a": (
        "apps/telegram-bot/tests/test_012_phase_g_alert_and_status.py",
        "docs/readiness/evidence/channel-token-custody-design.md",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-compare-window.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-supervise.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-verify-daily.service",
    ),
    # ciclo 499 (d_15, artefato b): units de rotacao da chave do armazem VERSIONADAS na
    # casa da 012 (mesma casa dos timers de supervisao) -- spec alheia tocada de proposito.
    "644a9374ea1064318d174e3d4930e30af819b054": (
        "apps/telegram-bot/rotate_warehouse_key.py",
        "apps/telegram-bot/tests/test_key_rotation.py",
        "apps/telegram-bot/tests/test_warehouse_identity_scope.py",
        "docs/readiness/multichannel-external-readiness.yaml",
        "docs/readiness/warehouse-credential-custody-design.md",
        "docs/readiness/warehouse-identity-scope.yaml",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-key-rotation.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-key-rotation.timer",
    ),
    "f1586adb5b614b021da9e8c481320d9bcc9d4908": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
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
    # S-31: README verdade-de-hoje, snapshot recongelado, contra-barras, olho do sweep.
    "bc6a45f08efa89d36b8b19c30bc0ae10ea5c2117": (
        "PROJECT-HANDOFF-COMPLETE.yml",
        "apps/telegram-bot/README.md",
        "apps/telegram-bot/tests/test_no_governance_change.py",
        "docs/registro-do-agendamento-diario.md",
        "specs/009-daily-run-caller-and-trigger/plan.md",
    ),
    # E501 no comentario da excecao.
    "8bd3c43c5d5a313ff8e7cd3d942437fbc6f7ef84": (
        "apps/telegram-bot/tests/test_no_governance_change.py",
    ),
    "45f5f6b73eaed2339f2b78518ba0ed893cf8974b": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # formatacao do proprio guarda apos as declaracoes do move.
    "e5c153c47107d630d0904e9a2f02fba73347bbf8": (
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # OD-79: os quatorze modulos perdem o prefixo (help vira help_desk, decisao escrita).
    "9a65dedf85bc98909056202a61d0717fd33029ea": (
        ".github/workflows/harness.yml",
        "apps/telegram-bot/anomaly.py",
        "apps/telegram-bot/audit.py",
        "apps/telegram-bot/bigquery_backend.py",
        "apps/telegram-bot/catalog.py",
        "apps/telegram-bot/channel.py",
        "apps/telegram-bot/claims.py",
        "apps/telegram-bot/clarify.py",
        "apps/telegram-bot/compose.py",
        "apps/telegram-bot/content.py",
        "apps/telegram-bot/deliver_daily_report.py",
        "apps/telegram-bot/delivery.py",
        "apps/telegram-bot/execution.py",
        "apps/telegram-bot/help_desk.py",
        "apps/telegram-bot/metrics.py",
        "apps/telegram-bot/model.py",
        "apps/telegram-bot/period.py",
        "apps/telegram-bot/run.py",
        "apps/telegram-bot/telegram_client.py",
        "apps/telegram-bot/temporal.py",
        "apps/telegram-bot/tests/test_012_phase_g_alert_and_status.py",
        "apps/telegram-bot/tests/test_bigquery_backend.py",
        "apps/telegram-bot/tests/test_clarification.py",
        "apps/telegram-bot/tests/test_comparison.py",
        "apps/telegram-bot/tests/test_configuration.py",
        "apps/telegram-bot/tests/test_execution_backend.py",
        "apps/telegram-bot/tests/test_free_periods.py",
        "apps/telegram-bot/tests/test_help.py",
        "apps/telegram-bot/tests/test_metrics.py",
        "apps/telegram-bot/tests/test_model.py",
        "apps/telegram-bot/tests/test_no_governance_change.py",
        "apps/telegram-bot/tests/test_od74_his_words_reach_the_vocabulary.py",
        "apps/telegram-bot/tests/test_od76_the_bot_asks_back.py",
        "apps/telegram-bot/tests/test_operational_message.py",
        "apps/telegram-bot/tests/test_roundtrip.py",
        "apps/telegram-bot/tests/test_shutdown.py",
        "apps/telegram-bot/tests/test_the_delivered_figure_keeps_his_ceiling.py",
        "apps/telegram-bot/tests/test_the_demo_reaches_the_last_two_features.py",
        "apps/telegram-bot/tests/test_transport.py",
        "apps/telegram-bot/trail.py",
    ),
    # as units versionadas ganham o caminho REAL da VM (o 203/EXEC fechado na fonte).
    "98bbbdba4ee949e41633a18a8a6b311d62b24914": (
        "apps/telegram-bot/tests/test_012_phase_g_alert_and_status.py",
        "specs/012-orchestration-and-continuous-improvement/vm/README.md",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-compare-window.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-supervise.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-verify-daily.service",
    ),
    # OD-82: o /status fala o formato v2 dele, escolhido por clique apos o teste ao vivo.
    "d4034cd6ea4f3cf4d0fdbe7bc3e61720ad106648": (
        "apps/telegram-bot/owner_alerts.py",
        "apps/telegram-bot/tests/test_012_phase_g_alert_and_status.py",
    ),
    # OD-79: o move (lista cheia sem rename-detection), as referencias, o settings
    # fora do indice, o sweep -- e os tres commits de DOCS do REVIEWER que a arvore
    # compartilhada trouxe para esta branch (dele, deixados como estao por instrucao).
    "d7ac67168782f5b4e287c2eff208dd722a562608": (
        "apps/telegram-bot/.env.example",
        "apps/telegram-bot/MVP-SUMMARY-KPI-MAPPING.md",
        "apps/telegram-bot/README.md",
        "apps/telegram-bot/anthropic_client.py",
        "apps/telegram-bot/bigquery_backend.py",
        "apps/telegram-bot/clarify.py",
        "apps/telegram-bot/compare_window.py",
        "apps/telegram-bot/compose.py",
        "apps/telegram-bot/config.py",
        "apps/telegram-bot/deliver_daily_report.py",
        "apps/telegram-bot/demo_anomaly.py",
        "apps/telegram-bot/demo_audit.py",
        "apps/telegram-bot/demo_catalog.py",
        "apps/telegram-bot/demo_channel.py",
        "apps/telegram-bot/demo_claims.py",
        "apps/telegram-bot/demo_content.py",
        "apps/telegram-bot/demo_delivery.py",
        "apps/telegram-bot/demo_execution.py",
        "apps/telegram-bot/demo_help.py",
        "apps/telegram-bot/demo_metrics.py",
        "apps/telegram-bot/demo_model.py",
        "apps/telegram-bot/demo_period.py",
        "apps/telegram-bot/demo_temporal.py",
        "apps/telegram-bot/demo_trail.py",
        "apps/telegram-bot/execution_backend.py",
        "apps/telegram-bot/operational.py",
        "apps/telegram-bot/orchestration.py",
        "apps/telegram-bot/owner_alerts.py",
        "apps/telegram-bot/polling.py",
        "apps/telegram-bot/pyproject.toml",
        "apps/telegram-bot/redaction.py",
        "apps/telegram-bot/run.py",
        "apps/telegram-bot/run_daily.py",
        "apps/telegram-bot/supervise.py",
        "apps/telegram-bot/telegram_client.py",
        "apps/telegram-bot/tests/_fakes.py",
        "apps/telegram-bot/tests/conftest.py",
        "apps/telegram-bot/tests/test_012_phase_a_heartbeat_and_state.py",
        "apps/telegram-bot/tests/test_012_phase_g_alert_and_status.py",
        "apps/telegram-bot/tests/test_012_phases_c_d_supervisor_and_verifier.py",
        "apps/telegram-bot/tests/test_012_phases_e_f_window_and_ledger.py",
        "apps/telegram-bot/tests/test_bigquery_backend.py",
        "apps/telegram-bot/tests/test_clarification.py",
        "apps/telegram-bot/tests/test_comparison.py",
        "apps/telegram-bot/tests/test_configuration.py",
        "apps/telegram-bot/tests/test_dependencies.py",
        "apps/telegram-bot/tests/test_execution_backend.py",
        "apps/telegram-bot/tests/test_free_periods.py",
        "apps/telegram-bot/tests/test_help.py",
        "apps/telegram-bot/tests/test_metrics.py",
        "apps/telegram-bot/tests/test_model.py",
        "apps/telegram-bot/tests/test_no_governance_change.py",
        "apps/telegram-bot/tests/test_od74_his_words_reach_the_vocabulary.py",
        "apps/telegram-bot/tests/test_od76_the_bot_asks_back.py",
        "apps/telegram-bot/tests/test_operational_message.py",
        "apps/telegram-bot/tests/test_polling.py",
        "apps/telegram-bot/tests/test_refusal_boundary.py",
        "apps/telegram-bot/tests/test_roundtrip.py",
        "apps/telegram-bot/tests/test_shutdown.py",
        "apps/telegram-bot/tests/test_the_caller_sends_a_day_once.py",
        "apps/telegram-bot/tests/test_the_class_is_read_from_the_view.py",
        "apps/telegram-bot/tests/test_the_delivered_figure_keeps_his_ceiling.py",
        "apps/telegram-bot/tests/test_the_demo_reaches_the_last_two_features.py",
        "apps/telegram-bot/tests/test_the_env_file_declares_the_backend.py",
        "apps/telegram-bot/tests/test_the_schedule_record_survives_regeneration.py",
        "apps/telegram-bot/tests/test_the_subquery_carries_what_the_outer_select_reads.py",
        "apps/telegram-bot/tests/test_transport.py",
        "apps/telegram-bot/verify_daily_run.py",
        "apps/telegram-bot/write_schedule_record.py",
    ),
    "382f10dd8616f104ba9769fba90e8d2d016e0248": (
        ".claude/settings.json",
        ".github/workflows/harness.yml",
        ".gitignore",
        "PROJECT-HANDOFF-COMPLETE.yml",
        "apps/telegram-bot/README.md",
        "apps/telegram-bot/write_schedule_record.py",
        "docs/credencial-bigquery-service-account.md",
        "docs/readiness/multichannel-external-readiness.yaml",
        "docs/registro-do-agendamento-diario.md",
        "docs/vm-de-producao.md",
        "packages/channel_integration/tests/contract/test_claim_classes.py",
        "packages/daily_reporting/tests/security/test_the_caller_authors_nothing.py",
        "packages/insights_prioritisation/tests/contract/test_a_step_that_did_not_report_is_a_failure.py",
        "packages/insights_prioritisation/tests/contract/test_the_push_gate_covers_every_package.py",
        "specs/009-daily-run-caller-and-trigger/plan.md",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
        "specs/010-report-to-the-declared-recipients/tasks.md",
        "specs/012-orchestration-and-continuous-improvement/plan.md",
        "specs/012-orchestration-and-continuous-improvement/spec.md",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-compare-window.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-supervise.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-verify-daily.service",
        "tools/git-hooks/pre-push",
    ),
    "be1c98eea744edc8f59076a6b701dd4ec6ec1d5c": (".claude/settings.json",),
    "be5e40a7de9dc5e05b44fe41e68853315e59bccb": (
        "packages/channel_integration/tests/contract/test_the_prose_does_not_assert_the_old_world.py",
    ),
    "fe62457f362348cc926a6e960053427c5dd871ce": ("docs/estado-das-nove-frentes.txt",),
    "4b29270a33f9b54454ea129053ad31a20ab7868c": ("docs/estado-das-nove-frentes.txt",),
    "9d743bdf9c83ea7f934ec2225bd80dfb836e13f5": ("docs/estado-das-nove-frentes.txt",),
    # fase G da 012: alerta e /status com as palavras dele, units versionadas.
    "d0daa3cc9e4a53e8a6d0ec820b8a44c629e4af5f": (
        "specs/012-orchestration-and-continuous-improvement/debts-ledger.yaml",
        "specs/012-orchestration-and-continuous-improvement/tasks.md",
        "specs/012-orchestration-and-continuous-improvement/vm/README.md",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-compare-window.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-compare-window.timer",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-supervise.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-supervise.timer",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-verify-daily.service",
        "specs/012-orchestration-and-continuous-improvement/vm/intelligence-agent-verify-daily.timer",
        "tools/telegram-local-roundtrip-harness/compare_window.py",
        "tools/telegram-local-roundtrip-harness/owner_alerts.py",
        "tools/telegram-local-roundtrip-harness/run.py",
        "tools/telegram-local-roundtrip-harness/supervise.py",
        "tools/telegram-local-roundtrip-harness/tests/test_012_phase_g_alert_and_status.py",
        "tools/telegram-local-roundtrip-harness/verify_daily_run.py",
    ),
    # fases E e F da 012: as duas janelas e o ledger com cinco sementes.
    "ecf7ffabfe2e536b5e04df1f68f530d010255efb": (
        "specs/012-orchestration-and-continuous-improvement/debts-ledger.yaml",
        "specs/012-orchestration-and-continuous-improvement/tasks.md",
        "tools/telegram-local-roundtrip-harness/compare_window.py",
        "tools/telegram-local-roundtrip-harness/tests/test_012_phases_e_f_window_and_ledger.py",
    ),
    # fases C e D da 012 (T125..T129 marcadas, decisao do run_fired escrita na linha).
    "f3e85ac3cb04d4d90bc6543711c813ae1ce57e74": (
        "specs/012-orchestration-and-continuous-improvement/tasks.md",
        "tools/telegram-local-roundtrip-harness/supervise.py",
        "tools/telegram-local-roundtrip-harness/tests/test_012_phases_c_d_supervisor_and_verifier.py",
        "tools/telegram-local-roundtrip-harness/verify_daily_run.py",
    ),
    # fase A da 012 (T121..T124 marcadas) e o conserto dos caminhos de runtime.
    "91132d89de240fef481afbcf04349cb3c0d6444d": (
        "specs/012-orchestration-and-continuous-improvement/tasks.md",
        "tools/telegram-local-roundtrip-harness/orchestration.py",
        "tools/telegram-local-roundtrip-harness/run.py",
        "tools/telegram-local-roundtrip-harness/tests/test_012_phase_a_heartbeat_and_state.py",
    ),
    "db78e383f9801474f45a87df819d7cd70bbbeb24": (
        "specs/012-orchestration-and-continuous-improvement/plan.md",
        "specs/012-orchestration-and-continuous-improvement/tasks.md",
    ),
    # S-28: a orfa vira T122 e a divida da citacao invisivel entra no ledger.
    "5c1cc184a358915f33da5dc83d50cf0c1c079e9a": (
        "specs/012-orchestration-and-continuous-improvement/tasks.md",
    ),
    # a gramatica do instrumento: T de tres digitos e promessa na linha.
    "4e8295085291e8c7f01e84153e63e62e53e508e2": (
        "specs/012-orchestration-and-continuous-improvement/tasks.md",
    ),
    # ciclo 471: as seis do OD-75 transcritas, plan e tasks -- papel, so specs/012-.
    "556677cfbd994cab491506d780ee1f79af9834ca": (
        "specs/012-orchestration-and-continuous-improvement/plan.md",
        "specs/012-orchestration-and-continuous-improvement/spec.md",
        "specs/012-orchestration-and-continuous-improvement/tasks.md",
    ),
    # a crase sai do caminho fora da arvore -- mesmo ciclo 468.
    "f894d06e345d026b107e85de1c224fd637bab229": (
        "specs/012-orchestration-and-continuous-improvement/spec.md",
    ),
    # a spec 012 nasce em papel -- ciclo 468, so specs/012-.
    "f22ceabe36595c29210504234f11eda8d4fff4cf": (
        "specs/012-orchestration-and-continuous-improvement/spec.md",
    ),
    # a nomeacao, lista cheia.
    "522ba5e39228af56bd0d71788893ad189bfb7184": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # a declaracao nos tres vigias, lista cheia.
    "fd464cb4d186e31613d2b2b760576d60f5f0647c": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # o fechamento da 008: T836 e T839 fecham no ledger DELA com a medicao citada, e o
    # placar segue a contagem -- ciclo 464, tarefa 1 e 3.
    "ebb4db829340652231121578a6db0895531c3ed7": (
        "docs/estado-das-nove-frentes.txt",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # os tipos estritos, lista cheia.
    "c8d2ae1e0e5fb0fe9bd1ae066013957bd25df7db": (
        "packages/analytics_interaction/tests/integration/test_stateless_clarification.py",
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
        "tools/telegram-local-roundtrip-harness/run.py",
        "tools/telegram-local-roundtrip-harness/run_daily.py",
        "tools/telegram-local-roundtrip-harness/tests/test_the_caller_sends_a_day_once.py",
        "tools/telegram-local-roundtrip-harness/tests/test_the_schedule_record_survives_regeneration.py",
        "tools/telegram-local-roundtrip-harness/write_schedule_record.py",
    ),
    # a declaracao nos dois vigias, lista cheia.
    "57f3a17d73d28ee7e9c28c4368c84e28e4890319": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # a remocao da entrada stale, lista cheia.
    "45317aaba8c7c52302c7964955782ca40ce94b5e": (
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
    ),
    # a nomeacao dos vigias, lista cheia.
    "a06fb08e273fff7a31026bf54e09cafbcc592334": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # o move -- para ESTE _files_of o rename e um caminho so, o novo.
    "c2434f564c14525f6f1b117a59122d7ff921aacf": (
        "packages/daily_reporting/src/daily_reporting/view/shape.py",
        "packages/daily_reporting/tests/unit/test_the_header_the_colour_and_the_places.py",
        "report_governance/section_order.yaml",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
    ),
    # a declaracao nos tres vigias.
    "8d3e7a6df8654c903a4bc6475546d7d29188f940": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # o ajuste.
    "ecc6c2a7c148410528db51f4c312f2db86f6e8e6": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/daily_reporting/src/daily_reporting/view/shape.py",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # a mudanca de chao do OD-70: o yaml sai de semantic/ (chao do catalogo, medido com 131
    # UnknownKindError) para report_governance/, arvore governada propria do relatorio.
    # `OD-70`/`OD-71`: a ordem das secoes vira DADO GOVERNADO em semantic/report/ (dois scans
    # da 008 proibem o atalho de escrever nomes da view no pacote), e MRR/Revenue ganham as
    # duas moedas da MESMA linha da view.
    "2af36b99abfca7037207babeb9d9031b34296c44": (
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/src/daily_reporting/view/shape.py",
        "packages/daily_reporting/tests/unit/test_the_header_the_colour_and_the_places.py",
        "semantic/report/section_order.yaml",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
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
        "packages/conversation_context/src/conversation_context/store/local_file.py",
        "packages/conversation_context/tests/contract/test_memory_has_an_owner_a_scope_and_an_expiry.py",
        "specs/011-conversational-context/tasks.md",
    ),
    # `011` T1110 bloqueada com os tres motivos medidos, escritos no ledger da propria 011.
    "029e7b208838dacf731fba1aff509657cc37efe6": ("specs/011-conversational-context/tasks.md",),
    # `011` fases A-C: o pacote conversation_context nasce (memoria com dono, escopo e
    # expiracao) e o ledger da 011 vai de 0 para 8 com as respostas dele (OD-67, OD-68).
    "6e31a3665f8905608e958b3cf6a3b1ffeafe38f4": (
        "packages/conversation_context/README.md",
        "packages/conversation_context/pyproject.toml",
        "packages/conversation_context/src/conversation_context/__init__.py",
        "packages/conversation_context/src/conversation_context/contracts/__init__.py",
        "packages/conversation_context/src/conversation_context/contracts/memory.py",
        "packages/conversation_context/src/conversation_context/store/__init__.py",
        "packages/conversation_context/src/conversation_context/store/local_file.py",
        "packages/conversation_context/tests/conftest.py",
        "packages/conversation_context/tests/contract/test_memory_has_an_owner_a_scope_and_an_expiry.py",
        "specs/011-conversational-context/spec.md",
        "specs/011-conversational-context/tasks.md",
    ),
    # `011`: a spec do contexto conversacional abre -- spec, plan e tasks, zero codigo. A frente
    # e escolha dele (ciclo 452) e nasce em branch propria.
    "9d22e4fda5d2796ce997025fc207e18b7bcbbf3d": (
        "specs/011-conversational-context/plan.md",
        "specs/011-conversational-context/spec.md",
        "specs/011-conversational-context/tasks.md",
    ),
    # `008` S-27: o FR-804 e emendado NO REQUISITO -- oito, a oitava nomeada, a nona proibida --
    # porque o codigo tinha ido a oito com o OD-63 e o spec ainda dizia sete.
    "db09ce3cf9f7d5357f32638e05ca08f798599bd6": ("specs/008-daily-report-and-rule-alerts/spec.md",),
    # `008` T838 com palavra dele: o limiar do alerta veste a unidade do movimento e o
    # parentese amarra; T837 fecha citando a 009. Toca o tasks.md da 008 e o renderer.
    "d4c0dd0297ca777b3ddedf1d025f5db01e002973": (
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/tests/unit/test_the_header_the_colour_and_the_places.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # `OD-62`: as mensagens de skip de credencial apontam o remedio novo -- a service account
    # por GOOGLE_APPLICATION_CREDENTIALS -- e nao o re-login morto do gcloud. Toca as suites de
    # integracao de quatro pacotes porque era la que o remedio errado estava escrito.
    "0529cef53b7f4367d3e60b85015f549567bf592d": (
        "packages/anomaly_investigation/tests/integration/test_candidate_against_the_real_warehouse.py",
        "packages/anomaly_investigation/tests/integration/test_the_recorded_coverage_still_matches_the_view.py",
        "packages/daily_reporting/tests/integration/test_no_name_from_the_view_is_written_here.py",
        "packages/insights_prioritisation/tests/integration/test_against_real_candidates.py",
        "packages/proactive_distribution/tests/integration/test_a_real_finding_refuses_distribution.py",
        "tools/telegram-local-roundtrip-harness/tests/test_the_class_is_read_from_the_view.py",
    ),
    # `009` S-25: o no do registro passa a afirmar COERENCIA e nao estado, o gerador preserva o
    # ato no rerun do FR-904, e a T913 fecha o ledger em 14/14 -- o registro aconteceu por
    # procuracao autorizada e foi medido no Windows.
    "3b01654744f193d8858d03f45eb52f9d39686058": (
        "docs/registro-do-agendamento-diario.md",
        "packages/daily_reporting/tests/contract/test_the_registered_hour_is_not_earlier_than_the_rebuild.py",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
        "tools/telegram-local-roundtrip-harness/write_schedule_record.py",
    ),
    # `010` fases A e B: a lista DECLARADA de destinatarios, e a idempotencia por dia E por
    # destinatario.
    "20f5f3f876512bd3fc038a676f6b74ec48e9db20": (
        "packages/daily_reporting/src/daily_reporting/origination/conditions.py",
        "packages/daily_reporting/src/daily_reporting/run/journal.py",
        "packages/daily_reporting/tests/contract/test_the_declared_recipients_and_no_other.py",
        "specs/010-report-to-the-declared-recipients/spec.md",
        "specs/010-report-to-the-declared-recipients/tasks.md",
    ),
    # `010` fase C: o laco que envia sai do script e entra no pacote, onde um no o alcanca.
    "223a998d0cd2feec3347a00affa2b89f8209acec": (
        "packages/daily_reporting/src/daily_reporting/run/fanout.py",
        "packages/daily_reporting/tests/contract/test_one_failing_recipient_does_not_cost_the_others.py",
        "specs/010-report-to-the-declared-recipients/tasks.md",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
        "tools/telegram-local-roundtrip-harness/run_daily.py",
        "tools/telegram-local-roundtrip-harness/tests/test_the_caller_sends_a_day_once.py",
    ),
    # `009` S-17 outra vez: ele nao morreu no conserto anterior, ficou MAIS ESTREITO -- de "toda
    # hora diferente do piso" para "toda hora diferente de 08:00", porque a hora simulada era
    # constante. Agora ela e derivada do piso e a troca parte da hora que o documento carrega.
    "5a6598bd83c7104c26079841db067af97bc2896d": (
        "packages/daily_reporting/tests/contract/test_the_registered_hour_is_not_earlier_than_the_rebuild.py",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
    ),
    # `009` S-17, S-18 e S-19: as predicacoes do registro saem do arquivo de teste e entram no
    # pacote, o predicado vira NAO ANTERIOR em vez de igual, o /ST do COMANDO passa a ser conferido
    # e o SIM passa a custar. Toca specs/009 porque as sete mutacoes ficam registradas ali.
    "ab614c9048ea5fa5c0960ded8f3847b49285e83c": (
        "docs/registro-do-agendamento-diario.md",
        "packages/daily_reporting/src/daily_reporting/schedule/record.py",
        "packages/daily_reporting/tests/contract/test_the_registered_hour_is_not_earlier_than_the_rebuild.py",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
        "tools/telegram-local-roundtrip-harness/write_schedule_record.py",
    ),
    # `009` Fase D: o registro do agendamento, GERADO a partir do piso derivado, e o no da T904
    # que ele destrava. Toca specs/009 porque o ledger foi de 11 para 13, e a decima quarta e dele.
    "6ce4bb226b68917901eaf020f3ef8c93a7154ded": (
        "docs/registro-do-agendamento-diario.md",
        "packages/daily_reporting/tests/contract/test_the_registered_hour_is_not_earlier_than_the_rebuild.py",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
        "tools/telegram-local-roundtrip-harness/write_schedule_record.py",
    ),
    # `009` Fases C e E: o caller, o no do FR-902 e a entrega ao vivo das 06:10:10Z. Toca
    # specs/009 porque o ledger foi de 7 para 11, e toca o deliver_daily_report.py porque o dia
    # carregado expos um StopIteration que sobreviveu dois ciclos atras da recusa do dia vazio.
    "ed46664a767782f72d1d60edb4b0511c23a398e5": (
        ".gitignore",
        "packages/daily_reporting/tests/security/test_the_caller_authors_nothing.py",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
        "tools/telegram-local-roundtrip-harness/run_daily.py",
        "tools/telegram-local-roundtrip-harness/tests/test_the_caller_sends_a_day_once.py",
    ),
    # `009`: a qualificacao do `008:T828` e a declaracao do f8280cf. Toca specs/009 porque a
    # referencia mal escrita estava la; a declaracao de uma travessia sempre chega no commit
    # seguinte, porque um commit nao pode nomear o proprio sha.
    "cdd7a2e92dde71adc41ea80287663a9849df461a": (
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
    ),
    # `009` Fase B: o diario, que responde as duas perguntas com um registro so -- o que
    # aconteceu e se o dia fechado ja foi. Toca specs/009 porque o ledger foi de 3 para 7.
    "f8280cf153017c4a69020778566e219bdac84c81": (
        "packages/daily_reporting/src/daily_reporting/run/__init__.py",
        "packages/daily_reporting/src/daily_reporting/run/journal.py",
        "packages/daily_reporting/tests/contract/test_a_day_already_sent_is_not_sent_again.py",
        "packages/daily_reporting/tests/contract/test_every_run_is_recorded_with_its_zone.py",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
    ),
    # `009` OD-51: a spec do caller e do gatilho abre em branch propria, e a Fase A entrega a
    # derivacao da hora no pacote. Toca specs/009 porque a spec E o trabalho, e toca
    # daily_reporting porque a licao do 408 e que a decisao mora onde um no a alcanca.
    #
    # POR QUE ESTA LINHA CHEGOU UM CICLO ATRASADA, e vale escrever: a suite foi medida ANTES
    # do commit que cria a travessia. O guarda le a JANELA DE COMMITS -- antes de commitar nao
    # existe o que ele possa ver, entao ele leu verde por nao ter o que ler. Verde por medir na
    # hora errada, primo do verde por pular e do verde por nao medir. A suite que vale, quando o
    # ciclo cria arquivo fora do proprio escopo, e a rodada DEPOIS do commit.
    "4ea6f10a7b88171c2bcc2f677cef1ba599d3e062": (
        "packages/daily_reporting/src/daily_reporting/schedule/__init__.py",
        "packages/daily_reporting/src/daily_reporting/schedule/derive.py",
        "packages/daily_reporting/tests/contract/test_the_trigger_hour_is_derived_from_the_rebuild.py",
        "specs/009-daily-run-caller-and-trigger/plan.md",
        "specs/009-daily-run-caller-and-trigger/spec.md",
        "specs/009-daily-run-caller-and-trigger/tasks.md",
    ),
    # `008` OD-52 e OD-54: a descricao para de afirmar um numero e um NO passa a contar uma
    # linha por KPI ativo; e a Fase G abre o que ainda falta, entao o ledger cai de 35 de 35
    # para 35 de 39. Toca o tasks.md da 008, que e trabalho da 008 e nao travessia para ca.
    "61d07373bea5c22307a4c37ece032f8d749e10e0": (
        "packages/daily_reporting/src/daily_reporting/report/template.py",
        "packages/daily_reporting/tests/contract/test_every_kpi_declares_its_column_and_no_gap_was_filled.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
    ),
    # `008` OD-46: as duas palavras saem da linha do KPI, e o cabecalho vira o unico
    # vinculo entre numero e dia.
    "b7feaacdd9de3b113b955f9260f55f8fbd7e54fe": (
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/tests/unit/test_the_header_the_colour_and_the_places.py",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
    ),
    # `008` OD-48: o rotulo do KPI em negrito, e a marcacao SAI do pacote para o transporte.
    "26e6317ac603c7aa1250feda36f2a1043c3aa7b8": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
        "tools/telegram-local-roundtrip-harness/telegram_client.py",
        "tools/telegram-local-roundtrip-harness/tests/test_transport.py",
    ),
    # `008` OD-49: cada produto diz o que e, e dois KPIs atrasados param de sumir calados.
    # Toca o spec da 008 porque o FR-804 foi de tres strings autoradas para SETE.
    "01120a3a0a0ad78ebb50119ec7165ac40e00a835": (
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/src/daily_reporting/report/template.py",
        "packages/daily_reporting/tests/contract/test_only_his_words_are_authored_here.py",
        "specs/008-daily-report-and-rule-alerts/spec.md",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
    ),
    # `008`: os cinco achados dele na primeira leitura -- a ordem invertida, o parenteses,
    # a data, a bola e as casas decimais. Toca o spec da 008 porque o FR-804 foi de duas
    # strings autoradas para tres, com a decisao dele escrita ao lado.
    "25518a6f49b2d06309d29dec0502252244659163": (
        "docs/entrega-do-relatorio-2026-08-30.md",
        "docs/modelos-da-mensagem-diaria.md",
        "docs/resumo-sexta-e-hoje.txt",
        "packages/daily_reporting/src/daily_reporting/alert/rule.py",
        "packages/daily_reporting/src/daily_reporting/alert/threshold.py",
        "packages/daily_reporting/src/daily_reporting/numbers/variation.py",
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/src/daily_reporting/report/template.py",
        "packages/daily_reporting/tests/unit/test_the_header_the_colour_and_the_places.py",
        "packages/daily_reporting/tests/unit/test_the_report_carries_every_kpi.py",
        "packages/daily_reporting/tests/unit/test_the_threshold_is_computed.py",
        "specs/008-daily-report-and-rule-alerts/spec.md",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
    ),
    # `008`: os vinte KPIs, o alerta como segundo produto, e o layout que deixou de depender
    # de fonte. Toca o spec da 008 no FR-805 e no SC-801, emendados para dizer todo KPI ATIVO
    # quando ele mandou tirar o CAC da lista.
    "26e79b78a53ba29e27c17d042f31128048902719": (
        "packages/daily_reporting/src/daily_reporting/alert/rule.py",
        "packages/daily_reporting/src/daily_reporting/alert/threshold.py",
        "packages/daily_reporting/src/daily_reporting/contracts/reason_codes.py",
        "packages/daily_reporting/src/daily_reporting/numbers/variation.py",
        "packages/daily_reporting/src/daily_reporting/origination/conditions.py",
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/tests/contract/test_every_kpi_declares_its_column_and_no_gap_was_filled.py",
        "packages/daily_reporting/tests/unit/test_the_header_the_colour_and_the_places.py",
        "packages/daily_reporting/tests/unit/test_the_report_carries_every_kpi.py",
        "semantic/metrics/cac_brl.yaml",
        "specs/008-daily-report-and-rule-alerts/spec.md",
        "tools/telegram-local-roundtrip-harness/deliver_daily_report.py",
        "tools/telegram-local-roundtrip-harness/telegram_client.py",
        "tools/telegram-local-roundtrip-harness/tests/test_transport.py",
    ),
    # `008`: cada linha passa a nomear os dois dias, para ser legivel sozinha nas vinte.
    "d9fba27a89961ab37a7be97af4bc6253cdb5c345": (
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
    ),
    # `008`: a declaracao da travessia da T829, e ela e ela mesma uma travessia -- nomear um
    # cruzamento e trabalho que cruza. Termina aqui: o proximo commit nao toca arquivo
    # vigiado por este guarda.
    "2cf88c2d00f03de6b8611789678faba8902b20e4": (
        "packages/anomaly_investigation/tests/contract/test_no_upstream_file_was_edited.py",
        "packages/channel_integration/tests/contract/test_upstream_untouched.py",
        "packages/channel_integration/tests/fixtures/upstream_node_ids.json",
        "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py",
        "tools/telegram-local-roundtrip-harness/tests/test_metrics.py",
    ),
    # `008` T827 e T828: os dois guardas nascem, e a marca no tasks.md da 008 e trabalho
    # da 008 -- estrangeiro para esta feature, nao travessia para dentro dela.
    "e0624ac681bad1cd370b81b9ddd9708d5ae38bc6": (
        "packages/daily_reporting/tests/security/test_the_key_is_named_and_no_readiness_is_declared.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # `008` T829: os dezenove entram no catalogo. Toca o tasks.md da 008 e a tabela publicada
    # da 001, que registra os dois campos novos que o FR-806 e o FR-808 exigem.
    "3222492d1e048770c55343fbca219b7137942465": (
        "docs/pedido-ao-business-intelligence-linhas-de-observacao.md",
        "packages/daily_reporting/tests/contract/test_every_kpi_declares_its_column_and_no_gap_was_filled.py",
        "packages/daily_reporting/tests/security/test_nothing_is_signed_and_nothing_is_written.py",
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
        "schemas/access_tags.schema.json",
        "schemas/catalog_decision_audit_event.schema.json",
        "schemas/catalog_policy.schema.json",
        "schemas/comparability.schema.json",
        "schemas/dimension.schema.json",
        "schemas/freshness_approvals.schema.json",
        "schemas/glossary.schema.json",
        "schemas/metric.schema.json",
        "schemas/owners.schema.json",
        "schemas/pending_visibility_approvals.schema.json",
        "schemas/reason_messages.schema.json",
        "schemas/source.schema.json",
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
        "specs/001-semantic-catalog/contracts/catalog-file-contracts.md",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # `008`: S-4, the record created and never enumerated
    "1279b55846790e8c14e9e54748ed869e44e9310c": (
        "packages/channel_integration/src/channel_integration/cli/main.py",
        "packages/channel_integration/src/channel_integration/compliance/readiness.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/channel_integration/tests/contract/test_the_split_key_is_asked_by_its_callers.py",
        "packages/channel_integration/tests/integration/test_readiness_locks.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
        "tools/telegram-local-roundtrip-harness/tests/test_no_governance_change.py",
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
        "packages/daily_reporting/src/daily_reporting/origination/conditions.py",
        "packages/proactive_distribution/src/proactive_distribution/distribute/conditions.py",
        "packages/proactive_distribution/tests/security/test_no_readiness_record_is_touched.py",
        "packages/proactive_distribution/tests/unit/test_the_three_conditions_are_each_load_bearing.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # `008`: four more nodes asserting the old world, harness guard included
    "266b37144ebb48c92c4adbc6c784e7dc24f15240": (
        "packages/channel_integration/tests/contract/test_fifth_channel.py",
        "tools/telegram-local-roundtrip-harness/tests/test_no_governance_change.py",
    ),
    # `008`: OD-20-A splits the key, and 24 nodes across seven files re-derived
    "9fc3b62188d6b8878fe15b704f9d2fcc733575e1": (
        "docs/rascunho-definicoes-dezenove-kpis.md",
        "docs/readiness/multichannel-external-readiness.yaml",
        "packages/channel_integration/src/channel_integration/compliance/readiness.py",
        "packages/channel_integration/src/channel_integration/inbound/verify.py",
        "packages/channel_integration/tests/adversarial/test_fixture_substitution.py",
        "packages/channel_integration/tests/contract/test_cli.py",
        "packages/channel_integration/tests/contract/test_readiness.py",
        "packages/channel_integration/tests/contract/test_replay_defence_bound.py",
        "packages/channel_integration/tests/integration/test_readiness_locks.py",
        "packages/channel_integration/tests/integration/test_refusal_paths.py",
        "packages/channel_integration/tests/integration/test_round_trip.py",
        "packages/daily_reporting/src/daily_reporting/numbers/variation.py",
        "packages/daily_reporting/tests/unit/test_the_five_conditions_are_each_load_bearing.py",
        "packages/daily_reporting/tests/unit/test_the_report_carries_every_kpi.py",
        "packages/proactive_distribution/tests/unit/test_the_three_conditions_are_each_load_bearing.py",
        "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # `008`: ADR 0036's conditions proved, and a fourth absent view found
    "2903181e85f8619dccee807335c527d17b01fc1a": (
        "packages/daily_reporting/src/daily_reporting/contracts/origination_codes.py",
        "packages/daily_reporting/src/daily_reporting/origination/__init__.py",
        "packages/daily_reporting/src/daily_reporting/origination/conditions.py",
        "packages/daily_reporting/tests/contract/test_namespace_is_disjoint.py",
        "packages/daily_reporting/tests/contract/test_the_two_adrs_say_what_they_say.py",
        "packages/daily_reporting/tests/security/test_nothing_is_signed_and_nothing_is_written.py",
        "packages/daily_reporting/tests/unit/test_the_five_conditions_are_each_load_bearing.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # `008`: the zero rule committed, and T830's names half measured
    "8d767fcb5d25ca066bfc860285f600b6e7518a0c": (
        "packages/daily_reporting/src/daily_reporting/view/reading.py",
        "packages/daily_reporting/tests/contract/test_the_loop_enumerates_nothing.py",
        "packages/daily_reporting/tests/integration/__init__.py",
        "packages/daily_reporting/tests/integration/test_no_name_from_the_view_is_written_here.py",
        "packages/daily_reporting/tests/unit/test_absent_is_not_zero.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # `008`: the label finding, and Phase F's property
    "92fcabac314257c211a3f2e86e24dd5ca5b6630d": (
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/tests/contract/test_the_loop_enumerates_nothing.py",
        "packages/daily_reporting/tests/unit/test_the_report_carries_every_kpi.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    # `008` Phase E: the replay gate's count proxy re-derived; d_24 declaration withdrawn
    "f6bd047124f188e7ee66759852b32bc1d49b65ca": (
        "docs/readiness/multichannel-external-readiness.yaml",
        "docs/release/multichannel-internal-validation.md",
        "docs/release/multichannel-release-state.md",
        "packages/channel_integration/tests/contract/test_replay_defence_bound.py",
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/tests/unit/test_the_report_carries_every_kpi.py",
        "packages/proactive_distribution/tests/unit/test_the_three_conditions_are_each_load_bearing.py",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    "9b801a81ef19eb29d4dfeced9d648ebdea9ceed0": (  # `007`: T703, T716, T702
        "packages/proactive_distribution/src/proactive_distribution/distribute/conditions.py",
        "packages/proactive_distribution/tests/integration/__init__.py",
        "packages/proactive_distribution/tests/integration/test_a_real_finding_refuses_distribution.py",
        "packages/proactive_distribution/tests/security/test_no_readiness_record_is_touched.py",
        "packages/proactive_distribution/tests/unit/test_the_three_conditions_are_each_load_bearing.py",
        "specs/007-proactive-distribution/tasks.md",
    ),
    "e3a6e283b244feb44fde5ee71eba913c8489b12e": (  # `007`: his five labels
        "packages/proactive_distribution/src/proactive_distribution/distribute/labels.py",
        "packages/proactive_distribution/tests/contract/test_no_label_was_authored_here.py",
        "specs/007-proactive-distribution/plan.md",
        "specs/007-proactive-distribution/tasks.md",
    ),
    "db93991facd04ab4c424634f4ed44bcd671a2dae": (  # `007`: package and plan
        "packages/proactive_distribution/README.md",
        "packages/proactive_distribution/pyproject.toml",
        "packages/proactive_distribution/src/proactive_distribution/__init__.py",
        "packages/proactive_distribution/src/proactive_distribution/contracts/__init__.py",
        "packages/proactive_distribution/src/proactive_distribution/contracts/_base.py",
        "packages/proactive_distribution/src/proactive_distribution/contracts/reason_codes.py",
        "packages/proactive_distribution/src/proactive_distribution/contracts/report.py",
        "packages/proactive_distribution/src/proactive_distribution/distribute/__init__.py",
        "packages/proactive_distribution/src/proactive_distribution/distribute/conditions.py",
        "packages/proactive_distribution/src/proactive_distribution/distribute/labels.py",
        "packages/proactive_distribution/src/proactive_distribution/distribute/recipient.py",
        "packages/proactive_distribution/tests/__init__.py",
        "packages/proactive_distribution/tests/conftest.py",
        "packages/proactive_distribution/tests/contract/__init__.py",
        "packages/proactive_distribution/tests/contract/test_no_label_was_authored_here.py",
        "packages/proactive_distribution/tests/contract/test_the_five_fields_are_the_shape_he_chose.py",
        "packages/proactive_distribution/tests/security/__init__.py",
        "packages/proactive_distribution/tests/security/test_no_composed_prose.py",
        "packages/proactive_distribution/tests/security/test_originates_nothing.py",
        "packages/proactive_distribution/tests/unit/__init__.py",
        "packages/proactive_distribution/tests/unit/test_the_recipient_is_derived.py",
        "packages/proactive_distribution/tests/unit/test_the_three_conditions_are_each_load_bearing.py",
        "specs/007-proactive-distribution/plan.md",
        "specs/007-proactive-distribution/tasks.md",
    ),
    "1e99c34ae6c6c954627901c9d5f2e58130d6b0dc": (  # `007`, planned on its own branch
        "docs/adr/0035-proactive-distribution-supersedes-fr-062-for-item-8-only.md",
        "specs/007-proactive-distribution/plan.md",
        "specs/007-proactive-distribution/spec.md",
        "specs/007-proactive-distribution/tasks.md",
    ),
    "d113205e14b0edfb3f7333ed6582969aeb826e5d": (  # `008`: the ADR-0035 authority claim corrected
        "specs/008-daily-report-and-rule-alerts/plan.md",
        "specs/008-daily-report-and-rule-alerts/spec.md",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    "8f3b90057b08bb39ce8ca14d4248ddbf28c6ef2e": (  # `008`: ADR 0036, written after the decision
        "docs/adr/0036-daily-report-and-rule-alerts-supersede-fr-062-for-two-named-products.md",
        "specs/008-daily-report-and-rule-alerts/plan.md",
        "specs/008-daily-report-and-rule-alerts/spec.md",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    "2ec7ef717b19edee804cc0a8469c7913554e6e64": (  # `008`: phases A to D, and the ledger marked
        "packages/daily_reporting/README.md",
        "packages/daily_reporting/pyproject.toml",
        "packages/daily_reporting/src/daily_reporting/__init__.py",
        "packages/daily_reporting/src/daily_reporting/alert/__init__.py",
        "packages/daily_reporting/src/daily_reporting/alert/rule.py",
        "packages/daily_reporting/src/daily_reporting/alert/threshold.py",
        "packages/daily_reporting/src/daily_reporting/contracts/__init__.py",
        "packages/daily_reporting/src/daily_reporting/contracts/_base.py",
        "packages/daily_reporting/src/daily_reporting/contracts/reason_codes.py",
        "packages/daily_reporting/src/daily_reporting/numbers/__init__.py",
        "packages/daily_reporting/src/daily_reporting/numbers/column.py",
        "packages/daily_reporting/src/daily_reporting/numbers/period.py",
        "packages/daily_reporting/src/daily_reporting/numbers/variation.py",
        "packages/daily_reporting/src/daily_reporting/report/__init__.py",
        "packages/daily_reporting/src/daily_reporting/report/summary.py",
        "packages/daily_reporting/src/daily_reporting/report/template.py",
        "packages/daily_reporting/src/daily_reporting/view/__init__.py",
        "packages/daily_reporting/src/daily_reporting/view/shape.py",
        "packages/daily_reporting/tests/__init__.py",
        "packages/daily_reporting/tests/conftest.py",
        "packages/daily_reporting/tests/contract/__init__.py",
        "packages/daily_reporting/tests/contract/test_namespace_is_disjoint.py",
        "packages/daily_reporting/tests/contract/test_only_his_words_are_authored_here.py",
        "packages/daily_reporting/tests/contract/test_the_shape_is_read_from_the_view.py",
        "packages/daily_reporting/tests/contract/test_the_two_products_never_merge.py",
        "packages/daily_reporting/tests/security/__init__.py",
        "packages/daily_reporting/tests/security/test_no_composed_prose_and_nothing_originates.py",
        "packages/daily_reporting/tests/security/test_no_p90_constant_anywhere.py",
        "packages/daily_reporting/tests/unit/__init__.py",
        "packages/daily_reporting/tests/unit/test_the_period_and_the_closed_day.py",
        "packages/daily_reporting/tests/unit/test_the_report_carries_every_kpi.py",
        "packages/daily_reporting/tests/unit/test_the_threshold_is_computed.py",
        "packages/daily_reporting/tests/unit/test_the_unit_comes_from_the_format.py",
        "packages/daily_reporting/tests/unit/test_the_value_column_is_declared.py",
        "specs/008-daily-report-and-rule-alerts/spec.md",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
    "23ad9236677fe6eca87eb5a1d65129756a30e242": (  # `008`, planned on its own branch
        "specs/008-daily-report-and-rule-alerts/plan.md",
        "specs/008-daily-report-and-rule-alerts/spec.md",
        "specs/008-daily-report-and-rule-alerts/tasks.md",
    ),
}


def _reach_list_names() -> set[str]:
    """Every constant in this module that maps a sha to a reach.

    Derived from the module's own namespace rather than listed, so the two nodes below
    disagree with reality rather than with a copy.
    """
    return {
        name
        for name, value in globals().items()
        if name.startswith("AUTHORIZED_") and isinstance(value, dict)
    }


def _all_commits() -> list[str]:
    """**The PROHIBITION window: every commit in the range, filtered by nothing.**

    A commit that touches only upstream has no root of ours in it, which is precisely why
    the root filter must not stand between this branch and the checks that forbid upstream
    edits. `_feature_commits()` stays what it is -- the ATTRIBUTION window, which answers
    *which commits are ours* -- and the two are not interchangeable.
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

    ``named`` is a parameter rather than a constant read, and that is the `G-1` lesson taken
    from `005`'s copy of this file rather than relearned: it is what lets a node **drive
    this function** with one name withheld and assert the withheld crossing comes back. A
    node that merely compared the two windows would prove only that both exist -- and the
    defect was never a missing window, it was which one the prohibition consumed.
    """
    names = AUTHORIZED_CROSSINGS if named is None else named
    touched: set[str] = set()
    for sha in _all_commits():
        if sha in names:
            continue
        touched.update(_crossings_of(sha))
    return sorted(touched)


def _paths_of_unnamed_commits() -> set[str]:
    """Every path touched by a commit in the prohibition window that is not a named crossing.

    Wider than `_unnamed_crossings`, which narrows to `WATCHED_PREFIXES`. It exists because
    the spec prohibition watches a tree that is NOT in those prefixes: `specs/006-` is this
    feature's own and must not be watched, so adding `specs/` to the shared list would turn
    every commit of ours into an unnamed crossing.
    """
    touched: set[str] = set()
    for sha in _all_commits():
        if sha in AUTHORIZED_CROSSINGS or sha in AUTHORIZED_FOREIGN_WORK:
            continue
        touched.update(_files_of(sha))
    return touched


def test_the_base_is_still_an_ancestor_of_head() -> None:
    """**Absence of history skips; a real answer of "no" fails.**

    ``--is-ancestor`` answers ``1`` for no and ``128`` for *unknown commit*, which is
    what a shallow checkout says about everything but the tip. Asserting
    ``returncode == 0`` would turn a missing object into a reported boundary violation
    — a node going red for something that is not what it guards.
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


def test_the_window_is_readable_and_not_empty() -> None:
    """**A comparison that found nothing would pass by doing nothing.**

    This feature has changed files. An empty window means the anchor or the roots are
    wrong, and every assertion below would be vacuously true — the failure mode this
    repository keeps closing, most recently by reporting the empty answer of a check
    against a directory that did not exist as though it were a proof.
    """
    commits = _feature_commits()
    assert commits, f"no commit of this feature is in {BASE[:7]}..HEAD; the anchor is wrong"
    assert _changed_files(), "the window names no file; the checks below would be vacuous"


def test_the_root_filter_discriminates() -> None:
    """**The path filter, asserted rather than trusted -- and re-derived after the rewrite.**

    The earlier form asserted that the range held **strictly more** commits than the
    feature does. That was true while this branch carried `005`'s history behind its own
    anchor, and the rewrite made it false -- not because the filter stopped working, but
    because the window no longer holds anybody else's work. **A node whose proof depends
    on a mess existing is a node that fails when the mess is cleaned up.**

    ## And the FIRST of the two measurements was itself `F135`, found on 2026-08-27

    It read *"every commit in the window touches a root of this feature"*, and that is
    **false the moment the repository continues past this feature** -- a repository-wide
    repair, a fix to another package, anything at all that is not `006` lands inside
    `BASE..HEAD` and turns this node red. **It fails when the repository succeeds**, which
    is the exact shape this file's own docstring was written to refuse, reappearing one
    assertion further down.

    It bit for real: a cycle ordered seventy-seven strict type errors zeroed across every
    package, and the commit carrying the repository-wide half made this node red for
    existing. Splitting the commit was right and necessary for the OTHER assertions --
    a commit touching a feature root and an upstream package is exactly what they catch --
    but no split makes a non-`006` commit stop being a non-`006` commit.

    ## The assertion is REMOVED rather than replaced, and the first replacement was vacuous

    **I wrote a replacement first and it was worthless, which was measured rather than
    suspected.** It said: *every commit in the window that is not ours must touch none of
    our roots*. That is a tautology -- "not ours" is DEFINED as "touches none of our
    roots", so the two halves are the same predicate and the assertion cannot fail. The
    mutation that should have caught it -- narrowing `FEATURE_ROOTS` so real feature
    commits fall outside the measured set -- came back **green**, which is the `G-1`
    defect exactly: a check comparing a derivation against itself.

    There is no non-vacuous replacement, and the reason is worth writing down rather than
    hunting for one: any commit touching this feature's files is IN `_feature_commits()`
    by construction, so "a commit edited us without being counted" is not a state this
    repository can reach. What the old assertion actually detected was **unrelated work
    existing on the line** -- the branch's tidiness, not this feature's boundary.

    **What still holds, and it is the part that was ever about the boundary:** the filter
    discriminates, proved on the anchor itself -- `BASE` is a `005` commit, it touches none
    of these roots, and the same predicate that builds the window excludes it. Every other
    node in this file measures the diff of `_feature_commits()`, and none of them cares
    whether somebody else committed alongside.
    """
    ours = _feature_commits()
    assert ours, "the window names no commit of this feature; the anchor is wrong"

    anchor_under_our_roots = [
        line.strip()
        for line in _git(
            "log", "--format=%H", f"{BASE}~1..{BASE}", "--", *FEATURE_ROOTS
        ).splitlines()
        if line.strip()
    ]
    assert not anchor_under_our_roots, (
        f"{BASE[:7]} is a 005 commit that touches this feature's roots, so the filter "
        "cannot tell our work from theirs"
    )


def _invisible_to_the_attribution_window() -> list[str]:
    """The named crossings the ROOT-FILTERED window cannot see.

    These are the whole point of the prohibition window existing: a commit touching only
    upstream has no root of ours in it, so `_feature_commits()` never walks it. If this list
    were empty, every probe below would be comparing the two windows on commits both can
    see -- and would pass while the prohibition read the wrong one.
    """
    ours = set(_feature_commits())
    return [sha for sha in AUTHORIZED_CROSSINGS if sha not in ours]


def test_there_is_a_crossing_the_attribution_window_cannot_see() -> None:
    """The premise of the two nodes below, stated so its failure is loud.

    With every crossing also touching a feature root, the probes cannot tell the windows
    apart and would prove nothing while passing -- so the absence is asserted here rather
    than discovered as a silent weakening later.
    """
    assert _invisible_to_the_attribution_window(), (
        "every named crossing also touches a feature root, so nothing here can distinguish "
        "the prohibition window from the attribution one"
    )


def test_the_prohibition_actually_consumes_the_unfiltered_window() -> None:
    """**`G-1`, inherited from `005`'s copy of this file rather than paid for again.**

    `005` learned this the expensive way: two nodes existed to stop the prohibition reading
    the root-filtered window, both asserted only that TWO WINDOWS EXIST, and the regression
    walked between them while the guards announced it could not. The defect was never a
    missing window -- it was **which window the prohibition consumed**.

    So this DRIVES the function. One named crossing the attribution window cannot see is
    withheld from the list, and its paths must come back out. Under the filtered window that
    commit is not walked at all, nothing comes back, and this goes red.
    """
    probe = _invisible_to_the_attribution_window()[0]
    withheld = {sha: reach for sha, reach in AUTHORIZED_CROSSINGS.items() if sha != probe}
    exposed = set(_unnamed_crossings(withheld))
    recorded = set(AUTHORIZED_CROSSINGS[probe])
    assert recorded, f"{probe[:7]} records no path, so withholding it exposes nothing"
    assert recorded <= exposed, (
        f"withholding {probe[:7]} exposed {sorted(recorded - exposed)} nowhere: the "
        "prohibition is reading the root-filtered window, which is the F-1 defect back"
    )


def test_every_declaration_really_crossed_and_nothing_crossed_undeclared() -> None:
    """**The reach is a claim in both directions, and both are measured.**

    A crossing recorded with paths it did not touch is a declaration nobody can trust; a
    crossing that touches one file more than it declares is a crossing that widened without
    a decision. The second is the one that matters day to day -- it is what stops a commit
    inheriting a name it already has while reaching somewhere new.
    """
    for sha, declared in AUTHORIZED_CROSSINGS.items():
        actual = _crossings_of(sha)
        assert set(declared) == set(actual), (
            f"{sha[:7]} declares {sorted(set(declared) - set(actual))} it did not touch and "
            f"touched {sorted(set(actual) - set(declared))} it did not declare"
        )


def test_every_foreign_declaration_really_touched_what_it_declares() -> None:
    """**The same claim, for the other list — and it went unmade for four crossings.**

    `AUTHORIZED_FOREIGN_WORK` was given the SHAPE of its sibling -- full path tuples and a
    docstring saying *named with its reach* -- **without the node that makes a reach mean
    anything.** It appeared in exactly two places: its definition, and an `if sha in ...:
    continue` that reads THE KEY ALONE. Twelve lines from a node asserting precisely this,
    in the same file.

    **Measured before the fix**, and the contrast is the proof: removing a path from a reach
    in `AUTHORIZED_FOREIGN_WORK` left **14 passed** and nothing bit; removing one from
    `AUTHORIZED_CROSSINGS` gave **1 failed**, naming it.

    The four `007` crossings named in that list were checked against their commits by hand
    and were correct -- so this was a **defect of the instrument and not a crossing that got
    through**, which is exactly why it is worth fixing before one does.

    **The comparison is over ALL files the commit touched**, not the watched ones: this list
    exists for foreign work whose subject is `specs/` and `docs/`, neither of which is in
    `WATCHED_PREFIXES`. Narrowing it here would reproduce the original hole in a new place.
    """
    for sha, declared in AUTHORIZED_FOREIGN_WORK.items():
        actual = set(_files_of(sha))
        assert set(declared) == actual, (
            f"{sha[:7]} declares {sorted(set(declared) - actual)} it did not touch and "
            f"touched {sorted(actual - set(declared))} it did not declare"
        )


def test_every_reach_list_is_actually_consumed_by_a_node() -> None:
    """**The claim this node used to make in prose while measuring something else.**

    Its docstring said every reach mapping *"must be consumed by a node above"*, and it
    compared an INVENTORY OF NAMES. Measured: a third list appearing was caught, and
    **deleting the node that reads the foreign reach left 15 passed** — the guard stayed
    green asserting that a consumer existed, over a consumer that had been removed.

    So it walks the syntax tree of this module and asks where each name is READ. A list is
    consumed when its name appears inside the body of a node — a `test_` function — and not
    merely at its own assignment. That is the same move `007`'s disguise scan made for the
    same reason: **look at code, not at names.**

    The mechanism the old node really held is kept and stated separately below, because it
    is worth having: a third list cannot appear without a decision.
    """
    module = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    read_in_nodes: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        for descendant in ast.walk(node):
            if isinstance(descendant, ast.Name):
                read_in_nodes.add(descendant.id)

    unconsumed = sorted(name for name in _reach_list_names() if name not in read_in_nodes)
    assert not unconsumed, (
        f"these reach lists are declared and read by no node: {unconsumed}. A reach nothing "
        "reads is a declaration that cannot fail, which is what this file already paid for."
    )


def test_the_named_consumers_are_the_ones_that_compare_a_reach() -> None:
    """**Consumed is not enough — it must be consumed by something that CHECKS the reach.**

    A list mentioned in a node that only counts it would satisfy the walk above. So the two
    comparing nodes are asserted by name here, and each is asserted to READ its own list:
    delete either one and the node above goes red for the deletion, this one for the name.
    """
    module = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    reads: dict[str, set[str]] = {}
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        reads[node.name] = {
            descendant.id for descendant in ast.walk(node) if isinstance(descendant, ast.Name)
        }

    expected = {
        "test_every_declaration_really_crossed_and_nothing_crossed_undeclared": (
            "AUTHORIZED_CROSSINGS"
        ),
        "test_every_foreign_declaration_really_touched_what_it_declares": (
            "AUTHORIZED_FOREIGN_WORK"
        ),
    }
    missing = sorted(name for name in expected if name not in reads)
    assert not missing, f"the node that compares a reach is gone: {missing}"

    wrong = sorted(name for name, constant in expected.items() if constant not in reads[name])
    assert not wrong, f"these nodes no longer read the list they are named for: {wrong}"


def test_no_third_reach_list_appears_without_a_decision() -> None:
    """The mechanism the old node genuinely held, kept and now saying what it measures.

    An inventory, and an inventory is the right instrument for THIS question: a list nobody
    decided on should not exist at all, whatever any node does with it.
    """
    assert _reach_list_names() == {"AUTHORIZED_CROSSINGS", "AUTHORIZED_FOREIGN_WORK"}, (
        f"a reach list was added or removed without a decision: {sorted(_reach_list_names())}"
    )
    assert all(globals()[name] for name in _reach_list_names()), (
        "a reach list is empty, so the node reading it asserts nothing"
    )


def test_the_prohibition_window_is_wider_than_the_attribution_one() -> None:
    """**A necessary condition, and NOT the proof -- that is the `G-1` lesson.**

    Equal windows would mean the prohibitions read the root-filtered set again under a new
    name. But equal windows were never the failure: the windows differed and the prohibition
    consumed the wrong one anyway. This stays as the cheap structural check; the node above
    is what holds the behaviour down.
    """
    assert set(_feature_commits()) < set(_all_commits()), (
        "the two windows hold the same commits, so the prohibitions are reading the "
        "attribution window under another name"
    )


@pytest.mark.parametrize("package", UPSTREAM)
def test_no_file_of_an_upstream_package_was_changed(package: str) -> None:
    """Any path under `packages/<upstream>/` is an edit, whatever its content.

    Including a test: `FR-008` says the boundary is not widened, and adding a test to
    an upstream suite is changing that package.
    """
    prefix = f"packages/{package}/"
    touched = [path for path in _unnamed_crossings() if path.startswith(prefix)]
    assert not touched, f"{package} was edited by a commit nobody named: {touched}"


def test_no_governed_content_was_changed() -> None:
    """Three governed trees, none of them this feature's to write."""
    touched = [
        path
        for path in _unnamed_crossings()
        if path.startswith(("semantic/", "interpretation_governance/", "channel_governance/"))
    ]
    assert not touched, f"governed content was edited by a commit nobody named: {touched}"


def test_no_other_features_spec_was_touched() -> None:
    """`005`'s ledger is not this feature's to mark, and neither is anybody else's.

    The reverse direction of the branch rule: `006` work stays on the `006` branch, and
    `006` commits stay out of other features' documents.
    """
    touched = sorted(
        path
        for path in _paths_of_unnamed_commits()
        if path.startswith("specs/") and not path.startswith("specs/006-")
    )
    assert not touched, f"another feature's spec was edited: {touched}"
