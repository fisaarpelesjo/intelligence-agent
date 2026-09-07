"""Every skip this suite can emit begins with a reason the push hook declares.

**The partition changed shape on 2026-09-06, and this node changed with it.**

It used to be a list of FILE PATHS, written twice: once in `catalog.yml`'s `awk` and once,
more harshly, in `nl-analytics.yml`, which tolerated nothing at all. Two declarations of one
decision are two lists waiting to disagree, and the one that disagrees in silence is always
the one nobody reads. A file named in one and not the other is how `catalog.yml` went red on
2026-09-04 for a skip it had been written to permit — the reason was already blessed, the
address was not.

So the partition is now a set of REASON PREFIXES, declared once in
`tools/git-hooks/pre-push` and asked for by three doors. This node asserts the property that
matters after that move: **every reason this suite can emit is inside the partition** — and
it asks the hook rather than holding a copy, because a copy is the thing that ages.

## What it reads, and why the syntax tree

Reasons are read from the AST, not by regular expression, and both forms are read: the
`pytest.skip("...")` call and the `reason=` argument of `@pytest.mark.skipif`. The scan walks
the tree WHOLE rather than top-level only, because a skip inside a function body is exactly
where the credential guards live.

## A reason built at runtime cannot be declared, so it cannot be tolerated

That is not a limitation, it is the finding that forced a reword one directory over: a reason
beginning with an interpolated absolute path has no prefix anybody can write down, and the
gate would have no way to judge it. `test_no_skip_reason_is_unreadable` names those.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

PACKAGE = Path(__file__).resolve().parents[2]
REPO = PACKAGE.parents[1]
HOOK = REPO / "tools" / "git-hooks" / "pre-push"

#: The suite as the hook's partition names it — the same string the workflows pass.
SUITE = "packages/semantic_catalog"

#: Reasons DELIBERATELY outside the partition, each with why firing it is a real defect.
#:
#: **The first version of this node was wrong, and how it was wrong is worth keeping.** It
#: demanded that every emittable reason be TOLERATED, and went red naming three guards that
#: must never be: if `schemas/` is genuinely absent, the suite measured nothing about the
#: exported schemas and the gate SHOULD be red. `test_upstream_node_ids.py` had reached the
#: same conclusion from the other side -- a static scan flagged these exact guards and was
#: discarded for it.
#:
#: So the property is not "everything is tolerated". It is **everything is CLASSIFIED**: a
#: reason is either declared in the hook, or named here with its consequence. A reason in
#: neither fails this node, and the author chooses in the diff that adds it.
MUST_STAY_RED: dict[str, str] = {
    "feature not present": (
        "a feature directory the citation guard walks is missing, so its links were not "
        "resolved; a green run over an absent feature measures nothing"
    ),
    "schemas/ not present": (
        "the exported schemas are absent, so drift between the models and the published "
        "table was not measured -- the one thing that step exists to measure"
    ),
    "no dimension in the production catalog declares source applicability": (
        "the catalog declares no applicability at all; the L3 reconciliation had nothing "
        "to reconcile, and an empty subject is not a passing subject"
    ),
    "the fixture script is not in this checkout": (
        "`tools/ci/assert_fixture_fallback.py` is what two workflows invoke by path; if it "
        "is gone the fixture-fallback refusal is unasserted on both doors"
    ),
}


def _bash() -> str:
    """The shell the gate is written in.

    Absence is a FAILURE and never an absence of one: every gate in this repository's push
    path is this bash hook, and a machine that cannot run it cannot run the gate at all. A
    skip here would also be a skip this very partition does not declare, which would turn
    this node into the thing it forbids.
    """
    found = shutil.which("bash")
    assert found is not None, (
        "no bash on this machine, so the push hook could not be asked what it tolerates; "
        "that is a failure and not an absence of one"
    )
    return found


def declared_prefixes() -> tuple[str, ...]:
    """The reason prefixes the hook declares for this suite. **Asked, never copied.**

    The source is read first to prove the flag is DISPATCHED. `pre-push` matches its
    sub-commands with a chain of `if [ "${1:-}" = ... ]` and falls through to running the
    whole forty-job gate when none match — so an unimplemented flag would start the entire
    push gate from inside a test.
    """
    assert HOOK.is_file(), f"{HOOK} is not in this checkout; the gate's one door is missing"
    source = HOOK.read_text(encoding="utf-8")
    assert '= "--tolerated-skip-reasons"' in source, (
        "the hook does not dispatch `--tolerated-skip-reasons`, so the partition is not "
        "declared in the one place the doors read; it is not invoked here, because a flag "
        "this hook does not recognise falls through to running the entire push gate"
    )
    result = subprocess.run(
        [_bash(), str(HOOK), "--tolerated-skip-reasons", SUITE],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"the hook declares no skip partition for {SUITE}: {result.stderr.strip()!r}. "
        "A partition that cannot be read is a partition that is not applied"
    )
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def _literal(node: ast.expr) -> str:
    """The reason's LEADING fixed text, or the empty string when there is none.

    Implicit concatenation across lines is already folded into one `ast.Constant` by the
    parser, so a reason split over three source lines reads as one string here.

    **An f-string is read too, and reading only its head is the whole point.** The partition
    matches a PREFIX, so a reason that begins with fixed words is judgeable however much it
    interpolates afterwards -- `the caller is not in this checkout ({DELIVER})` is fine. What
    cannot be judged is a reason that BEGINS with interpolation, because its first characters
    change from one machine to the next and no declared prefix can ever match them.

    The first version of this function refused every f-string outright, and that was a defect
    in the instrument rather than in the code: it reported a correctly reworded reason as
    unreadable, which would have pushed the next author to remove the interpolation entirely
    instead of moving it.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else ""
    if isinstance(node, ast.JoinedStr) and node.values:
        head = node.values[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
    return ""


def skip_reasons() -> list[tuple[str, int, str]]:
    """Every skip reason this suite can emit: (file, line, reason)."""
    found: list[tuple[str, int, str]] = []
    for path in sorted((PACKAGE / "tests").rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            if name == "skip":
                #: `pytest.skip(reason="...")` E A GRAFIA DOCUMENTADA, e este ramo nao a lia:
                #: exigia `node.args`, entao a forma nomeada nao era classificada NEM reportada
                #: como ilegivel. Um motivo que o instrumento nao ve nao e um motivo tolerado --
                #: e um motivo sobre o qual ninguem decidiu, que e o que este arquivo proibe.
                if node.args:
                    found.append((path.name, node.lineno, _literal(node.args[0])))
                else:
                    for keyword in node.keywords:
                        if keyword.arg == "reason":
                            found.append((path.name, node.lineno, _literal(keyword.value)))
            if name == "skipif":
                for keyword in node.keywords:
                    if keyword.arg == "reason":
                        found.append((path.name, node.lineno, _literal(keyword.value)))
    return found


def test_every_skip_reason_this_suite_can_emit_is_inside_the_partition() -> None:
    """**The node that fires.**

    Not "the two files that skip today are allowed" — that sentence is the defect. Every
    reason the suite can PRODUCE is compared against the declared prefixes, so a reason
    nobody declared is red in the diff that adds it, on the machine that wrote it, rather
    than on a runner a day later.
    """
    declared = declared_prefixes()
    assert declared, f"the hook declares an EMPTY partition for {SUITE}, so nothing is tolerated"
    emitted = skip_reasons()
    assert emitted, "this suite emits no skip at all, so this node is asserting nothing"

    unclassified = [
        f"{name}:{line}: {reason}"
        for name, line, reason in emitted
        if reason
        and not any(reason.startswith(prefix) for prefix in declared)
        and not any(reason.startswith(prefix) for prefix in MUST_STAY_RED)
    ]
    assert not unclassified, (
        "classified NEITHER as tolerated NOR as must-stay-red: "
        + "; ".join(unclassified)
        + " -- choose in this diff. If the runner lacks it by design, the prefix belongs in "
        "`tolerated_skip_reasons` in tools/git-hooks/pre-push. If firing it means something "
        "is really missing, name it in MUST_STAY_RED with the consequence. A skip that is "
        "neither is a skip nobody decided about."
    )


def test_no_skip_reason_is_unreadable() -> None:
    """A reason built at runtime cannot be declared, so the gate cannot judge it.

    This is what forced the reword in `apps/telegram-bot`: a reason that began with an
    interpolated absolute path has no prefix anybody can write down, and it changes from one
    machine to the next.
    """
    unreadable = [f"{name}:{line}" for name, line, reason in skip_reasons() if not reason]
    assert not unreadable, (
        f"these skips build their reason at runtime: {unreadable}. Lead with a fixed phrase "
        "and interpolate after it, or the partition has nothing to match against"
    )


def test_the_scan_reaches_a_reason_inside_a_function_body() -> None:
    """Proof the instrument bites where the credential guards actually live.

    A top-level-only scan would be green on this repository today and would have been green
    on the day the runner went red. Asserting the scan's REACH keeps the check honest
    independently of whether any reason happens to be undeclared right now.
    """
    inside = [
        f"{name}:{line}"
        for name, line, reason in skip_reasons()
        if reason.startswith("no Google credential is configured")
    ]
    assert len(inside) >= 2, (
        f"the scan found {len(inside)} credential skip(s); it used to find at least two, one "
        "in a `pytest.skip` inside a helper and one in a `skipif` decorator, and losing "
        "either means the walk stopped reaching where the guards live"
    )


def test_an_undeclared_suite_is_refused_rather_than_tolerated() -> None:
    """A mistyped suite name must not read as "nothing needed explaining".

    The same rule the floor already carries: a floor that cannot be read is a failure. Note
    this is NOT the same as a partition that is declared and EMPTY — `analytics_query`
    declares one and tolerates nothing, which is a measured statement rather than silence.
    """
    result = subprocess.run(
        [_bash(), str(HOOK), "--tolerated-skip-reasons", "packages/a_suite_with_no_partition"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        "the hook answered for a suite it declares no partition for; a typo in a workflow "
        "would then tolerate every skip in silence"
    )


def test_no_declared_prefix_outlived_the_skip_it_was_written_for() -> None:
    """**A OUTRA DIRECAO, e nao e simetria por simetria.**

    O `32a7e50` trazia esta metade, por CAMINHO -- e o commit que generalizou a particao para
    PREFIXOS a apagou em silencio, o que e o defeito que aquele commit existia para remover,
    reintroduzido pelo commit que dizia cura-lo. Aqui volta na forma nova.

    Uma isencao deixada para tras depois de o seu motivo deixar de existir nao faz nada falhar:
    ela **permite em silencio algum skip POSTERIOR e sem relacao** que por acaso comece pela
    mesma frase. Apague `test_the_declared_direction_matches_the_source.py` e o prefixo `no
    Google credential is configured` fica no hook para sempre, pre-abencoando o proximo.
    """
    emitted = [reason for _name, _line, reason in skip_reasons() if reason]
    assert emitted, "this suite emits no skip at all, so this node is asserting nothing"

    orphans = [
        prefix
        for prefix in (*declared_prefixes(), *MUST_STAY_RED)
        if not any(reason.startswith(prefix) for reason in emitted)
    ]
    assert not orphans, (
        f"declared for a skip this suite no longer emits: {orphans}. Uma isencao que sobrevive "
        "ao seu motivo nao falha nada -- ela abencoa em silencio o proximo skip que comecar por "
        "essa frase. Remova-a do `tolerated_skip_reasons` (ou do MUST_STAY_RED) no mesmo diff "
        "que removeu o skip"
    )


def test_a_reason_is_never_tolerated_and_must_stay_red_at_once() -> None:
    """As duas listas classificam, e uma classificacao dupla nao classifica nada.

    Sem isto, acrescentar `schemas/ not present` ao `tolerated_skip_reasons` deixa este arquivo
    verde enquanto uma chave chamada `MUST_STAY_RED` documenta uma consequencia que ja nao
    acontece -- prosa que se le como portao.
    """
    both = sorted(set(MUST_STAY_RED) & set(declared_prefixes()))
    assert not both, (
        f"classificado como tolerado E como must-stay-red: {both}. A particao do hook e o "
        "MUST_STAY_RED sao os dois lados de uma escolha; um motivo nos dois nao foi escolhido"
    )
