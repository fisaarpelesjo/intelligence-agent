"""T116 — every upstream change since `T106` is one an ADR authorized (`SC-057`).

`T116` was written as "byte-identical to `T106`, only the new module added". That is no longer the
truth, and asserting it would fail on changes the owner authorized in writing. What the task
protects is not stillness — it is that **no upstream file changed without a decision naming it**.

So the invariant is stated as an allowlist. It holds `112` upstream paths — `30` added and `82`
modified — each carrying the decision that authorized it, and **any** path outside it is a failure
regardless of how reasonable it looks.

**This count moved four times on 2026-08-26 and the sequence is worth recording**: 25 to 26 when
a D-1 signature added a path, back to 25 when the owner reverted it, to 30 when the minimum path
over the new view made five of `001`'s count assertions false, and to 32 when his two authorized
signatures falsified two more. **Not one of those numbers was written from memory** — every time,
the assertion below is what produced it, which is the difference between a count that is checked
and a count that happens to be right today.

**And the last seven are the shape this file exists to make visible.** They are not seven
decisions. Declaring a seventh source makes `len(sources) == 6` false, and there is no way to
declare it and leave the sentence true; signing an approval makes "the registry is empty" false,
and authoring a formula makes "every governed document is empty" false. Each is the *consequence*
of one authorized act, each amends a COUNT or a SHAPE and leaves the PROPERTY alone -- `001` still
asserts that nothing at all is publishable, and it passes, because the signature moved the SOURCE
and the metric is still `PENDING` for a reason of its own.

Those three numbers are **asserted**, by
:func:`test_the_docstring_counts_match_the_allowlist`, and the sentence carries no ordinal on
purpose. This paragraph has been wrong twice — it said "three upstream paths" and "a fourth path"
long after ADR 0029 had grown the list, and the `why` field below said "a fourth set" when it was
the fifth. Both were prose nobody could check. A hand-written count in a file whose whole argument
is *"prose was the only place that claim lived"* is the same defect the file exists to refuse, so
the count either fails loudly or is not written down. An ordinal — "a fourth path", "a tenth path" —
cannot be asserted against anything, so it is replaced by the property it was gesturing at: outside
the allowlist fails, however many are inside.

## Why `git` rather than stored hashes

A hash table in this repository would be a second baseline to keep current, and the first time it
drifted the test would be asserting against a stale copy of history — the `T106` fixture already
records that it was captured with an unclean tree, which is exactly that class of problem. `git`
answers the question from the history itself.

The comparison is against `captured_at_commit` in `upstream_node_ids.json`, so the node-ID baseline
and this assertion share one reference point. CI checks out with `fetch-depth: 0`, so the commit is
reachable; if it ever is not, the failure says so rather than passing vacuously.

## What this does not assert

Not that the changes are *good*, and not that the ADRs were correctly reasoned. It asserts that each
change is **named** by an accepted decision. Review finding M is why: a handoff claimed zero
upstream files were modified while `001`'s guard had been modified under ADR 0025, and prose was the
only place that claim lived.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


_ROOT = _repository_root()
_BASELINE = (
    _ROOT / "packages" / "channel_integration" / "tests" / "fixtures" / "upstream_node_ids.json"
)
_ADR_DIR = _ROOT / "docs" / "adr"

_UPSTREAM_PACKAGES = (
    "packages/semantic_catalog",
    "packages/analytics_query",
    "packages/analytics_interaction",
)

#: The three counts this module's own docstring claims, read back out of it.
#:
#: Anchored on the words around them rather than on position, and deliberately **required** to
#: match: a reworded paragraph that drops the claim fails here too, which is the difference between
#: a count that is checked and a count that merely happens to be right today. `[^`]*` spans the
#: punctuation between the total and the split so a dash or a comma is not load-bearing.
#: Every gap is `\s+` rather than a literal space: this sentence is wrapped prose, so any of the
#: words can end a line, and a formatter re-wrapping the paragraph must not turn a correct count
#: into a missing claim. The first version of this pattern did exactly that.
_DOCSTRING_COUNTS = re.compile(
    r"It\s+holds\s+`(?P<total>\d+)`\s+upstream\s+paths[^`]*"
    r"`(?P<added>\d+)`\s+added\s+and\s+`(?P<modified>\d+)`\s+modified"
)


@dataclass(frozen=True, slots=True)
class Authorized:
    """One upstream path this feature is permitted to have changed, and by what decision.

    A decision is **either** an accepted ADR or a dated owner instruction, and never both. Most are
    ADRs. The exception exists because one change had no ADR that could honestly name it: amending
    `002`'s scope gate was authorized by the owner directly, and citing ADR 0029 for it would have
    been false — that ADR names `001` paths, and `002`'s own assertion checks that it does.

    Exactly one of `adr` and `instruction` is set. `instruction` carries the date, so a reader can
    find the authorization in the loop's event log rather than taking this file's word for it.
    """

    status: str
    why: str
    adr: str = ""
    instruction: str = ""

    def __post_init__(self) -> None:
        cited = bool(self.adr) + bool(self.instruction)
        if cited != 1:
            raise ValueError(
                "an authorization cites exactly one decision: an ADR filename or an owner "
                f"instruction, not {cited}"
            )


#: The complete allowlist. ``A`` is an addition, ``M`` a modification. A path absent from this table
#: is a failure even if an ADR would plainly have allowed it: the point is that the decision exists
#: **before** the change, and an unlisted change is evidence that it did not.
AUTHORIZED: dict[str, Authorized] = {
    # ciclo 565: o manifesto passa a declarar google-cloud-bigquery, que o pacote importa e o
    # runner nao instalava -- 17 runs vermelhos do catalog.yml no pyright estrito.
    ("packages/semantic_catalog/pyproject.toml"): Authorized(
        status="M",
        instruction="2026-09-06",
        why=(
            "cycle 565: the catalog workflow installs this package ALONE, so a module imported "
            "here and pinned one directory over is absent on the runner; the dev extra gains "
            "google-cloud-bigquery at the pin analytics_query already carries"
        ),
    ),
    # ciclo 565: o no que afirma que este pacote declara o que importa, alcancando import
    # dentro de corpo de funcao -- que e onde o import que quebrou o runner vive.
    (
        "packages/semantic_catalog/tests/contract/test_the_package_declares_what_it_imports.py"
    ): Authorized(
        status="A",
        instruction="2026-09-06",
        why=(
            "cycle 565: the property no local run can see, because the monorepo venv always "
            "held the library; this node walks the syntax tree whole so an import inside a "
            "function body is not read as absent"
        ),
    ),
    # ciclo 565: o no que mantem viva a particao de skips declarada no catalog.yml.
    (
        "packages/semantic_catalog/tests/contract/test_the_declared_skip_partition_is_current.py"
    ): Authorized(
        status="A",
        instruction="2026-09-06",
        why=(
            "cycle 565: the declared no-credential partition named one file and a second began "
            "skipping for the same reason the next day; this node derives the live set from the "
            "source so the partition cannot age a third time"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/contract/test_aggregate_readiness.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/contract/test_baseline_deviation.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/contract/test_d21_carry_forward.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/contract/test_fr_coverage.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/contract/test_readiness.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/contract/test_sc_coverage.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/contract/test_terminal_convergence.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/eval/test_grader_regression.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/integration/test_quickstart_1_4.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/integration/test_quickstart_5_8.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 501 (OD-86): a virada do d_15 acendeu nos do 003; emenda datada, {d_15} exato.
    "packages/analytics_interaction/tests/integration/test_quickstart_9_12.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): aggregate-is-NONE assertions re-anchored to exactly d_15; "
            "no 003 gate opened (available_capabilities stays empty)"
        ),
    ),
    # ciclo 517 (S-33): os nos dos dois sentidos do zero (constroi; -1 recusa).
    "packages/analytics_query/tests/contract/test_foundational_contracts.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "S-33 (cycle 517): the two-direction nodes for the approved zero — threshold=0 "
            "constructs, -1 still refuses ContractViolation"
        ),
    ),
    # ciclo 519: leitores aprendem o d_1.
    "packages/semantic_catalog/src/semantic_catalog/compliance/readiness.py": Authorized(
        status="M",
        instruction="2026-09-03",
        why=(
            "OD-99 (cycle 519): the 001 reader's Capability enum learns d_1 so the record "
            "parses; no gate opens by it. OD-110 (cycle 542, S-41): load_readiness stops "
            "answering for a record that does not say -- entry without declared, "
            "non-boolean declared, unknown key and unparseable YAML now raise instead of "
            "reading as not-declared; no gate opens by it either"
        ),
    ),
    # ciclo 519: leitores aprendem o d_1.
    "packages/analytics_interaction/src/analytics_interaction/compliance/readiness.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "OD-99 (cycle 519): the 003 reader learns the declared_by_role key the 001 "
            "reader requires (mirrors the 004 reader)"
        ),
    ),
    # ciclo 519: leitores aprendem o d_1.
    "packages/semantic_catalog/tests/unit/test_readiness_guard.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "OD-99 (cycle 519): the shipped-record node counts d_1 as the ONE ready; "
            "a second still fails"
        ),
    ),
    # ciclo 542 (OD-106): a semantica deslizante e o mundo declarado novo.
    "packages/semantic_catalog/src/semantic_catalog/validation/l3_reconciliation.py": Authorized(
        status="M",
        instruction="2026-09-03",
        why=(
            "OD-106 (cycle 542): sliding availability semantics — the pair-exists check stays, th"
            "e predates is waived for sliding declarations by design (OD-22)"
        ),
    ),
    # ciclo 545 (D-1303/T1311): a polaridade passa a morar no contrato da metrica; o no que afirma.
    (
        "packages/semantic_catalog/tests/contract/test_the_declared_direction_matches_the_source.py"
    ): Authorized(
        status="A",
        instruction="2026-09-04",
        why=(
            "D-1303 (cycle 545, T1311): metric polarity moved out of the view's own column and "
            "into the metric contract; this node drives the assertion that the direction the "
            "contract declares is the direction the warehouse measures"
        ),
    ),
    # ciclo 542 (S-40): o fail-closed do T101 acendeu ao declarar ext_a; o no que afirma a recusa.
    (
        "packages/semantic_catalog/tests/contract/test_the_fixture_step_asserts_the_refusal.py"
    ): Authorized(
        status="A",
        instruction="2026-09-03",
        why=(
            "OD-106 (cycle 542, S-40): declaring ext_a put three CI steps in exit 1 for the "
            "guard WORKING; this node drives the assertion that the fixture-backed steps "
            "demand the refusal the record is due, and refuses the --mode local repair"
        ),
    ),
    # ciclo 542 (OD-106): a semantica deslizante e o mundo declarado novo.
    "packages/semantic_catalog/tests/unit/test_l3_l4_validation.py": Authorized(
        status="M",
        instruction="2026-09-03",
        why=(
            "OD-106 (cycle 542): the four L3 drive nodes re-derived to the sliding world — predat"
            "es proven in a non-sliding copy AND waived on the real sliding one"
        ),
    ),
    # ciclo 539 (T109/D-12): as condicoes 2-5, engenharia sem declaracao.
    "packages/semantic_catalog/src/semantic_catalog/freshness/warehouse_read.py": Authorized(
        status="A",
        instruction="2026-09-03",
        why=(
            "cycle 539 (T109/D-12): the package's own live read of its two tables through the ded"
            "icated identity — conditions 2/3 machinery; opens no gate (d_12 stays undeclared)"
        ),
    ),
    # ciclo 539 (T109/D-12): as condicoes 2-5, engenharia sem declaracao.
    "packages/semantic_catalog/tests/integration/test_ext_a_readiness_conditions.py": Authorized(
        status="A",
        instruction="2026-09-03",
        why=(
            "cycle 539 (T109/D-12): the three condition nodes with honest skips; condition 4 asse"
            "rts the EXACT measured divergence and goes red the day it clears"
        ),
    ),
    # ciclo 537 (OD-103): o sink operacional do D-13 nasce na 001.
    "packages/semantic_catalog/src/semantic_catalog/provenance/file_archive.py": Authorized(
        status="A",
        instruction="2026-09-03",
        why=(
            "OD-103 (cycle 537): the D-13 operational audit sink — 001 runtime: the real AuditSin"
            "k and the contract-revalidating query; wired to the steward check"
        ),
    ),
    # ciclo 537 (OD-103): o sink operacional do D-13 nasce na 001.
    "packages/semantic_catalog/tests/contract/test_operational_audit_archive.py": Authorized(
        status="A",
        instruction="2026-09-03",
        why=(
            "OD-103 (cycle 537): the sink driven by the PUBLIC CLI path — emission, append, queri"
            "es, tampered-line-by-position, five-key line shape"
        ),
    ),
    # ciclo 533 (OD-104): o vocabulario do D-18 foi autorado pelo dono.
    "packages/analytics_interaction/tests/unit/test_period_governance.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "OD-104 (cycle 533): the shipped vocabulary now holds the eleven decided expressions "
            "with declared conventions — the empty-world nodes re-derived by NAME, seen to fail f"
            "irst"
        ),
    ),
    # ciclo 527 (OD-101): o selo do D-21 nasce e a onda datada passa por aqui.
    "packages/analytics_interaction/README.md": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "OD-101 (cycle 527): the 003 README stops saying aggregate readiness is NONE — d_21 i"
            "s ready by the owner's four clicked decisions and every other lock stays closed; tru"
            "th-of-today over stale prose"
        ),
    ),
    # ciclo 527 (OD-101): o selo do D-21 nasce e a onda datada passa por aqui.
    "packages/analytics_interaction/tests/adversarial/test_seal_tampering.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "OD-101 (cycle 527): the shipped state now verifies THROUGH the injected port; the un"
            "ready copy still refuses before it — amended dated, seen to fail first"
        ),
    ),
    # ciclo 527 (OD-101): o selo do D-21 nasce e a onda datada passa por aqui.
    "packages/analytics_interaction/tests/contract/test_no_readiness_claim.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "OD-101 (cycle 527): d_21 is declared with evidence and a dated note; the other three"
            " entries still say false/None in full — amended dated, seen to fail first"
        ),
    ),
    # ciclo 527 (OD-101): o selo do D-21 nasce e a onda datada passa por aqui.
    "packages/analytics_interaction/tests/integration/test_clarification_zero_calls.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "OD-101 (cycle 527): the shipped readiness now REACHES the injected port (one counted"
            " call); an unready copy keeps zero calls — amended dated, seen to fail"
        ),
    ),
    # ciclo 525 (OD-100): o cofre do D-2.
    "packages/semantic_catalog/src/semantic_catalog/contracts/definition_approval.py": Authorized(
        status="A",
        instruction="2026-09-02",
        why=(
            "OD-100 (cycle 525): the D-2 signature vault contract, in the freshness mold — restat"
            "e + metric_commit + distinct role + public evaluate with named denials"
        ),
    ),
    # ciclo 525 (OD-100): o cofre do D-2.
    "packages/semantic_catalog/src/semantic_catalog/loader/load.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "OD-100 (cycle 525): the loader learns the definition_approvals kind (mapping, single"
            "ton, LoadedCatalog field) so the vault is a governed file, not a stray yaml"
        ),
    ),
    # ciclo 525 (OD-100): o cofre do D-2.
    "packages/semantic_catalog/tests/contract/test_definition_approvals_current.py": Authorized(
        status="A",
        instruction="2026-09-02",
        why=(
            "OD-100 (cycle 525): the currency node — all nineteen evaluate clean at the current c"
            "ommit and every refusal is driven one by one in copies"
        ),
    ),
    # ciclo 519 (OD-99): o no que prende a assinatura de frescor ao commit ATUAL da fonte.
    "packages/semantic_catalog/tests/contract/test_freshness_signature_current.py": Authorized(
        status="A",
        instruction="2026-09-02",
        why=(
            "OD-99 (cycle 519): the freshness signature must cover the CURRENT source "
            "commit (same git command the CLI uses); a stale-commit copy lights up"
        ),
    ),
    # ciclo 517 (S-33): ge=0 — o zero aprovado por OD-97 era irrepresentavel no tipo.
    "packages/analytics_query/src/analytics_query/contracts/policy.py": Authorized(
        status="M",
        instruction="2026-09-02",
        why=(
            "S-33 (cycle 517): minimum_aggregation_threshold gt=0 made the owner-approved "
            "zero unrepresentable; ge=0 with the dated reason, negative still refused"
        ),
    ),
    # ciclo 501 (OD-86): declaracao do d_15 acendeu este no; emenda datada.
    "packages/analytics_query/tests/contract/test_readiness.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): the owner declared d_15 -- the node now holds "
            "ready == {d_15} and the other three closed"
        ),
    ),
    # ciclo 501 (OD-86): declaracao do d_15 acendeu este no; emenda datada.
    "packages/analytics_query/tests/integration/test_fail_closed.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=("cycle 501 (OD-86): lock independence re-anchored to ready == {d_15}"),
    ),
    # ciclo 501 (OD-86): declaracao do d_15 acendeu este no; emenda datada.
    "packages/analytics_query/tests/integration/test_quickstart_scenarios.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "cycle 501 (OD-86): scenario 14 re-anchored (awaiting drops d_15, "
            "limitation phrase kept)"
        ),
    ),
    # ciclo 501 (OD-86): declaracao do d_15 acendeu este no; emenda datada.
    "packages/analytics_query/tests/integration/test_single_metric_query.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=("cycle 501 (OD-86): capabilities_ready == (d_15,), limitation phrase kept"),
    ),
    # ciclo 501 (OD-86): declaracao do d_15 acendeu este no; emenda datada.
    "packages/analytics_query/tests/unit/test_range_limits_and_reporting.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=("cycle 501 (OD-86): awaiting names the three still closed; ready names d_15"),
    ),
    # ciclo 499 (T0, mapa de renames OD-79): o no runner-temp do guarda de node-IDs
    # aprende que o mapa e LIDO (por nome, prefixo workspace) e nunca escrito.
    "packages/analytics_interaction/tests/contract/test_workflow_node_id_guard.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "rename map (cycle 499): the runner-temp node lets the guard READ the versioned "
            "rename map from the workspace and forbids any redirect into it"
        ),
    ),
    # ciclo 495 (catalog v2): a fixture de versao-nao-suportada segue o bump dos 50 yamls.
    "packages/semantic_catalog/tests/unit/test_cli_exit_codes.py": Authorized(
        status="M",
        instruction="2026-09-01",
        why=(
            "catalog v1->2 (cycle 495): the fixture replaced 'catalog_schema_version: 1' "
            "which died with the bump; it now targets ': 2' and asserts the target exists"
        ),
    ),
    # `OD-69`, 2026-08-31: o dono emendou a fronteira do 003 -- a memoria da 011 alcanca o
    # resume PELO contrato (ConversationMemory), nunca por caminho proprio, nunca texto cru.
    # Os guards do 003 foram REESCRITOS para vigiar a regra nova; toda outra persistencia
    # segue proibida.
    "packages/analytics_interaction/src/analytics_interaction/clarification/"
    "future_store.py": Authorized(
        status="M",
        instruction="2026-08-31",
        why=(
            "OD-69: the owner amended 003s boundary so 011s memory reaches resume "
            "through the ConversationMemory contract; the guards were rewritten to "
            "watch the new rule and every other persistence stays forbidden"
        ),
    ),
    "packages/analytics_interaction/src/analytics_interaction/clarification/resume.py": Authorized(
        status="M",
        instruction="2026-08-31",
        why=(
            "OD-69: the owner amended 003s boundary so 011s memory reaches resume "
            "through the ConversationMemory contract; the guards were rewritten to "
            "watch the new rule and every other persistence stays forbidden"
        ),
    ),
    "packages/analytics_interaction/tests/contract/test_no_persistence.py": Authorized(
        status="M",
        instruction="2026-08-31",
        why=(
            "OD-69: the owner amended 003s boundary so 011s memory reaches resume "
            "through the ConversationMemory contract; the guards were rewritten to "
            "watch the new rule and every other persistence stays forbidden"
        ),
    ),
    "packages/analytics_interaction/tests/integration/test_stateless_clarification.py": Authorized(
        status="M",
        instruction="2026-08-31",
        why=(
            "OD-69: the owner amended 003s boundary so 011s memory reaches resume "
            "through the ConversationMemory contract; the guards were rewritten to "
            "watch the new rule and every other persistence stays forbidden. "
            "2026-09-01, OD-73: the memory spy gained the protocols exact signatures "
            "so the strict gate reads it -- behaviour identical, 24 passed"
        ),
    ),
    "packages/analytics_interaction/tests/unit/test_clarification_lifecycle.py": Authorized(
        status="M",
        instruction="2026-08-31",
        why=(
            "OD-69: the owner amended 003s boundary so 011s memory reaches resume "
            "through the ConversationMemory contract; the guards were rewritten to "
            "watch the new rule and every other persistence stays forbidden"
        ),
    ),
    # --- OD-26, 2026-08-30: a assinatura ampla dele, e a `T829` que ela destravou -----------
    #
    # As dezenove metricas entraram no catalogo, e a metade do `FR-806` que faltava era a do
    # CATALOGO: cada contrato declarando a coluna que carrega seu numero. O campo nasce no
    # modelo da `001`, e o `FR-808` obriga `catalog_schema_version` a mover JUNTO com ele.
    # Nenhuma lacuna de negocio foi preenchida: a assinatura autorizou os contratos a
    # existir, e o `D-28` e regra de verdade e nao de permissao.
    "packages/semantic_catalog/src/semantic_catalog/contracts/_base.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "catalog_schema_version moved to 2 because FR-806's field was born; FR-808 requires "
            "the "
            "version to move WITH the field, not after it"
        ),
    ),
    "packages/semantic_catalog/src/semantic_catalog/contracts/classification.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "moveu duas vezes: ADR 0029 classificou `Dimension.access` como AVAILABILITY, e o "
            "OD-26 "
            "acrescentou `kpi_name` e `value_column`, ambos Semantic -- qual linha da view uma "
            "metrica "
            "e, e qual coluna carrega seu numero, mudam o numero"
        ),
    ),
    "packages/semantic_catalog/src/semantic_catalog/contracts/metric.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "value_column and kpi_name declared per metric (FR-806), plus the five money and count "
            "units a KPI in reais could not otherwise state truthfully"
        ),
    ),
    "packages/semantic_catalog/src/semantic_catalog/loader/upgrade.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "the first 1 -> 2 migration, and it deliberately adds NEITHER field: defaulting "
            "value_column to 'value' would re-commit the published error"
        ),
    ),
    "packages/semantic_catalog/tests/contract/test_published_table_consistency.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "re-derived: it asserted a fingerprint count of 29 that classification moves; the "
            "property "
            "is the set, not the number"
        ),
    ),
    "packages/semantic_catalog/tests/integration/"
    "test_authored_catalog_is_fail_closed.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "moveu duas vezes por contagem: seis para sete fontes e onze para doze metricas em "
            "2026-08-26, e agora re-derivado porque a T829 levou a 31 -- a contagem passa a ser "
            "lida do catalogo, e a afirmacao de que NADA e publicavel nunca mudou"
        ),
    ),
    "packages/semantic_catalog/tests/integration/test_projection_leakage.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "moveu duas vezes, e as duas por contagem: de onze para doze em 2026-08-26, e agora "
            "re-derivado porque a T829 levou a 31 -- a propriedade e que a projecao publica cobre "
            "TODA "
            "metrica, e ela nunca dependeu do numero"
        ),
    ),
    "packages/semantic_catalog/tests/unit/test_classification_and_export.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "re-derived: asserted the exported schema version == 1, which FR-808 moved; it reads "
            "the "
            "model's version now"
        ),
    ),
    "packages/semantic_catalog/tests/unit/test_compliance.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "moveu duas vezes: onze para doze em 2026-08-26, e agora re-derivado porque a T829 "
            "levou a "
            "31 -- o conjunto pendente passa a ser comparado com o proprio catalogo"
        ),
    ),
    "packages/semantic_catalog/tests/unit/test_lifecycle_and_bundle.py": Authorized(
        status="M",
        instruction="2026-08-30",
        why=(
            "moveu duas vezes: onze para doze em 2026-08-26, e agora re-derivado porque a T829 "
            "levou a "
            "31 -- e o proprio comentario do no ja dizia que as duas projecoes tem de concordar "
            "QUALQUER "
            "QUE SEJA a contagem"
        ),
    ),
    # --- ADR 0034: two guard repairs inside the ADR 0010 freeze -------------------------------
    #
    # Both defects were IN THE GUARDS rather than in what the package does. This one searched its
    # own source for a literal its own assertion writes, so renaming the constant it watches left
    # it green -- measured, 3 passed. Its sibling, the freeze guard itself, is already authorized
    # under ADR 0016 and needs no second entry.
    "packages/analytics_query/tests/contract/test_adr0010_baseline.py": Authorized(
        status="M",
        adr="0034-two-named-guard-repairs-inside-the-adr-0010-freeze.md",
        why="the presence check reads the module namespace, so the constant has to exist",
    ),
    "packages/analytics_interaction/src/analytics_interaction/interact.py": Authorized(
        status="A",
        adr="0017-interaction-composed-entry-point.md",
        why="the composed entry point ADR 0017 authorized, owned by 003, additive",
    ),
    "packages/analytics_interaction/src/analytics_interaction/segmentation.py": Authorized(
        status="A",
        adr="0027-slot-surface-segmentation.md",
        why="slot-surface segmentation, the element ADR 0017's stop condition surfaced",
    ),
    "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py": Authorized(
        status="M",
        adr="0025-repository-bound-path-citations.md",
        why="the citation guard now decides a path by the repository root rather than by existence",
    ),
    # --- ADR 0029: the dimension disclosure gate, as governed work of `001` --------------------
    #
    # Five paths, and they are not five decisions: `001`'s own gates require all five together. The
    # field alone fails the classification map; the map alone fails the published table; the table
    # alone fails the schema-drift check. A partial application of this ADR does not pass `001`.
    "packages/semantic_catalog/src/semantic_catalog/contracts/dimension.py": Authorized(
        status="M",
        adr="0029-dimension-disclosure-gate.md",
        why="the optional `access` field, absence denying, with no tag authored",
    ),
    "packages/semantic_catalog/src/semantic_catalog/search/concepts.py": Authorized(
        status="A",
        adr="0029-dimension-disclosure-gate.md",
        why="the concept surface: additive, gated, and reporting no dimension while none is tagged",
    ),
    "packages/semantic_catalog/tests/contract/test_concept_disclosure.py": Authorized(
        status="A",
        adr="0029-dimension-disclosure-gate.md",
        why="`001`'s own assertions for the gate: deny-by-default, and a denial indistinguishable "
        "from a non-match. Modified on 2026-08-26 for a second act: `OD-3` authored a seventh "
        "axis, `game`, and the sentinel's own failure message requires a new axis to be "
        "RE-DERIVED here rather than absorbed. One entry added; the whole mapping is still "
        "asserted, so an eighth axis still fails",
    ),
    # --- The two signatures of 2026-08-26, and what they falsified ----------------------------
    #
    # The owner authorized both -- "Autorizar as duas (Recomendado)", governed channel,
    # 17:17:40Z: the D-1 freshness approval of `subscription_daily` and the D-18
    # `percentage_change` formula. Both landed. Both falsified a node that asserted the
    # emptiness they ended.
    #
    # Cited as an **instruction** for the reason every owner entry here gives: no ADR names
    # these paths, and a signature is a business act rather than an architectural one.
    #
    # **Each amendment changes a COUNT or a SHAPE and leaves the PROPERTY alone.** Neither
    # node was loosened: the first still asserts that governed content appears only by an
    # authored act, the second still asserts that the three undecided documents are empty and
    # that the formula set stays CLOSED -- measured, `ratio` and `absolute_difference` are
    # still refused.
    "packages/analytics_interaction/tests/contract/test_fixture_containment.py": Authorized(
        status="M",
        instruction="2026-08-26",
        why="it asserted that all four governed documents are empty, which was the shipped "
        "state and not the rule. One of the four was authored by his decision, so the "
        "property is restated as what it always was: content appears only by an authored "
        "act, and an authored instance carries an approval naming a role and a date. The "
        "other three are still asserted empty, one by one",
    ),
    "packages/analytics_interaction/tests/unit/test_governance_resolution.py": Authorized(
        status="M",
        instruction="2026-08-26",
        why="the same emptiness, asserted through the loaders. Re-derived to assert the one "
        "authored instance names exactly `percentage_change`, so the set stays closed. And "
        "the sibling node that still refuses on an earlier date got the reason written down "
        "-- it passes because of the EFFECTIVITY WINDOW now, not because the file is empty, "
        "and an unexplained pass is how a gate becomes decorative",
    ),
    # --- ADR 0033: a freshness approval binds to content, not to repository state ---------------
    #
    # Accepted 2026-08-26 on his literal words "Ligar ao conteudo (Recomendado)". The four runtime
    # modules are the chain the comparand travels -- the registry that compares it, the eligibility
    # functions that now take it PER SOURCE, the lifecycle derivation that feeds them, and the
    # bundle that receives it from the caller. The two tests are the only ones in `001` that call
    # those functions directly and therefore name the parameter; every other node goes through
    # `build_bundle` and did not move.
    #
    # **The PROPERTY that had to survive did survive, and it is asserted:** binding to content makes
    # a SOURCE publishable and publishes NO METRIC. Measured after the change -- 12 of 12 metrics
    # still PENDING, `new_trials` included, because it declares no `source_availability` at all.
    "packages/semantic_catalog/src/semantic_catalog/contracts/freshness_approval.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="the comparand: `source_content_commit`, the commit that last touched the approved "
        "source's own file, replacing the caller's publishing commit. Renamed rather than "
        "reused, because the old name is what made the promise and the implementation disagree. "
        "The prefix comparison is stated in its own helper, in the safe direction",
    ),
    "packages/semantic_catalog/src/semantic_catalog/validation/publication.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="a commit PER SOURCE. One shared commit could not say 'this source's content is "
        "unchanged' for seven sources, and a source absent from the mapping is denied",
    ),
    "packages/semantic_catalog/src/semantic_catalog/loader/lifecycle.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="its `current_commit` only ever fed the freshness check, so it became "
        "`source_commits` rather than gaining a second parameter beside a misleading one",
    ),
    "packages/semantic_catalog/src/semantic_catalog/loader/bundle.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="the caller's entry point. `current_commit` stays for the VISIBILITY registry, which "
        "legitimately wants the publishing commit; `source_commits` is new and feeds freshness. "
        "Its absence falls back to the old comparand -- a DECLARED TRANSITION, named in the "
        "docstring with the measurement behind it: a hard cutover fails 142 nodes across fifteen "
        "files, all of them fixture catalogs that are not in Git at all",
    ),
    "packages/semantic_catalog/tests/unit/test_freshness_approval.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="it calls the registry and `source_eligibility` directly, so it names the comparand. "
        "Keyword renames only; not one assertion changed",
    ),
    "packages/semantic_catalog/tests/unit/test_retention_pending.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="it calls `derive_lifecycles` directly. One call site, given the same commit for "
        "every source, which is what it always meant by one commit",
    ),
    # --- ADR 0033, second half: the CALLER, and the nodes that left the fallback ---------------
    #
    # The first attempt at wiring the caller was ESCALATED rather than forced; the reviewer
    # answered with a cheaper path that touches no contract -- the CLI states the mapping with a
    # repeatable `--source-commit id=sha` and resolves the rest from Git, and the fixtures state
    # their own invented commit on purpose. ADR 0033 already put commit resolution on the caller,
    # so nothing was widened to make this pass.
    #
    # The converted test nodes each state the SAME commit they always stated, per source instead
    # of inherited -- a no-op by construction, and the suite outcome is unchanged at 1899.
    "packages/semantic_catalog/src/semantic_catalog/cli/main.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="the caller. `--source-commit` states a content commit per source and Git answers "
        "for the rest, with explicit beating resolved -- only the caller knows whether a "
        "catalog is versioned at all. A source with uncommitted changes is OMITTED and "
        "omission denies, because its content is not any commit",
    ),
    "packages/semantic_catalog/tests/unit/test_cli.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="the three nodes that validate the fixture catalog now state "
        "`fixture_source=fixture0`, which is what the fixture's own approval names. The "
        "binding is satisfied honestly instead of being weakened to let a fixture through",
    ),
    "packages/semantic_catalog/tests/integration/test_adversarial.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback: states app_a and store_a per source",
    ),
    "packages/semantic_catalog/tests/integration/test_audit_emission.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback: states app_a and store_a per source",
    ),
    "packages/semantic_catalog/tests/integration/test_no_auto_degradation.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback: states app_a and store_a per source",
    ),
    "packages/semantic_catalog/tests/integration/test_provenance_statement.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback: states app_a and store_a per source",
    ),
    "packages/semantic_catalog/tests/integration/test_unsafe_combinations.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback: states app_a and store_a per source",
    ),
    "packages/semantic_catalog/tests/unit/test_coverage_freshness_independence.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback: states app_a and store_a per source",
    ),
    "packages/semantic_catalog/tests/unit/test_freshness_and_coverage.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback: states app_a and store_a per source",
    ),
    "packages/semantic_catalog/tests/unit/test_matrix_and_pipeline.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback on both roots: the fixture and the production tree",
    ),
    "packages/semantic_catalog/tests/unit/test_fail_closed.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback on the production tree it walks",
    ),
    "packages/semantic_catalog/tests/unit/test_search.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback: states subscription_daily per source",
    ),
    "packages/semantic_catalog/tests/integration/test_decision_matrix.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback, and it is one of the seven that ACTUALLY exercised the "
        "comparand -- its FIXTURES constant already points at the fixture directory, so "
        "its catalog carries an approval naming the very commit it passes",
    ),
    "packages/semantic_catalog/tests/integration/test_deprecation_boundaries.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback, and it is one of the seven that ACTUALLY exercised the "
        "comparand -- its FIXTURES constant already points at the fixture directory, so "
        "its catalog carries an approval naming the very commit it passes",
    ),
    "packages/semantic_catalog/tests/integration/test_release_lifecycle.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback, and it is one of the seven that ACTUALLY exercised the "
        "comparand -- its FIXTURES constant already points at the fixture directory, so "
        "its catalog carries an approval naming the very commit it passes",
    ),
    "packages/semantic_catalog/tests/unit/test_as_of_stability.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback, and it is one of the seven that ACTUALLY exercised the "
        "comparand -- its FIXTURES constant already points at the fixture directory, so "
        "its catalog carries an approval naming the very commit it passes",
    ),
    "packages/semantic_catalog/tests/integration/test_comparable_window_publication.py": Authorized(
        status="M",
        adr="0033-freshness-approval-binds-to-content.md",
        why="off the fallback, one of the seven that actually exercised the comparand",
    ),
    "packages/analytics_interaction/tests/contract/test_interact_contract.py": Authorized(
        status="A",
        adr="0017-interaction-composed-entry-point.md",
        why="`T109`: the entry point adds no reason code, no audit stage and no answer field",
    ),
    # --- T110 to T113: the entry point's own validation families -------------------------------
    #
    # Four new test modules under `003`, added 2026-08-19 on the owner's authorization of the D0
    # scope. They are `A` rather than `M`: no existing `003` test is touched, which is what keeps
    # ADR 0017's additive limit intact while the entry point gains the suites its own task list
    # names.
    #
    # Cited as an **instruction** and not as an ADR, for the reason the entry beside `002`'s scope
    # gate gives: ADR 0017 authorized the module, not these four files, and claiming it named them
    # would be the drift this allowlist exists to catch.
    "packages/analytics_interaction/tests/integration/test_interact_equivalence.py": Authorized(
        status="A",
        instruction="2026-08-19",
        why="`T110`: each refusal `ask` surfaces is compared with the single component that owns "
        "it, by type, code and detail byte for byte — never by re-composing the sixteen steps, "
        "which would be the second interpretation path `T115` proves absent",
    ),
    # Both modules below had their docstrings corrected on 2026-08-20 under the F12 instruction:
    # each described step 7 as comparing the whole question by exact equality, which stopped being
    # true. The paths were already authorized as additions, and `Authorized` cites exactly one
    # decision, so this is recorded here rather than by overwriting the 2026-08-19 citation.
    "packages/analytics_interaction/tests/integration/test_interact_boundaries.py": Authorized(
        status="A",
        instruction="2026-08-19",
        why="`T111`: every reachable refusal happens at its required step, asserted by isolation "
        "and by precedence — an input violating two steps must refuse with the earlier one — plus "
        "step 2's six cost surfaces counted at zero",
    ),
    "packages/analytics_interaction/tests/adversarial/test_interact_adversarial.py": Authorized(
        status="A",
        instruction="2026-08-19",
        why="`T112`: injection at five placements, enumeration probing with byte-identical "
        "answers, tag escalation refused at step 2, fabricated intake fields including a fixture "
        "flag, and six environment switches proven inert",
    ),
    "packages/analytics_interaction/tests/property/test_interact_determinism.py": Authorized(
        status="A",
        instruction="2026-08-19",
        why="`T113`: one input one outcome, across ten repetitions and across subprocesses run "
        "under three different hash seeds, with the sensitivity direction asserted so stability "
        "over an ignored input cannot pass",
    ),
    # --- Option A: the owner's amendment of `002`'s scope gate ---------------------------------
    #
    # `002`'s prohibition on approved artifacts was absolute, and ADR 0029's execution needed two of
    # them. The owner chose Option A on 2026-08-19 — amend the gate with a named, disjoint exception
    # rather than skip the artifacts or revert the ADR.
    #
    # Cited as an **instruction** and not as an ADR on purpose. No ADR names this path: ADR 0029
    # names `001` paths, and `002`'s own assertion that ADR 0029 names its own paths would catch the
    # lie if this claimed otherwise.
    # --- F12: the period expression is located inside the question ----------------------------
    #
    # The owner authorized "uma correcao restrita do finding F12" on 2026-08-20, recorded verbatim
    # in the loop's event log. Step 7 used to hand the *whole question* to
    # `resolve_governed_period`, which compares by exact equality, so no input could satisfy both
    # halves of an analytical question. The correction searches the question for the expression it
    # contains, over the same spans step 6 already resolves terms across.
    #
    # Cited as an **instruction** and not as an ADR, for the reason the two entries below give: no
    # ADR names these paths. ADR 0029 names `001` paths and ADR 0017 authorized the composed entry
    # point, not an edit to `003`'s period resolver.
    #
    # The owner wrote "no nucleo da Feature 004". F12 is not in `004`: the wall is `period.py` and
    # its caller in `interact.py`, both owned by `003`. The REVIEWER measured that before opening
    # the scope and interpreted the order by its substance rather than by the feature number, which
    # is why these are `003` paths.
    "packages/analytics_interaction/src/analytics_interaction/interpretation/period.py": Authorized(
        status="M",
        instruction="2026-08-20",
        why="`F12`: `locate_expression` finds the governed expression a question contains, reusing "
        "`segmentation.segment` so token alignment and punctuation handling are inherited rather "
        "than re-implemented; `normalise_surface` declares one normalisation for case, accents and "
        "spacing, applied to both sides of every comparison; more than one distinct expression "
        "refuses `INTENT_AMBIGUOUS` rather than choosing. `resolve_expression`'s exact-match "
        "contract is untouched, and no date arithmetic was added — `R-8` keeps that in `001`",
    ),
    "packages/analytics_interaction/src/analytics_interaction/interpretation"
    "/__init__.py": Authorized(
        status="M",
        instruction="2026-08-20",
        why="`F12`: re-exports the two new period functions beside the three that were already "
        "public, so the package surface stays one list rather than two",
    ),
    "packages/analytics_interaction/tests/unit/test_period_in_question.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="`F12`'s evidence: the expression found inside a full question, token boundaries "
        "holding against `julhoxyz`, the four spellings the owner's item 6 names, both sides of "
        "the comparison normalised, two periods refusing rather than choosing, an absent period "
        "and an empty vocabulary still refusing, and no refusal carrying any part of the question",
    ),
    # The owner authorized closing "AS DUAS PAREDES ESTRUTURAIS, construcao de claims e resolucao
    # governada de intervalo" on 2026-08-20, in his words a "CORRECAO NECESSARIA PARA A DEMONSTRACAO
    # LOCAL, NAO nova feature e NAO ativacao produtiva". Items A and B of that instruction required
    # searching for existing ports and contracts before creating anything, and required any new port
    # to be provider-neutral, mandatory, and to delegate the calendar to `001`. These are the paths
    # that required, and the reason each one is here rather than avoided.
    "packages/analytics_interaction/src/analytics_interaction/contracts/intent.py": Authorized(
        status="M",
        instruction="2026-08-20",
        why="Item B: adds `GovernedInterval`, the typed interval a boundary resolver returns — "
        "start, end, time zone and inclusivity in one value instead of three owners assembling "
        "them by hand. No existing contract carried the four together, measured before adding: "
        "`ResolvedPeriod` has no zone, `PeriodExpression` has no dates, and `001`'s "
        "`CanonicalPeriod` has no inclusivity. Nothing existing was changed",
    ),
    "packages/analytics_interaction/src/analytics_interaction/interpretation"
    "/boundary_port.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="Item B: `PeriodBoundaryResolverPort`, provider-neutral and with no implementation in "
        "`src/` — a calendar there would be this feature deciding a reporting standard, the same "
        "reason `RedactionMatcher` ships none. It computes no dates and resolves no zone: `001` "
        "keeps both under `R-8`, which is what the instruction's "
        '"NENHUMA ARITMETICA NAO AUTORIZADA ESCONDIDA EM INTERACT.PY" required',
    ),
    "packages/analytics_interaction/src/analytics_interaction/answer/claims_port.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="Item A: `ClaimConstructionPort` plus `assert_claims_are_authorised`. It produces the "
        "existing `AnswerClaim` and no new type, because the contract already existed — seven "
        "fields, four classes, measured before adding. The question text is absent from the "
        "signature, and the guard refuses any subject the plan did not authorise and the result "
        'did not label, which is what makes "nunca interpretar texto livre do usuario" '
        "structurally observable rather than a rule",
    ),
    "packages/analytics_interaction/tests/unit/test_period_boundaries.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="Item B's evidence: the full 2026-07-01 to 2026-07-31 range reaching the resolved "
        "period; a resolver answering in another zone refusing; a resolver restating the `D-18` "
        "inclusivity refusing; an unordered interval refusing; an unknown boundary rule carried as "
        "the resolver's own refusal; and an empty vocabulary still refusing before the resolver is "
        "ever consulted",
    ),
    "packages/analytics_interaction/tests/unit/test_claim_construction.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="Item A's evidence: an authorised metric, an authorised dimension and a label the "
        "result carried all accepted; a fabricated subject, a span of a question and a unit no "
        "column declared all refusing `IDENTIFIER_FABRICATED`; one bad claim among good ones "
        "refusing the whole tuple; and the allowlist proven to be read off the plan and the result "
        "rather than supplied",
    ),
    # The owner's master authorization of 2026-08-20 for trials, purchases, BigQuery and flexible
    # periods. It requires a deterministic temporal resolver and a deterministic comparison, and it
    # forbids the model computing either. `R-8` puts date arithmetic in `001`, which is why the
    # resolver is there and not in `003`.
    "packages/semantic_catalog/src/semantic_catalog/periods/temporal.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="The deterministic temporal resolver: `TemporalIntent` in, `ResolvedWindow` out, clock "
        "injected. It lives in `001` because `R-8` puts date arithmetic and IANA resolution here "
        "and `CANONICAL_TIMEZONE` is declared here once. Every bound comes from calendar "
        "arithmetic — `add_months` clamps, so 31 January plus a month is 28 or 29 February and "
        "never 3 March — and no constant stands in for a month or a year. Ambiguity refuses: a "
        "month with no year, an unknown rule, an inverted range and a naive reference instant all "
        "raise rather than resolve",
    ),
    "packages/semantic_catalog/tests/unit/test_temporal_resolution.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="The thirty-nine temporal cases the authorization lists, with the clock injected and "
        "every expected date written as a literal derived by hand from one reference instant — "
        "deriving it with the code's own arithmetic would assert that the code agrees with itself. "
        "Includes the turns of day, week, month and year, February in a common and a leap year, "
        "and the case a `timedelta` implementation gets wrong",
    ),
    "packages/analytics_interaction/src/analytics_interaction/comparison/direction.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="The one piece the comparison arithmetic did not have: the **word**. Measured before "
        "writing it — `compute.py` already owns absolute difference, ratio and percentage change "
        "in a closed `MappingProxyType` over `Decimal` with `float` refused, and `formula.py` "
        "already applies the governed zero-baseline rule to the dividing operations only. Nothing "
        "there was rewritten. `classify_direction` reads a signed difference as increase, decrease "
        "or stable, with the stability band explicit and symmetric",
    ),
    "packages/analytics_interaction/tests/unit/test_comparison_direction.py": Authorized(
        status="A",
        instruction="2026-08-20",
        why="The direction reading, including the case that would catch a reversed sign "
        "convention: the difference is taken from `compute.OPERATIONS` rather than restated, so a "
        "flip on either side would make growth read as a fall",
    ),
    "packages/analytics_query/tests/contract/test_adr0010_scope.py": Authorized(
        status="M",
        instruction="2026-08-19",
        why="Option A: a third authorization set for ADR 0029's four `001` paths, and a named "
        "two-path exception to the approved-artifact prohibition, with a planted-path assertion "
        "proving it stays an allowlist. Amended again the same day, by the owner's second choice: "
        "a fifth set naming the seven governed-content paths under `semantic/` that tagging the "
        "six authored dimensions required, bounded at seven by its own assertion, held to ADR "
        "0029's execution note, and with a third planted path proving `semantic/` stays an "
        "allowlist rather than an opening. The two-path exception is unchanged and still asserted "
        "to be exactly two. Amended a third time on 2026-08-26: the prose counts of sets and "
        "of admitted paths were removed rather than incremented, because both had aged -- the "
        "F136 class. A seventh authorization set was added the same day for the D-1 signature "
        "and removed again when the owner reverted it; the count removal stayed, which is the "
        "argument for taking numbers out of prose. Amended a fourth time on 2026-08-26: a "
        "SIXTH set, `OWNER_DECISIONS_2026_08_26`, holding the ONE path his four decisions "
        "of that day create that the prohibition did not already admit -- `dimensions/game.yaml`. "
        "The other three decisions amend four dimension files already admitted BY PATH by the "
        "fifth set, for a different act, and repeating them here would break the pairwise-disjoint "
        "assertion that keeps each authorization readable on its own. Amended a fifth time on "
        "2026-09-01 (cycle 501, OD-86): an EIGHTH pierced set, OWNER_D15_DECLARATION_2026_09_01, "
        "holding the one readiness-record path the owner's declaration writes, plus the named "
        "surface OD_86_AMENDED_NODES_SURFACE of the five content nodes the flip lit, held to the "
        "declaration itself by a companion check",
    ),
    # --- The minimum path: one source, one metric, and the counts it falsified -----------------
    #
    # The owner ordered the `semantic` dataset and the view created on 2026-08-26, then ordered the
    # bot migrated to read only the view. Declaring the seventh source made five of `001`'s count
    # assertions false, and there is no way to declare it and leave them true -- so the five are
    # amended here as the consequence of the authorized act rather than as a second decision.
    #
    # Cited as an **instruction** for the reason every entry above gives: no ADR names these paths,
    # and D-1 plus the view are business acts rather than architectural ones.
    #
    # **Each amendment changes a COUNT and leaves the PROPERTY alone.** `001` still asserts that
    # nothing at all is publishable, and still walks every source rather than a subset -- measured:
    # its suite passes with seven sources and twelve metrics, none of them publishable.
    "packages/semantic_catalog/tests/contract/test_baseline_reconciliation.py": Authorized(
        status="M",
        instruction="2026-08-26",
        why="six sources became seven; BD-5 asks that every authored source be GOVERNED and the "
        "seventh is -- owner, review group, and no approval, which is what "
        "governed-and-unpublishable looks like",
    ),
    # --- 2026-08-27: the two paths a WIDENED PUSH GATE found, and finding them is the point -----
    #
    # This node was red at HEAD and nobody knew, because the push hook named ONE package by hand
    # and never ran this suite on the branches doing the work. The hook now derives which packages
    # it gates; its first run reported these two. **The gate going red the first time it looks is
    # the gate working**, and the answer is to name what was authorized -- never to widen a pattern
    # so the red goes away.
    "packages/semantic_catalog/src/semantic_catalog/compliance/leakage_scan.py": Authorized(
        status="M",
        instruction="2026-08-27",
        why="the draft-definition scan answered correctly only while NOTHING was publishable: it "
        "looked for draft field names anywhere in the public bundle whenever any metric was "
        "pending, so the first metric to reach `published` had its own legitimate definition "
        "reported as a leak. The check is now per pending metric, against that metric's own "
        "entry, and stricter -- anything beyond the six-field stub is a leak whether or not its "
        "name was ever listed",
    ),
    "packages/semantic_catalog/tests/fixtures/coverage/observed.yaml": Authorized(
        status="M",
        instruction="2026-08-27",
        why="one row, for the pair `new_trials` on `subscription_daily`, written to match the "
        "warehouse rather than to make a test pass. It is the only row in that file that is not "
        "invented: `semantic.metric_availability` was created on his word and holds exactly this "
        "pair with these dates, computed by MIN and MAX over the view INSIDE the insert",
    ),
    "packages/semantic_catalog/tests/unit/"
    "test_a_signed_definition_that_changed_is_refused.py": Authorized(
        status="A",
        instruction="2026-09-04",
        why="OD-124 (c): the OD-100 vault had nineteen signatures and zero readers on the "
        "production path. `derive_lifecycles` now consults it, and a rewritten signed definition "
        "becomes PENDING with the denial NAMED. Eight nodes, every fixture written with approved "
        "and current sentences that DIFFER; the commit half is declared not measured here",
    ),
}


def _baseline_commit() -> str:
    document = json.loads(_BASELINE.read_text(encoding="utf-8"))
    commit = document["captured_at_commit"]
    assert isinstance(commit, str) and len(commit) == 40, f"malformed baseline commit {commit!r}"
    return commit


def _git(*arguments: str) -> str:
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - git absent
        raise AssertionError(
            "git is not available, so this assertion cannot be evaluated. It is not vacuously "
            "true: run the suite in a git checkout."
        ) from exc
    assert completed.returncode == 0, (
        f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
    )
    return completed.stdout


def _changed_upstream_paths() -> dict[str, str]:
    """``path -> status`` for every upstream path differing from the baseline commit.

    Includes the working tree, not only committed history: an uncommitted upstream edit is exactly
    the kind this assertion exists to notice, and comparing commit-to-commit would miss it until
    push.
    """
    changed: dict[str, str] = {}

    raw = _git("diff", "--name-status", _baseline_commit(), "--", *_UPSTREAM_PACKAGES)
    for line in raw.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        changed[path.strip().replace("\\", "/")] = status.strip()[:1]

    #: Untracked files too, and this closes a real gap in this gate rather than refining it. `git
    #: diff` compares commits and an index, so a **new** upstream file that was never staged is
    #: invisible to it — the allowlist's own stale-entry assertion caught that, by reporting three
    #: authorized new files as "no longer differing" when they had never been seen at all. An
    #: unauthorized new upstream module is exactly what this gate exists to notice.
    for line in _git("status", "--porcelain", "--", *_UPSTREAM_PACKAGES).splitlines():
        if not line.startswith("??"):
            continue
        path = line[2:].strip().replace("\\", "/")
        changed.setdefault(path, "A")

    return changed


def test_the_baseline_commit_is_reachable() -> None:
    """Without this, every assertion below would compare against nothing."""
    commit = _baseline_commit()
    kind = _git("cat-file", "-t", commit).strip()
    assert kind == "commit", f"{commit} is a {kind}, not a commit"


def test_every_changed_upstream_path_is_authorized() -> None:
    """The assertion itself: no upstream file changed without a decision naming it."""
    changed = _changed_upstream_paths()
    unauthorized = sorted(set(changed) - set(AUTHORIZED))
    assert not unauthorized, (
        f"upstream paths changed with no authorizing decision: {unauthorized}. Either an ADR names "
        "the change and this allowlist must record it, or the change must be reverted — ADR 0017 "
        "§ Acceptance permits additive work only, and 'plainly harmless' is not an authorization."
    )


def test_each_authorized_path_changed_in_the_way_its_decision_permits() -> None:
    """An addition that became a modification is a different decision.

    ADR 0017's limit is *additive*: a new module. If `interact.py` were later recorded as `M`
    against a pre-existing file, the allowlist entry would be describing something that no longer
    matches.
    """
    changed = _changed_upstream_paths()
    mismatched = {
        path: (status, AUTHORIZED[path].status)
        for path, status in changed.items()
        if path in AUTHORIZED and status != AUTHORIZED[path].status
    }
    assert not mismatched, f"actual versus authorized change kind: {mismatched}"


def test_the_allowlist_carries_no_stale_entry() -> None:
    """A path that no longer differs must leave the list.

    Otherwise the allowlist grows into a record of everything ever permitted, and its size stops
    saying anything about what this feature actually touched.
    """
    changed = _changed_upstream_paths()
    stale = sorted(set(AUTHORIZED) - set(changed))
    assert not stale, f"allowlist entries that no longer differ from the baseline: {stale}"


def test_the_docstring_counts_match_the_allowlist() -> None:
    """The count in this module's prose is derived from the list, or it fails.

    Added 2026-08-19, on the reviewer's requirement that the count stop being derivable by hand. It
    had been wrong twice by then: the opening paragraph said "three upstream paths" and "a fourth
    path" while `AUTHORIZED` held nine, and the `why` field of one entry said "a fourth set" when it
    was the fifth. Neither was caught by anything, because a sentence is not an assertion.

    This is the assertion. Three claims, each read back out of `__doc__` and compared with the list
    itself:

    * the **total**, against `len(AUTHORIZED)`;
    * the count of **additions**, against the entries whose status is ``A``;
    * the count of **modifications**, against the entries whose status is ``M``.

    **The match is required, not optional.** A paragraph reworded to drop the claim fails here as
    loudly as a wrong number, which is what stops the next authorization from quietly restoring the
    original defect by deleting the sentence instead of updating it.

    What this deliberately does **not** do is police prose generally. It reads one anchored
    sentence. The `zero` in "a handoff claimed zero upstream files were modified" further down is a
    quotation about a past claim rather than a count of this list, and a scan broad enough to catch
    it would fail on every ADR number in the file.
    """
    assert __doc__ is not None, "this module has no docstring to check"
    claimed = _DOCSTRING_COUNTS.search(__doc__)
    assert claimed is not None, (
        "the module docstring no longer states the allowlist counts in the asserted form "
        '("It holds `N` upstream paths ... `N` added and `N` modified"). Restate them rather than '
        "removing the claim: an unstated count is how this paragraph went stale twice"
    )

    statuses = [entry.status for entry in AUTHORIZED.values()]
    measured = {
        "total": len(AUTHORIZED),
        "added": statuses.count("A"),
        "modified": statuses.count("M"),
    }
    stated = {name: int(claimed.group(name)) for name in measured}

    assert stated == measured, (
        f"the docstring claims {stated} and the allowlist holds {measured}. Update the paragraph; "
        "the list is the source of truth and the sentence is the copy"
    )

    #: Anti-vacuity. If the statuses were ever something other than `A` and `M`, the two sub-counts
    #: could agree with the prose while summing to less than the total, and the assertion above
    #: would pass over a list it had only partly described.
    assert measured["added"] + measured["modified"] == measured["total"], (
        f"{sorted(set(statuses))} are not only 'A' and 'M', so the split does not cover the list"
    )


def test_every_cited_decision_exists_and_is_accepted() -> None:
    """A citation to a missing or proposed ADR authorizes nothing.

    Scoped to the ADR-cited entries. Instruction-cited entries are checked by the assertion below,
    which is a different check because an instruction is not a file in this repository.
    """
    problems: list[str] = []
    for path, entry in sorted(AUTHORIZED.items()):
        if not entry.adr:
            continue
        adr = _ADR_DIR / entry.adr
        if not adr.is_file():
            problems.append(f"{path}: {entry.adr} does not exist")
            continue
        text = adr.read_text(encoding="utf-8")
        if "**Status**: **Accepted**" not in text:
            problems.append(f"{path}: {entry.adr} is not Accepted")
    assert not problems, problems


def test_every_authorization_cites_exactly_one_decision() -> None:
    """An ADR or an instruction, never both and never neither.

    `Authorized.__post_init__` refuses at construction, so this cannot fail while the module imports
    — which is the point: the invariant is enforced where the entry is written, and asserted here so
    a reader sees it stated rather than having to find the constructor.
    """
    for path, entry in sorted(AUTHORIZED.items()):
        assert bool(entry.adr) != bool(entry.instruction), path


def test_every_instruction_cited_entry_carries_a_date_and_a_reason() -> None:
    """An instruction is not a file, so what makes it checkable is the date and the reason.

    A dated instruction can be found in the loop's event log. An undated one is a claim that
    somebody said something, which is exactly the shape of an authorization nobody can verify.
    """
    instruction_cited = {path: entry for path, entry in AUTHORIZED.items() if entry.instruction}
    #: Not asserted to be non-empty. If a future cycle reverts the amendment this set becomes empty
    #: and that is correct — an empty set of instruction-cited authorizations is the normal state.
    for path, entry in sorted(instruction_cited.items()):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.instruction), (
            f"{path} cites {entry.instruction!r}, which is not a date"
        )
        assert len(entry.why) > 40, f"{path} cites an instruction with a thin reason"


def test_no_runtime_source_of_002_changed_and_001_changes_only_where_named() -> None:
    """The stronger claim, re-derived a second time rather than weakened.

    It used to read "no runtime source of `001` or `002` moved". ADR 0029 made that false,
    because a disclosure gate cannot live in a test, so it was split: `002` absolutely untouched,
    and `001` only at paths that ADR names.

    **On 2026-08-20 it failed again**, and correctly: the owner's master authorization for trials,
    purchases and flexible periods requires a deterministic temporal resolver, and `R-8` puts
    date arithmetic in `001`. So `periods/temporal.py` is `001` runtime code authorized by a
    **dated owner instruction** rather than by an ADR — the exact case `Authorized` already
    models, and the case the previous version's own message asked for: "it needs its own
    re-derivation here rather than
    passing quietly".

    This is that re-derivation, and it keeps the strength rather than trading it away:

    * `002`'s runtime source is untouched, **absolutely**. Unchanged.
    * every changed `001` runtime path is in the allowlist. Unchanged.
    * each one is authorized **either** by ADR 0029 **or** by a dated owner instruction, and by
      nothing else. An ADR that is not 0029 still fails, which is what stops an unrelated ADR from
      being cited as cover.

    What is deliberately **not** weakened: the set of acceptable decisions is still closed and still
    NAMED — three members since 2026-08-26, when ADR 0033 became the second ADR to authorize `001`
    runtime. Three named decisions is not "any authorization"; a fourth ADR still fails.
    Widening it to "any authorization" would make this test pass for anything in the
    allowlist, which is what `test_every_changed_upstream_path_is_authorized` already
    checks — and a second copy of that check is not this test's job.
    """
    changed = _changed_upstream_paths()

    # RE-DERIVADO em 2026-09-02 (ciclo 517, S-33), pela terceira vez e pelo mesmo molde do
    # temporal.py acima: "002 absolutamente intocado" era verdade ate o dia em que a palavra
    # do dono (OD-97, limiar zero) exigiu que o CONTRATO do QueryPolicy o representasse —
    # ge=0 em contracts/policy.py. A forca que fica: todo caminho de runtime da 002 mudado
    # exige entrada em AUTHORIZED com instrucao DATADA; um caminho sem entrada segue
    # falhando aqui, e a entrada sem instrucao tambem.
    runtime_002 = sorted(
        path for path in changed if path.startswith("packages/analytics_query/src/")
    )
    unnamed_002 = [
        path
        for path in runtime_002
        if AUTHORIZED.get(path) is None or not AUTHORIZED[path].instruction
    ]
    assert not unnamed_002, f"runtime source of 002 changed: {unnamed_002}"

    runtime_001 = sorted(
        path for path in changed if path.startswith("packages/semantic_catalog/src/")
    )

    unnamed_001 = [path for path in runtime_001 if AUTHORIZED.get(path) is None]
    assert not unnamed_001, f"001 runtime source changed with no decision naming it: {unnamed_001}"

    wrong_decision = [
        path
        for path in runtime_001
        if AUTHORIZED[path].adr
        not in {
            "",
            "0029-dimension-disclosure-gate.md",
            # Added 2026-08-26. THREE named members, still closed: an ADR that is not one of
            # these still fails, which is what stops an unrelated ADR from being cited as cover.
            # Widening to "any authorization" is what the docstring above refuses, and this is
            # not that -- it is one more decision, named, that actually authorized 001 runtime.
            "0033-freshness-approval-binds-to-content.md",
        }
    ]
    assert not wrong_decision, (
        f"001 runtime source changed citing an ADR other than 0029: {wrong_decision}. Only ADR "
        "0029 and a dated owner instruction authorize a change here, and an unrelated ADR is not "
        "cover"
    )

    #: Instruction-cited `001` runtime paths are permitted and **named**, so a reader sees which
    #: ones they are rather than discovering that the assertion has a second branch.
    #:
    #: **TWO members since 2026-08-27**, and the second is stated rather than absorbed, exactly as
    #: this assertion's own message demanded. `compliance/leakage_scan.py` is `001` runtime that a
    #: WIDENED PUSH GATE found red at HEAD: its draft-definition scan answered correctly only while
    #: nothing was publishable, and the first metric to reach `published` had its own legitimate
    #: definition reported as a leak. The fix is stricter than what it replaced -- per pending
    #: metric, against that metric's own entry, refusing anything beyond the stub.
    #:
    #: The set stays CLOSED. A third path still fails here, which is the difference between naming
    #: a decision and widening a rule.
    #: **SIX since 2026-08-30**, and the four new ones are one decision: the owner's broad
    #: signature (`OD-26`) let the nineteen KPIs into the catalog, and the half of `FR-806` that
    #: was missing is the CATALOG half -- each metric declaring which column carries its number.
    #: That field has to exist in `001`'s model, and `FR-808` requires `catalog_schema_version`
    #: to move WITH it rather than after it, which is the loader and the migration.
    #:
    #: **TWELVE since 2026-09-03 (cycle 542, OD-106)**: the L3 reconciliation rule joins —
    #: the sliding semantics run in the CLI validate path; the availability contract and
    #: its classification were already named. By the owner's clicks, opening no gate alone.
    #: **ELEVEN since 2026-09-03 (cycle 539, T109)**: the live warehouse read is 001
    #: runtime too — the CLI's --coverage-live runs through it; no gate opens (the
    #: d_12 record stays open by measurement).
    #: **TEN since 2026-09-03 (cycle 537, OD-103)**: the D-13 sink is 001 runtime —
    #: the real archive the steward check now writes; by the owner's click, opening
    #: no gate by itself.
    #: **NINE since 2026-09-02 (cycle 525, OD-100)**: the D-2 vault is 001 runtime —
    #: the contract module and the loader that admits its kind; both by the owner's
    #: clicked decisions, both with gates that open nothing by themselves.
    #: **SEVEN since 2026-09-02 (cycle 519, OD-99)**: the owner declared `d_1` in `001`'s
    #: readiness record, and the reader's closed `Capability` enum
    #: (`compliance/readiness.py`) had to learn the NAME so the record parses — no gate
    #: opens by it, which the 001 guard node asserts (d_1 is the ONE ready; a second fails).
    #:
    #: The set stays CLOSED and this count is the gate: an eighth path fails here, which is
    #: the difference between naming a decision and widening a rule.
    named_by_instruction = frozenset(
        {
            "packages/semantic_catalog/src/semantic_catalog/periods/temporal.py",
            "packages/semantic_catalog/src/semantic_catalog/compliance/leakage_scan.py",
            "packages/semantic_catalog/src/semantic_catalog/compliance/readiness.py",
            "packages/semantic_catalog/src/semantic_catalog/contracts/definition_approval.py",
            "packages/semantic_catalog/src/semantic_catalog/loader/load.py",
            "packages/semantic_catalog/src/semantic_catalog/provenance/file_archive.py",
            "packages/semantic_catalog/src/semantic_catalog/freshness/warehouse_read.py",
            "packages/semantic_catalog/src/semantic_catalog/validation/l3_reconciliation.py",
            "packages/semantic_catalog/src/semantic_catalog/contracts/_base.py",
            "packages/semantic_catalog/src/semantic_catalog/contracts/classification.py",
            "packages/semantic_catalog/src/semantic_catalog/contracts/metric.py",
            "packages/semantic_catalog/src/semantic_catalog/loader/upgrade.py",
        }
    )
    assert len(named_by_instruction) == 12, "the named set grew without this count being re-derived"

    by_instruction = sorted(path for path in runtime_001 if AUTHORIZED[path].instruction)
    unnamed = sorted(set(by_instruction) - named_by_instruction)
    assert not unnamed, (
        f"the set of 001 runtime paths authorized by owner instruction gained {unnamed}; "
        "that is a decision to state here, not one to absorb"
    )
