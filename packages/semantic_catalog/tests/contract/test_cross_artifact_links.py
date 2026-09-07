"""Cross-artifact link check — T103, generalised to every feature in the repository.

The approved artifacts cite each other constantly: the plan cites research
sections, research cites contracts, contracts cite the data model, tasks cite
file paths that production code is supposed to create. Those citations are how a
reviewer navigates the feature, and every one of them is a claim that can rot
silently — a heading gets reworded, a file moves, a task is renumbered, and the
link keeps rendering while pointing at nothing.

This is the check that stops that, **repository-wide**. It is deliberately not
scoped to one feature: a guard that only polices the feature that wrote it stops
guarding the moment a second feature appears.

Every rule below is also exercised by a mutation test: the guard is shown to
fail on a real violation, not merely to pass on a clean tree.

Five rules:

* every relative Markdown link resolves to a file that exists;
* every ``#anchor`` matches a heading in the file it points at, slugged the way
  GitHub slugs headings;
* every backticked repository path resolves — or is an artifact a still-open task
  has promised to create;
* every ``T###`` reference names a task that is actually declared, resolved
  against the right feature;
* the promise mechanism expires by itself.

## Task references across features

Task numbers collide: `001` and `002` both declare a `T016`. So references are
resolved against a **feature**, never against a global pool:

* ``001:T115`` — qualified. Resolved against that feature, from anywhere.
* ``T115`` — unqualified. Resolved against the feature that **owns the
  referencing artifact**.

Ownership is derived, never configured. An artifact under ``specs/<feature>/``
belongs to that feature. An artifact outside it — an ADR, say — belongs to the
feature whose ``tasks.md`` names it as an output. `001`'s ADRs are named by
`001`'s tasks; `002`'s by `002`'s. Nothing is maintained by hand.

An artifact no feature owns — a fixture README, say — has no home registry to
resolve against, so its references are checked against the union: the number must
be declared by some feature. Ambiguity only matters where a reference genuinely
means one feature's task, which is the owned case above.

## Paths that do not exist yet

A task list names files the tasks will create. Demanding they exist before the
task runs would force either a fabricated file or a deleted reference.

So a missing path is permitted when — and only when — it is the **declared output
of an uncompleted task in the same feature**. That permission is *derived from
``tasks.md``*, never a hand-maintained allowlist, and it is deliberately narrow:

* the path must appear in the task's **description**, not in its ``Deps``,
  ``FR``, ``SC``, ``Evidence`` or ``Validation`` lines — a path discussed in
  prose is not a promise to create it;
* the citation is expanded against the same derived roots used to test
  existence, and each expansion is matched for **exact equality** against the
  promised set — root expansion, never prefix or fuzzy matching;
* the owning task must still be **open**. Marking it complete while the file is
  still absent fails, which is the whole point;
* creating the file removes the need for the permission entirely.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
PACKAGE = REPO / "packages" / "semantic_catalog"
SPECS = REPO / "specs"

_SKIP = {".venv", ".git", ".claude", ".specify", ".pytest_cache", "__pycache__", "node_modules"}
_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
#: Only paths that name a directory. A bare `owners.yaml` in prose is a file
#: name, not a repository path, and demanding it resolve produces noise.
_CODE_PATH = re.compile(r"`(/?[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)+\.(?:py|yaml|yml|json|md|toml))`")
#: The shape of a task id, everywhere one is written: three or four digits, with an
#: optional lowercase suffix. **One definition, used by all three patterns below**, so a
#: reference and a declaration can never disagree about what an id looks like.
#:
#: Four digits because `013` numbers its work ``T1301``..``T1337``. A three-digit pattern
#: did not fail on those — it matched their first three digits and dropped the rest, which
#: is why thirty-eight declarations became four registry keys and six open tasks were
#: reported complete. The trailing ``(?![0-9a-z])`` makes the *next* widening loud instead:
#: a five-digit id does not parse at all, and
#: `test_every_task_shaped_line_is_actually_parsed` says so by name rather than silently
#: truncating it the way this pattern used to.
#:
#: The suffix is part of the id, not decoration. `013` declares both ``T1320a`` and
#: ``T1320b``; they are two tasks with two checkboxes, and anything that discards the letter
#: merges them.
_TASK_ID = r"(\d{3,4}[a-z]?)(?![0-9a-z])"
#: A qualified reference names its feature by numeric prefix: ``001:T115``, ``013:T1336``.
_QUALIFIED_REF = re.compile(r"\b(\d{3}):T" + _TASK_ID)
#: An unqualified reference. The qualified form is stripped before this runs, so
#: the two never double-count the same citation.
#:
#: **A suffixed id is deliberately citable.** ``\bT(\d{3})\b`` could not match ``T1320a``
#: — the trailing letter defeats the closing ``\b`` — so a citation of a real, declared task
#: was invisible to every check here. Invisibility is the failure mode this module exists to
#: remove: a reference nobody matches is not a reference nobody needs, it is a claim nobody
#: verified. So ``T1320a`` resolves against `013`'s registry like any other id, and
#: ``T1320z`` is reported dangling like any other undeclared one.
_TASK_REF = re.compile(r"\bT" + _TASK_ID)
#: A task line: state, id, and everything after it on that line.
_TASK_LINE = re.compile(r"^- \[([ Xx])\] T" + _TASK_ID + r"(.*)$", re.M)
#: The same line, matched without reading the id — used only to prove every task-shaped
#: line was actually parsed, so a future numbering scheme cannot slip past unparsed.
_TASK_LINE_SHAPE = re.compile(r"^- \[[ Xx]\] T", re.M)
#: Marks a dependency record rather than executable work. Never completable here.
_EXTERNAL_RECORD = "[BLOCKED-EXTERNAL]"


# --------------------------------------------------------------------------- #
# Feature discovery and the task registry
# --------------------------------------------------------------------------- #


def _feature_dirs() -> dict[str, Path]:
    """Every ``specs/*/`` directory that declares a task list, keyed by name."""
    if not SPECS.is_dir():
        return {}
    return {d.name: d for d in sorted(SPECS.iterdir()) if (d / "tasks.md").is_file()}


FEATURES = _feature_dirs()


def _feature_prefix(feature: str) -> str:
    """``002-analytics-query`` -> ``002``."""
    return feature.split("-", 1)[0]


def _task_states(feature: str) -> dict[str, bool]:
    """``{task id: is_complete}`` for one feature, executable or not.

    ## The key is the id **as written**, never an integer

    `int(num)` was the second half of the collapse, and widening the regex alone does not
    remove it. Three reasons it cannot come back:

    * ``int("1320a")`` does not evaluate. Any route to an integer has to discard the
      suffix first, which merges `013`'s ``T1320a`` and ``T1320b`` into one key — the same
      last-writer-wins defect, one layer down.
    * ``int`` equates spellings that are different citations: ``T013``, ``T13`` and
      ``T0013`` all become ``13``. A registry keyed on text cannot confuse them.
    * A citation is text and a declaration is text. Comparing them without a lossy
      transform in between is the only arrangement in which the two cannot drift.

    The ids are zero-padded and fixed-width within a feature, so ordering and ``max()``
    behave exactly as they did — see `test_feature_003_is_complete_while_its_records_stay_open`.
    """
    text = (FEATURES[feature] / "tasks.md").read_text(encoding="utf-8")
    return {num: state.upper() == "X" for state, num, _rest in _TASK_LINE.findall(text)}


def _executable_task_states(feature: str) -> dict[str, bool]:
    """``{task id: is_complete}`` for the **executable** tasks only.

    A ``[BLOCKED-EXTERNAL]`` line is a dependency *record*, not work: it has no
    completion path inside this repository and nothing here can ever mark it
    done. Counting one as an open task would let it hold an artifact permission
    open forever, which is precisely the "permission outliving its task" defect
    this module exists to catch. Records are therefore excluded from the task
    states the permission mechanism consults, and from `_promised_artifacts`
    below, so a record can neither authorize an artifact nor keep one excused.
    """
    text = (FEATURES[feature] / "tasks.md").read_text(encoding="utf-8")
    return {
        num: state.upper() == "X"
        for state, num, rest in _TASK_LINE.findall(text)
        if _EXTERNAL_RECORD not in rest
    }


def _promised_artifacts(feature: str) -> dict[str, str]:
    """Paths a task **declares as its output**, keyed by path, valued by task id.

    Read from the task's description only. A path cited in an ``Evidence`` or
    ``Validation`` line is discussed, not promised, and granting it a permission
    would let any prose mention excuse a missing file.

    ``[BLOCKED-EXTERNAL]`` records are skipped for the reason given in
    `_executable_task_states`: a record promises nothing this repository can
    deliver.
    """
    text = (FEATURES[feature] / "tasks.md").read_text(encoding="utf-8")
    promised: dict[str, str] = {}
    for _state, num, description in _TASK_LINE.findall(text):
        if _EXTERNAL_RECORD in description:
            continue
        for path in _CODE_PATH.findall(description):
            promised.setdefault(_normalise(path), num)
    return promised


def _normalise(path: str) -> str:
    """Repository-relative, forward slashes, no leading slash. Exact matching only."""
    return path.lstrip("/").replace("\\", "/")


TASK_STATES = {name: _task_states(name) for name in FEATURES}
EXECUTABLE_TASK_STATES = {name: _executable_task_states(name) for name in FEATURES}
PROMISED = {name: _promised_artifacts(name) for name in FEATURES}
PREFIX_TO_FEATURE = {_feature_prefix(name): name for name in FEATURES}


def feature_is_complete(executable: dict[str, bool]) -> bool:
    """Has every executable task of a feature been completed?

    A feature with no executable tasks is not "complete" — it has not started.
    """
    return bool(executable) and all(executable.values())


#: Features **required** to have finished their executable work. Named, never derived.
#:
#: Scoping the completion invariants to features that have *actually* finished — the
#: criterion the terminal-artifact guard already uses — is what lets a feature in
#: planning hold open tasks without failing a claim it was never subject to. Applied
#: alone, that scoping would also make the claim tautological: a feature would be
#: exempt exactly when it failed.
#:
#: So the binding half names its features. A feature listed here cannot leave the
#: claim by un-checking a task; it can only fail it. Adding a feature here is the
#: deliberate act of declaring its work finished, and `004` is deliberately absent
#: while its ledger is open.
COMPLETION_BOUND_FEATURES = (
    "001-semantic-catalog",
    "002-analytics-query",
    "003-nl-analytics-interaction",
)


def finished_features() -> list[str]:
    """Features whose executable work is complete, by the terminal guard's criterion.

    The same predicate `test_no_permission_is_outstanding_now_that_every_task_is_complete`
    applies per feature, lifted so the completion invariants can share one definition
    of "finished" instead of two that could drift apart.
    """
    return [name for name in sorted(FEATURES) if feature_is_complete(EXECUTABLE_TASK_STATES[name])]


def outstanding_permissions(
    promised: dict[str, str],
    executable: dict[str, bool],
    exists: Callable[[str], bool],
) -> list[tuple[str, str, str]]:
    """Permissions no open executable task can justify, as ``(fault, task, path)``.

    A missing artifact is excused only while the executable task that declared
    it is still open. Two faults break that, and both are independent of how far
    the feature has progressed:

    ``completed``
        the owning task is finished and the artifact still is not there. The
        permission has outlived its task, which is the original defect.
    ``unowned``
        the path is promised by a number that is not an open executable task —
        a ``[BLOCKED-EXTERNAL]`` record or a stale id left by renumbering.
        Neither can ever produce a file, so neither may excuse one.

    A path whose owning task is open and executable is legitimately outstanding
    and is not reported. Whether *any* such permission may remain is a separate,
    stronger claim that only applies once a feature has finished — see
    :func:`feature_is_complete` and the terminal test.
    """
    faults: list[tuple[str, str, str]] = []
    for path, owner in sorted(promised.items()):
        if exists(path):
            continue
        state = executable.get(owner)
        if state is True:
            faults.append(("completed", owner, path))
        elif state is None:
            faults.append(("unowned", owner, path))
    return faults


# --------------------------------------------------------------------------- #
# Ownership — derived, never configured
# --------------------------------------------------------------------------- #


def _owning_feature(artifact: Path) -> str | None:
    """Which feature an artifact belongs to.

    Under ``specs/<feature>/`` it is that feature. Outside it, the feature whose
    task list names the artifact as an output — which is how `001`'s ADRs belong
    to `001` and `002`'s to `002` without anyone maintaining a mapping.
    """
    try:
        relative = artifact.resolve().relative_to(REPO)
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) >= 2 and parts[0] == "specs" and parts[1] in FEATURES:
        return parts[1]
    key = _normalise(relative.as_posix())
    owners = [name for name, promised in PROMISED.items() if key in promised]
    return owners[0] if len(owners) == 1 else None


# --------------------------------------------------------------------------- #
# Files, anchors, resolution
# --------------------------------------------------------------------------- #


def _markdown_files() -> list[Path]:
    """Every markdown file **git tracks** — `OD-154`, 2026-09-07, palavra dele.

    ## Porque nao e um `rglob`, e o que isso custava

    Era `REPO.rglob("*.md")` filtrado por `_SKIP` contra `p.parts` do caminho ABSOLUTO, e
    respondia coisas diferentes conforme a maquina. **Medido em 2026-09-06, nas duas
    direccoes:**

    * **192 ficheiros aqui, 190 num clone limpo.** O `rglob` nao le o `.gitignore`, entao dois
      documentos que o git ignora entravam na lista nesta maquina e faltavam no CI. Os quatro
      nos parametrizados por esta lista existiam localmente e **nem colhiam** la.
    * **Dentro de um worktree, ZERO.** Um worktree de agente vive sob `.claude/`, que esta no
      `_SKIP`; o filtro olhava para o caminho absoluto, entao TODO ficheiro tinha `.claude` nas
      suas partes e a lista vinha vazia. Um subagente correu os quatro nos e nenhum colheu --
      incluindo justamente o que a mudanca dele mais afectava.

    **Um vigia cuja resposta muda com a maquina nao e um vigia**, e o `ADR 0025` di-lo por
    outras palavras. Aqui estava a falhar dos dois lados ao mesmo tempo.

    ## O que muda, exactamente

    A lista vem de `git ls-files`, entao **e o conjunto versionado** e o portao local mede o
    mesmo que o CI, por construcao e nao por coincidencia. O `_SKIP` fica, mas passa a ser
    comparado com o caminho **RELATIVO ao repositorio** -- que e o que o git devolve --, entao
    `.claude` so o exclui quando e mesmo a pasta `.claude/` da raiz, e nunca porque um worktree
    calhou de viver la dentro.

    **Nao alarga o ambito de proposito.** So o `git ls-files` traria dez ficheiros `.md`
    versionados sob `.claude/skills/`, ferramenta de terceiros; medido, um deles cita `T0010`
    como EXEMPLO e reprovaria por uma referencia que nao e nossa. O `_SKIP` continua a mante-los
    fora, que e a mesma decisao de sempre, agora escrita onde se ve.

    ## Sem git nao ha lista, e isso e uma FALHA e nao uma ausencia dela

    Se o comando nao correr, este vigia nao pode saber o que existe. Recusa, em vez de devolver
    uma lista vazia que passaria todos os nos por nao ter nada que medir -- que e o defeito que
    este ficheiro inteiro existe para nao cometer.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert listed.returncode == 0, (
        f"`git ls-files` falhou em {REPO}: {listed.stderr.strip()!r}. Sem ela nao ha conjunto "
        "versionado para medir, e uma lista vazia passaria todos os nos por nao ter nada que "
        "medir -- entao recusa"
    )
    relatives = [Path(name) for name in listed.stdout.split(chr(0)) if name.strip()]
    assert relatives, "`git ls-files` nao devolveu ficheiro nenhum; nada seria medido"
    return sorted(
        REPO / relative
        for relative in relatives
        if not any(part in _SKIP for part in relative.parts)
    )


def _slug(heading: str) -> str:
    """GitHub's rule: lowercase, drop punctuation, **each space becomes a hyphen**.

    Collapsing runs of whitespace is the tempting simplification and it is
    wrong: a heading containing an em dash renders two consecutive hyphens in
    its anchor, and a checker that collapsed them would report every such link
    as broken.
    """
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return text.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    return {
        _slug(line.lstrip("#"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    }


def _citation_roots() -> list[Path]:
    """Directories a relative citation may be written against, all derived.

    Documentation cites `validation/pipeline.py`, `gates/coverage.py` or
    `checklists/requirements.md` rather than the full repository path, because
    the reader already knows which package or feature is under discussion. The
    roots that make those readable are therefore:

    * top-level repository trees — `query_governance/`, `docs/`, `semantic/`;
    * each feature directory under `specs/`;
    * each package, its fixture tree, and every directory inside its source tree.

    Deriving them means a new package or feature is checkable the day it appears,
    with nothing to remember.
    """
    roots: list[Path] = [
        child for child in sorted(REPO.iterdir()) if child.is_dir() and child.name not in _SKIP
    ]
    roots.extend(FEATURES.values())
    packages = REPO / "packages"
    if packages.is_dir():
        for pkg in sorted(packages.iterdir()):
            if not pkg.is_dir():
                continue
            roots.append(pkg)
            roots.append(pkg / "tests" / "fixtures")
            src = pkg / "src"
            if src.is_dir():
                roots.extend(
                    d for d in sorted(src.rglob("*")) if d.is_dir() and "__pycache__" not in d.parts
                )
    return roots


CITATION_ROOTS = _citation_roots()


def _candidates(candidate: str, origin: Path) -> list[Path]:
    """Every location a citation could denote, from the derived roots."""
    trimmed = candidate.lstrip("/")
    options = [REPO / trimmed, origin.parent / candidate]
    options.extend(root / trimmed for root in CITATION_ROOTS)
    return options


def _inside_repository(option: Path) -> bool:
    """Does ``option`` land inside this repository once resolved?

    ADR 0025. A backticked path with a file extension is a claim that the file is **part of this
    repository**. An option that resolves outside the root cannot support that claim, however
    real the file is on one machine — so it must not count as existence.

    The failure this closes was measured, not imagined: a release note cited
    ``../claude-loop-instructions.yml``, which exists one level above the checkout on the machine
    running the authoring loop and does not exist in CI. The suite passed locally and four
    workflows failed. A pass that depends on a file outside the working tree is not evidence.
    """
    try:
        option.resolve().relative_to(REPO)
    except ValueError:
        return False
    return True


def _resolves(candidate: str, origin: Path) -> bool:
    """Does ``candidate`` denote a file that exists **inside** this repository?

    Options landing outside the root are discarded before existence is consulted (ADR 0025), which
    is what makes the answer identical on a developer machine and on a clean checkout. This is a
    strict tightening: it can only withdraw evidence that came from outside the repository, and
    nothing inside it changes.
    """
    return any(
        option.exists() for option in _candidates(candidate, origin) if _inside_repository(option)
    )


def _repo_relative_candidates(candidate: str, origin: Path) -> set[str]:
    """The same candidates, normalised to repository-relative paths."""
    resolved: set[str] = set()
    for option in _candidates(candidate, origin):
        try:
            resolved.add(_normalise(option.resolve().relative_to(REPO).as_posix()))
        except ValueError:
            continue
    return resolved


def _permitted_missing(candidate: str, origin: Path) -> bool:
    """Is this missing path the declared output of an open task in its own feature?

    Documentation cites `contracts/request.py` where the task list declares
    `packages/analytics_query/src/analytics_query/contracts/request.py`. The
    citation is expanded against the **same derived roots** used to test
    existence, and each expansion is then compared for **exact equality** against
    the promised set. That is root expansion, not fuzzy matching: a directory
    prefix, a near-miss filename or a path under a different tree produces no
    expansion that equals a promised key.

    The permission is granted only by the **owning** feature's task list, so one
    feature can never excuse another's missing file.
    """
    feature = _owning_feature(origin)
    if feature is None:
        return False
    promised = PROMISED[feature]
    for path in _repo_relative_candidates(candidate, origin):
        owner = promised.get(path)
        if owner is not None and not TASK_STATES[feature].get(owner, False):
            return True
    return False


FILES = _markdown_files()


# --------------------------------------------------------------------------- #
# The checks
# --------------------------------------------------------------------------- #


def test_there_is_documentation_to_check() -> None:
    """A checker that found no files would pass by doing nothing."""
    assert len(FILES) >= 30, len(FILES)


def test_every_feature_declares_a_task_list() -> None:
    """The registry must actually have found the features it claims to police."""
    assert FEATURES, "no feature task lists discovered under specs/"
    for name in FEATURES:
        assert TASK_STATES[name], f"{name} declares no tasks"


@pytest.mark.parametrize("path", FILES, ids=[str(p.relative_to(REPO)) for p in FILES])
def test_every_relative_link_resolves(path: Path) -> None:
    broken = broken_links(path.read_text(encoding="utf-8"), path)
    assert not broken, broken


@pytest.mark.parametrize("path", FILES, ids=[str(p.relative_to(REPO)) for p in FILES])
def test_every_anchor_matches_a_heading(path: Path) -> None:
    broken: list[str] = []
    for _, target in _LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")) or "#" not in target:
            continue
        file_part, anchor = target.split("#", 1)
        resolved = (path.parent / file_part).resolve() if file_part else path
        if resolved.suffix != ".md" or not resolved.exists():
            continue
        if anchor not in _anchors(resolved):
            broken.append(target)
    assert not broken, broken


def missing_paths(text: str, origin: Path) -> list[str]:
    """Backticked repository paths in ``text`` that neither resolve nor are permitted."""
    missing: list[str] = []
    for candidate in _CODE_PATH.findall(text):
        if candidate.startswith(("http", "semantic.", "bigquery")):
            continue
        if _resolves(candidate, origin) or _permitted_missing(candidate, origin):
            continue
        missing.append(candidate)
    return missing


def broken_links(text: str, origin: Path) -> list[str]:
    """Relative Markdown links in ``text`` whose target does not exist."""
    broken: list[str] = []
    for label, target in _LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        target = target.split("#", 1)[0]
        if target and not (origin.parent / target).resolve().exists():
            broken.append(f"[{label}]({target})")
    return broken


@pytest.mark.parametrize("path", FILES, ids=[str(p.relative_to(REPO)) for p in FILES])
def test_every_backticked_repository_path_resolves(path: Path) -> None:
    missing = missing_paths(path.read_text(encoding="utf-8"), path)
    assert not missing, missing


def dangling_task_refs(text: str, owner: str | None) -> list[str]:
    """Task references in ``text`` that do not resolve for the given owning feature."""
    dangling: list[str] = []

    for prefix, number in _QUALIFIED_REF.findall(text):
        feature = PREFIX_TO_FEATURE.get(prefix)
        if feature is None:
            dangling.append(f"{prefix}:T{number} — no feature with prefix {prefix}")
        elif number not in TASK_STATES[feature]:
            dangling.append(f"{prefix}:T{number} — not declared by {feature}")

    # The qualified form is stripped first so the two never double-count the same
    # citation. Both patterns now share `_TASK_ID`, which is what keeps the stripping
    # exhaustive: a reference the qualified pattern could not match — `013:T1336` under
    # the old three-digit form — survived the substitution and was then re-read here as
    # something else, or as nothing at all.
    for number in _TASK_REF.findall(_QUALIFIED_REF.sub("", text)):
        if owner is not None:
            if number not in TASK_STATES[owner]:
                dangling.append(
                    f"T{number} — not declared by owning feature {owner}; "
                    f"qualify it if another feature is meant"
                )
            continue
        if not any(number in states for states in TASK_STATES.values()):
            dangling.append(f"T{number} — declared by no feature")
    return dangling


@pytest.mark.parametrize("path", FILES, ids=[str(p.relative_to(REPO)) for p in FILES])
def test_every_task_reference_names_a_declared_task(path: Path) -> None:
    """A renumbered task leaves references pointing at nothing."""
    dangling = dangling_task_refs(path.read_text(encoding="utf-8"), _owning_feature(path))
    assert not dangling, f"{path.relative_to(REPO)}: {sorted(set(dangling))}"


def test_no_manual_allowlist_exists() -> None:
    """Permissions are derived from task lists, never hand-maintained.

    The previous form of this checker carried a module-level dictionary of
    excused paths. It held one entry, which was removed when the task that owed
    the artifact produced it. A hand-maintained exception outlives the reason it
    was added; a derived one cannot.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    # `int` and `str` both, because the registry's task ids stopped being integers: an
    # allowlist re-added at the registry's *current* value type would otherwise walk past a
    # guard still watching for the old one.
    assert not re.search(r"^[A-Z_]+: *dict\[str, (?:int|str)\] *= *\{[^}]", source, re.M), (
        "a hand-maintained allowlist constant has reappeared"
    )
    # The terminal report that motivated the original entry still exists.
    assert (REPO / "docs/release/internal-validation-report.md").is_file()


def test_permissions_expire_by_themselves() -> None:
    """A permission survives only while its owning task is open.

    Both directions fail: complete the task without producing the artifact and
    this reports it; create the artifact and the permission is simply unused.
    """
    stale: list[str] = []
    for feature, promised in PROMISED.items():
        for artifact, task in sorted(promised.items()):
            complete = TASK_STATES[feature].get(task, False)
            exists = (REPO / artifact).exists()
            if complete and not exists and not _resolves(artifact, FEATURES[feature] / "tasks.md"):
                stale.append(f"{feature} T{task} is complete but {artifact} does not exist")
    assert not stale, stale


def test_the_measurement_procedures_referenced_by_tasks_exist() -> None:
    """T104-T106 are the tasks that create these; nothing else may promise them."""
    text = (FEATURES["001-semantic-catalog"] / "tasks.md").read_text(encoding="utf-8")
    for name in (
        "sc-012-answerability-comprehension",
        "sc-015-dispute-tracking",
        "sc-028-pending-comprehension",
    ):
        assert f"docs/measurement/{name}.md" in text
        assert (REPO / "docs" / "measurement" / f"{name}.md").exists(), name


# --------------------------------------------------------------------------- #
# Mutation tests — the guard must fail on real violations
# --------------------------------------------------------------------------- #
#
# A checker that has only ever passed proves nothing about what it catches. Each
# test below feeds a real violation to the same functions the checks above use,
# and asserts it is reported.

F002 = "002-analytics-query"
F001 = "001-semantic-catalog"
PLAN_002 = SPECS / F002 / "plan.md"


def test_mutation_unknown_task_reference_is_reported() -> None:
    """A number no feature declares must be caught, owned or not."""
    assert dangling_task_refs("see T999 for details", F002)
    assert dangling_task_refs("see T999 for details", None)


def test_mutation_cross_feature_reference_must_be_qualified() -> None:
    """`002` declares no T130; citing 001's T130 unqualified from a 002 artifact fails."""
    assert "130" not in TASK_STATES[F002]
    assert dangling_task_refs("depends on T130", F002), (
        "an unqualified reference to another feature's task must be reported"
    )


def test_mutation_qualified_reference_resolves_to_the_named_feature() -> None:
    """`001:T115` resolves against 001 even though 002 also declares a T115."""
    assert "115" in TASK_STATES[F001] and "115" in TASK_STATES[F002]
    assert not dangling_task_refs("inherits 001:T115", F002)
    assert dangling_task_refs("inherits 001:T130", F002), "001 declares no T130"
    assert dangling_task_refs("inherits 999:T001", F002), "no feature has prefix 999"


# --------------------------------------------------------------------------- #
# Task ids wider than three digits
#
# `013` numbers its work `T1301`..`T1337`. A three-digit parser read `T(\d{3})`
# out of every one of those lines, so thirty-eight declarations collapsed into
# four keys and the last line to write each key decided its state. That is not a
# missing check; it is a check answering about the wrong task.
# --------------------------------------------------------------------------- #

F013 = "013-dimensional-analysis"

#: The `013` tasks a three-digit parser reported as **complete while they were open**.
#:
#: Measured on 2026-09-06 against `specs/013-dimensional-analysis/tasks.md`. Key `132`
#: collected eleven lines, `T1321`..`T1329` among them, and `T1329` — the last one — is
#: `[x]`. So `T1321`, `T1323` and `T1326`..`T1328` inherited a neighbour's checkbox.
#: `T1310` inherited `T1319`'s the same way.
#:
#: Named literally because the tuple is the anchor: a registry that has re-collapsed
#: cannot contain these ids at all, whatever it contains instead. The *expectation* is
#: re-read from `tasks.md` on every run, so completing one of the six keeps the node
#: green — what is forbidden is the registry disagreeing with the line.
_013_TASKS_HIDDEN_BY_THE_THREE_DIGIT_PARSER = ("1310", "1321", "1323", "1326", "1327", "1328")


def test_every_declared_task_line_gets_its_own_registry_entry() -> None:
    """One declared task, one key. **Repo-wide, and it was false when written.**

    The collapse is a property of the parser, not of `013`: any feature numbering past
    `T999` loses the distinction between its tasks. Stating it over every feature means the
    next four-digit feature is covered the day it appears, with nothing to remember.
    """
    collapsed: list[str] = []
    for feature, directory in FEATURES.items():
        lines = _TASK_LINE.findall((directory / "tasks.md").read_text(encoding="utf-8"))
        keys = TASK_STATES[feature]
        if len(keys) != len(lines):
            collapsed.append(f"{feature}: {len(lines)} task lines collapsed into {len(keys)} keys")
    assert not collapsed, collapsed


def test_every_task_shaped_line_is_actually_parsed() -> None:
    """**The next widening must be loud.** A line that does not parse is not a line that passed.

    The three-digit pattern did not reject `T1301`; it read three of its four digits and
    kept going, which is why the collapse was silent for as long as it was. `_TASK_ID` now
    ends in ``(?![0-9a-z])``, so a five-digit id produces **no match at all** — and this node
    is what turns that from a second silence into a named failure.
    """
    unparsed: list[str] = []
    for feature, directory in FEATURES.items():
        text = (directory / "tasks.md").read_text(encoding="utf-8")
        shaped = len(_TASK_LINE_SHAPE.findall(text))
        parsed = len(_TASK_LINE.findall(text))
        if shaped != parsed:
            unparsed.append(f"{feature}: {shaped} task-shaped lines, only {parsed} parsed")
    assert not unparsed, unparsed


def test_the_six_open_013_tasks_are_read_from_their_own_lines() -> None:
    """**The defect, named.** Each id's state comes from its line, never from a neighbour's.

    Six tasks were reported finished while their own lines were unchecked. The assertion is
    not "these six are open" — that would expire the moment one is done — but "the registry
    says about each of these six exactly what its own line says".
    """
    assert F013 in FEATURES
    text = (FEATURES[F013] / "tasks.md").read_text(encoding="utf-8")
    declared = {num: state.upper() == "X" for state, num, _rest in _TASK_LINE.findall(text)}

    wrong: list[str] = []
    for task in _013_TASKS_HIDDEN_BY_THE_THREE_DIGIT_PARSER:
        assert f"- [ ] T{task}" in text or f"- [x] T{task}" in text or f"- [X] T{task}" in text, (
            f"T{task} is no longer declared by {F013}; this node names real ids"
        )
        if task not in TASK_STATES[F013]:
            wrong.append(f"T{task} is declared by {F013} and has no registry entry")
        elif TASK_STATES[F013][task] != declared[task]:
            wrong.append(
                f"T{task}: its line says complete={declared[task]} and the registry says "
                f"complete={TASK_STATES[F013][task]}"
            )
    assert not wrong, wrong


def test_a_suffixed_task_id_is_a_task_of_its_own() -> None:
    """`T1320a` and `T1320b` are two tasks, and `int()` cannot tell them apart.

    Widening the regex alone does not fix this: `int("1320a")` does not even evaluate, and
    any scheme that reaches an integer must first discard the suffix — which re-merges the
    two. The id is the key, verbatim.
    """
    assert "1320a" in TASK_STATES[F013] and "1320b" in TASK_STATES[F013]
    assert not dangling_task_refs("see T1320a and T1320b", F013)
    assert dangling_task_refs("see T1320z", F013), "013 declares no T1320z"


def test_a_qualified_four_digit_reference_is_checked_at_all() -> None:
    """A qualified four-digit citation matched **nothing**, which is worse than dangling.

    An unresolvable reference that is reported is a defect with an owner. One that no regex
    matches is a citation nobody ever checked, and `013:T1399` passed every run.
    """
    assert not dangling_task_refs("see 013:T1336 for the detail", F002)
    assert dangling_task_refs("see 013:T1399", F002), "013 declares no T1399"
    assert dangling_task_refs("see 999:T1336", F002), "no feature has prefix 999"


def test_mutation_unlisted_missing_path_is_reported() -> None:
    """A path no task promises gets no permission, however plausible it looks."""
    invented = "packages/analytics_query/src/analytics_query/contracts/not_a_real_module.py"
    assert not (REPO / invented).exists()
    assert missing_paths(f"see `{invented}` for details", PLAN_002) == [invented]


def test_mutation_fuzzy_and_prefix_paths_are_reported() -> None:
    """Matching is exact after root expansion. Near misses and prefixes are not promised."""
    for near_miss in (
        "packages/analytics_query/src/analytics_query/contracts/reason_codes2.py",
        "other/packages/analytics_query/src/analytics_query/contracts/reason_codes.py",
        "packages/analytics_query/src/analytics_query/contracts/reason_codes.md",
        "packages/analytics_query/src/analytics_query/contracts/nested/reason_codes.py",
    ):
        assert missing_paths(f"`{near_miss}`", PLAN_002) == [near_miss], near_miss

    # A promised path's parent directory is not itself promised, and a citation
    # carrying an unknown suffix is not recognised as a repository path at all.
    assert _CODE_PATH.findall("`packages/analytics_query/src/analytics_query/contracts/`") == []
    assert _CODE_PATH.findall("`contracts/reason_codes.py.bak`") == []


def test_mutation_prose_only_path_is_not_promised() -> None:
    """A path named in Evidence or Validation text is discussed, not promised."""
    prose = "docs/release/a-file-only-mentioned-in-evidence.md"
    assert prose not in PROMISED[F002]
    assert missing_paths(f"`{prose}`", PLAN_002) == [prose]


# --------------------------------------------------------------------------- #
# ADR 0025 — a citation that escapes the repository root                       #
# --------------------------------------------------------------------------- #
# Five additive regressions. The defect they close was real and was caught by CI
# rather than here: a release note cited `../claude-loop-instructions.yml`, which
# exists one level above the checkout on the authoring machine and not in CI, so
# this suite passed locally while four workflows failed. The rule is now that an
# option landing outside the root cannot supply existence, however real the file
# is somewhere.


def test_adr_0025_inside_repository_is_decided_by_the_root_not_by_existence() -> None:
    """The predicate, alone. Deterministic, and true of paths that do not exist."""
    assert _inside_repository(REPO / "docs")
    assert _inside_repository(REPO / "docs" / "a-file-that-does-not-exist.md")
    assert not _inside_repository(REPO.parent / "claude-loop-instructions.yml")
    assert not _inside_repository(REPO / ".." / "anything.yml")
    # A chain that leaves and returns is inside: what matters is where it lands.
    assert _inside_repository(REPO / "docs" / ".." / "README.md")


def test_adr_0025_a_file_that_really_exists_outside_the_root_does_not_resolve(
    tmp_path: Path,
) -> None:
    """The load-bearing case, proven against a file that genuinely exists.

    ``tmp_path`` is outside the repository in every environment, so the escaping citation below
    denotes something real. Before ADR 0025 that reality was accepted as evidence. The assertion
    is that it is not — existence outside the root is not existence in the repository.
    """
    outside = tmp_path / "declared-elsewhere.yml"
    outside.write_text("fixture: true\n", encoding="utf-8")
    assert outside.exists(), "the test needs a file that really exists outside the root"

    escaping = Path(os.path.relpath(outside, REPO)).as_posix()
    assert escaping.startswith(".."), f"expected an escaping relative path, got {escaping}"
    assert (REPO / escaping).exists(), "the pre-ADR resolution path must still find it"
    assert not _resolves(escaping, PLAN_002), "an outside file was accepted as repository evidence"


def test_adr_0025_the_historical_citation_is_reported_end_to_end() -> None:
    """The exact string CI failed on, through the regex and ``missing_paths``.

    Reported whether or not the loop instruction file happens to exist beside the checkout, which
    is the whole point: the two machines must now agree.
    """
    escaping = "../claude-loop-instructions.yml"
    assert _CODE_PATH.findall(f"`{escaping}`") == [escaping]
    assert missing_paths(f"see `{escaping}` for the rules", PLAN_002) == [escaping]


def test_adr_0025_an_escaping_citation_cannot_be_excused_by_an_open_task() -> None:
    """The permission is repo-bound too, so the tightening has no back door.

    An open task's declared output excuses a *missing* file. It must not excuse a file that is not
    in this repository at all, otherwise a feature could promise something outside the tree.
    """
    for escaping in ("../claude-loop-instructions.yml", "../../elsewhere/contracts/request.py"):
        assert not _permitted_missing(escaping, PLAN_002)
        assert missing_paths(f"`{escaping}`", PLAN_002) == [escaping]


def test_adr_0025_changes_nothing_for_paths_inside_the_repository() -> None:
    """The tightening withdraws only outside evidence. Asserted, not assumed.

    Three kinds of inside-repo citation keep behaving exactly as before: a real file cited by its
    repository path, the same file cited by a root-relative form, and a real file cited from a
    document that sits in another directory.
    """
    real = "packages/semantic_catalog/tests/contract/test_cross_artifact_links.py"
    assert (REPO / real).exists()
    assert _resolves(real, PLAN_002)
    assert _resolves(f"/{real}", PLAN_002)
    assert missing_paths(f"`{real}`", PLAN_002) == []
    assert missing_paths("`docs/adr/0025-repository-bound-path-citations.md`", PLAN_002) == []


def test_mutation_completed_owner_with_missing_artifact_is_reported() -> None:
    """The permission expires the moment its owning task is marked complete.

    Built synthetically rather than aimed at whichever module happens to be
    unbuilt. Every promised artifact now exists, so a test depending on one
    staying missing would depend on the project never finishing.
    """
    absent = "packages/analytics_query/src/analytics_query/never_built.py"
    owner = "999"
    assert not (REPO / absent).exists()

    real_promised = dict(PROMISED[F002])
    real_states = dict(TASK_STATES[F002])
    try:
        PROMISED[F002][absent] = owner

        TASK_STATES[F002] = {**real_states, owner: False}
        assert not missing_paths(f"`{absent}`", PLAN_002), (
            "an open owning task must permit its promised path"
        )

        TASK_STATES[F002] = {**real_states, owner: True}
        assert missing_paths(f"`{absent}`", PLAN_002) == [absent], (
            "a completed task must not excuse a missing artifact"
        )
    finally:
        PROMISED[F002].clear()
        PROMISED[F002].update(real_promised)
        TASK_STATES[F002] = real_states


def test_mutation_broken_relative_link_is_reported() -> None:
    """The link rule must reject a target that does not exist."""
    assert broken_links("[nowhere](./no-such-document.md)", PLAN_002) == [
        "[nowhere](./no-such-document.md)"
    ]
    assert not broken_links("[spec](./spec.md)", PLAN_002)


def test_mutation_one_feature_cannot_excuse_anothers_missing_file() -> None:
    """A 002 promise must not permit a missing path cited from a 001 artifact."""
    absent = "packages/analytics_query/src/analytics_query/never_built.py"
    owner = "999"
    origin_001 = SPECS / F001 / "plan.md"
    assert _owning_feature(origin_001) == F001

    real_promised = dict(PROMISED[F002])
    real_states = dict(TASK_STATES[F002])
    try:
        PROMISED[F002][absent] = owner
        TASK_STATES[F002] = {**real_states, owner: False}

        assert not missing_paths(f"`{absent}`", PLAN_002), "002 permits its own promise"
        assert missing_paths(f"`{absent}`", origin_001) == [absent], (
            "a 002 promise must not excuse a path cited from 001"
        )
    finally:
        PROMISED[F002].clear()
        PROMISED[F002].update(real_promised)
        TASK_STATES[F002] = real_states


def test_creating_a_promised_artifact_removes_the_need_for_its_permission() -> None:
    """`contracts/reason_codes.py` and `contracts/matrix.py` were the original case.

    They were cited by `002`'s plan before they existed, and were permitted only
    because T013 and T020 declared them and remained open. Phase 3 created them,
    so they now resolve on their own — which is the designed end state: the
    permission is not withdrawn by hand, it simply stops being consulted.
    """
    for path, owner in (
        ("packages/analytics_query/src/analytics_query/contracts/reason_codes.py", "013"),
        ("packages/analytics_query/src/analytics_query/contracts/matrix.py", "020"),
    ):
        assert PROMISED[F002].get(path) == owner, f"{path} must be declared by T{owner}"
        assert (REPO / path).exists(), f"{path} was promised by T{owner} and must exist"
        assert TASK_STATES[F002][owner] is True, f"T{owner} produced it and must be complete"
        assert not missing_paths(f"`{path}`", PLAN_002)


def _artifact_exists(feature: str, path: str) -> bool:
    """Resolution goes through the same root expansion citations use.

    A task list may declare a path package-relative while the file lives under a
    package root, and joining naively against the repository root would report a
    file that is plainly there.
    """
    origin = SPECS / feature / "tasks.md"
    return any(option.exists() for option in _candidates(path, origin))


def test_no_permission_is_outstanding_now_that_every_task_is_complete() -> None:
    """The mechanism's terminal state, applied per feature rather than repo-wide.

    A permission outliving its task was always the defect being guarded against.
    Two claims express that, and they are deliberately separated because they
    hold at different times:

    * **Always, for every feature.** No permission may be held open by a
      completed task or by anything that is not an open executable task. That is
      :func:`outstanding_permissions`, and progress never excuses it.
    * **Once a feature has finished.** When every executable task of a feature is
      complete, the stronger claim applies: no permission may remain outstanding
      at all, because there is no longer an open task to justify one.

    The assertion was previously written repo-wide, which silently assumed the
    repository as a whole was finished. It was introduced at `002`'s terminal
    validation, when that happened to be true. It stopped being true the moment a
    third feature entered planning — not because anything regressed, but because
    an in-progress feature legitimately has open tasks promising files that do
    not exist yet. Scoping the terminal claim to features that have actually
    finished restores the guard's intent without weakening it: `001` and `002`
    still have to satisfy it in full, and nothing about exact path matching,
    declared-path-only permission, or expiry changes.
    """
    for feature in sorted(FEATURES):
        executable = EXECUTABLE_TASK_STATES[feature]
        faults = outstanding_permissions(
            PROMISED[feature], executable, lambda p, f=feature: _artifact_exists(f, p)
        )
        assert not faults, (
            f"{feature}: permissions no open executable task can justify: "
            f"{[(kind, f'T{task}', path) for kind, task, path in faults]}"
        )

        if not feature_is_complete(executable):
            continue

        remaining = sorted(
            f"T{owner} {path}"
            for path, owner in PROMISED[feature].items()
            if not _artifact_exists(feature, path)
        )
        assert not remaining, (
            f"{feature} has completed every executable task, so no permission may "
            f"remain outstanding: {remaining}"
        )


def test_the_terminal_claim_still_binds_the_finished_features() -> None:
    """Scoping must not quietly exempt `001` and `002`.

    If a future edit made `feature_is_complete` too strict, the terminal claim
    would stop applying to anything and the scoping would have become a way out.
    """
    finished = [f for f in FEATURES if feature_is_complete(EXECUTABLE_TASK_STATES[f])]
    for feature in ("001-semantic-catalog", "002-analytics-query"):
        assert feature in finished, f"{feature} must still be held to the terminal claim"


#: Synthetic executable-task ledgers. **No live state.**
#:
#: `feature_is_complete` reads a ``{task: is_complete}`` mapping of **executable** tasks
#: only -- `_executable_task_states` filters `[BLOCKED-EXTERNAL]` records out before it is
#: ever called. So the completion invariants can be stated over synthetic ledgers, which is
#: what makes them permanent rather than true-until-the-next-phase-lands.
_IN_PROGRESS: dict[str, bool] = {"001": True, "002": True, "003": False}
_FINISHED: dict[str, bool] = {"001": True, "002": True, "003": True}
_NOTHING: dict[str, bool] = {}


def test_a_feature_in_progress_is_recognised_as_such() -> None:
    """A feature with open executable work reads as in progress. **Name preserved.**

    The claim is unchanged; where it is measured from is. It used to read `003`'s live
    state, which was a **temporary premise**: true when written and false the moment `003`'s
    terminal task was marked, at which point the test failed while the property it protected
    was satisfied more strongly than before.

    The property was never about `003` being unfinished. Its own docstring said it existed
    so that a checker which stopped distinguishing executable tasks from external records
    would be caught -- because `003`'s records are open, and counting them as work would
    make the feature read as unfinished forever.

    Stated here over synthetic ledgers, in both directions, so it cannot expire again. The
    node ID is kept because `002`'s ADR 0010 regression gate treats a vanished upstream node
    as a semantic change to `001`, and this is test maintenance rather than one.
    """
    assert not feature_is_complete(_IN_PROGRESS)
    assert feature_is_complete(_FINISHED)
    assert not feature_is_complete(_NOTHING)


def test_a_feature_with_no_executable_tasks_is_not_complete() -> None:
    """ "Not started" and "finished" must not collapse into one verdict.

    ``all(())`` is ``True``, so a naive implementation calls an empty feature complete --
    and would then hold it to every completed-feature guard, passing them all vacuously
    because it promised nothing.
    """
    empty: dict[str, bool] = {}
    assert not feature_is_complete(empty)
    assert not feature_is_complete(dict.fromkeys((f"{n:03d}" for n in range(0)), True))


def test_open_external_records_do_not_make_a_feature_incomplete() -> None:
    """**The case that expired the old test, asserted permanently.**

    A feature whose executable work is done is done, whatever its dependency records say.
    Records have no completion path in this repository: counting one as work would make
    every feature with an open dependency read as unfinished forever, and no amount of
    implementation would ever change that.

    Modelled the way the parser actually produces it -- the record numbers are simply
    absent from the executable ledger, because `_executable_task_states` filters them.
    """
    with_records_open = dict(_FINISHED)
    assert feature_is_complete(with_records_open)
    assert "182" not in with_records_open


@pytest.mark.parametrize("record_state", [True, False], ids=["records-checked", "records-open"])
def test_external_record_checkbox_state_cannot_change_the_verdict(record_state: bool) -> None:
    """Neither direction moves it, because records never enter the ledger.

    Parsed from real task text rather than hand-built, so this exercises the filter that
    produces the ledger and not a fixture's idea of one. A record marked complete -- which
    nothing may do, and which `test_no_external_record_is_marked_complete` forbids
    separately -- would still contribute nothing here.
    """
    marker = "X" if record_state else " "
    text = (
        "- [X] T001 Build the thing in `pkg/thing.py`\n"
        "- [X] T002 Build the other thing in `pkg/other.py`\n"
        f"- [{marker}] T182 `[BLOCKED-EXTERNAL]` **D-99 -- an external capability**\n"
        f"- [{marker}] T183 `[BLOCKED-EXTERNAL]` **D-98 -- another one**\n"
    )
    executable = {
        num: state.upper() == "X"
        for state, num, rest in _TASK_LINE.findall(text)
        if _EXTERNAL_RECORD not in rest
    }
    assert executable == {"001": True, "002": True}
    assert feature_is_complete(executable)


def test_a_completed_record_cannot_substitute_for_an_incomplete_task() -> None:
    """A checked record does not fill a gap left by real work.

    The failure this forecloses: a feature reading complete because somebody marked a
    dependency record done. The record is filtered out and the open executable task is
    still open, so the verdict is still "in progress".
    """
    text = (
        "- [X] T001 Build the thing in `pkg/thing.py`\n"
        "- [ ] T002 Build the other thing in `pkg/other.py`\n"
        "- [X] T182 `[BLOCKED-EXTERNAL]` **D-99 -- an external capability**\n"
    )
    executable = {
        num: state.upper() == "X"
        for state, num, rest in _TASK_LINE.findall(text)
        if _EXTERNAL_RECORD not in rest
    }
    assert executable == {"001": True, "002": False}
    assert not feature_is_complete(executable)


def test_a_feature_of_only_external_records_is_not_complete() -> None:
    """Records alone are not work, so a feature made of them has not started.

    Without this, a task list containing nothing but dependency records would produce an
    empty executable ledger and -- under the wrong implementation -- read as finished.
    """
    text = (
        "- [ ] T182 `[BLOCKED-EXTERNAL]` **D-99 -- an external capability**\n"
        "- [X] T183 `[BLOCKED-EXTERNAL]` **D-98 -- another one**\n"
    )
    executable = {
        num: state.upper() == "X"
        for state, num, rest in _TASK_LINE.findall(text)
        if _EXTERNAL_RECORD not in rest
    }
    assert executable == {}
    assert not feature_is_complete(executable)


@pytest.mark.parametrize("feature", finished_features())
def test_every_live_feature_has_finished_its_executable_work(feature: str) -> None:
    """The live half, and it names the feature that fails rather than the count.

    **Scoped to finished features**, mirroring the criterion
    `test_no_permission_is_outstanding_now_that_every_task_is_complete` already applies
    per feature. The previous form ran over every discovered feature, which silently
    assumed every feature in the repository was finished — true when it was written, and
    untrue the moment a fourth feature entered planning with an open ledger. An
    in-progress feature legitimately has open tasks; holding it to a completion claim it
    was never subject to reported a planning state as a regression.

    This half is now a **consistency** check over the finished set: a feature reaching it
    must declare executable tasks and have completed all of them.

    The **binding** half is
    `test_every_completion_bound_feature_has_finished_its_executable_work`, which names
    its features so the scoping cannot become an exemption — see
    `COMPLETION_BOUND_FEATURES`.
    """
    executable = EXECUTABLE_TASK_STATES[feature]
    assert executable, f"{feature} declares no executable tasks"
    assert feature_is_complete(executable), sorted(
        f"T{number}" for number, done in executable.items() if not done
    )


@pytest.mark.parametrize("feature", COMPLETION_BOUND_FEATURES)
def test_every_completion_bound_feature_has_finished_its_executable_work(feature: str) -> None:
    """The binding half. **Named features, so scoping cannot exempt one.**

    `001`, `002` and `003` have finished. Each is named here rather than discovered, so
    un-checking a task cannot remove a feature from the claim — it can only fail it. That
    is the difference between scoping a claim and dropping it.

    A feature is added here when its work is declared finished, which is a deliberate act
    and reviewable as one. `004` is absent while its ledger is open, and adding it before
    its tasks are complete would fail this test rather than pass it.
    """
    assert feature in FEATURES, f"{feature} is bound to the claim but declares no task list"
    executable = EXECUTABLE_TASK_STATES[feature]
    assert executable, f"{feature} declares no executable tasks"
    assert feature_is_complete(executable), sorted(
        f"T{number}" for number, done in executable.items() if not done
    )


def test_feature_003_is_complete_while_its_records_stay_open() -> None:
    """**The live form of the invariant that expired the old assertion.**

    `003` has completed `T001`-`T181` and holds four open `[BLOCKED-EXTERNAL]` records. The
    old test asserted the feature was *in progress*; the same distinction, stated so it
    survives the work finishing, is that the records are open **and** the feature is done.
    """
    feature = "003-nl-analytics-interaction"
    assert feature in FEATURES

    executable = EXECUTABLE_TASK_STATES[feature]
    assert feature_is_complete(executable)
    assert max(executable) == "181"
    assert set(executable) == {f"{n:03d}" for n in range(1, 182)}

    text = (FEATURES[feature] / "tasks.md").read_text(encoding="utf-8")
    records = {
        num: state.upper() == "X"
        for state, num, rest in _TASK_LINE.findall(text)
        if _EXTERNAL_RECORD in rest
    }
    assert set(records) == {"182", "183", "184", "185"}
    # OD-101 (2026-09-02, ciclo 527): T185 fechou pela regra uniforme dos externos —
    # [X] + marcador + "CLOSED 20.." datado na linha; um [X] sem data segue falhando.
    for num, done in records.items():
        if not done:
            continue
        line = next(ln for ln in text.splitlines() if f"T{num} `[BLOCKED-EXTERNAL]`" in ln)
        assert "CLOSED 20" in line, f"T{num} is marked complete without a dated closure"
    assert not set(records) & set(executable), "a record leaked into the executable ledger"


def test_the_open_records_authorize_no_artifact() -> None:
    """And an open record cannot hold an artifact permission open forever.

    A record has no completion path, so a permission it granted could never expire. Asserted
    across every feature, because the rule is not `003`'s.
    """
    for feature, directory in FEATURES.items():
        text = (directory / "tasks.md").read_text(encoding="utf-8")
        for _state, num, description in _TASK_LINE.findall(text):
            if _EXTERNAL_RECORD not in description:
                continue
            assert num not in EXECUTABLE_TASK_STATES[feature]
            for cited in _CODE_PATH.findall(description):
                assert PROMISED[feature].get(_normalise(cited)) != num, (
                    f"{feature} T{num} is a record and must promise nothing"
                )


def test_readiness_state_is_independent_of_implementation_completion() -> None:
    """Finishing the work does not declare a dependency ready, and never can.

    The two are different questions answered by different artifacts: completion is read from
    task checkboxes, readiness from `docs/readiness/`. This asserts the separation holds in
    the direction that matters -- every **completion-bound** feature's executable work is
    done, and every external record is still open.

    The completion half is scoped to `COMPLETION_BOUND_FEATURES` for the reason given in
    `test_every_live_feature_has_finished_its_executable_work`: a feature in planning has
    open work by definition, and its ledger says nothing about whether anyone declared a
    dependency ready. **The record half stays repo-wide**, over every discovered feature,
    because an open record must stay open regardless of how far any feature has progressed.
    """
    assert all(feature_is_complete(EXECUTABLE_TASK_STATES[f]) for f in COMPLETION_BOUND_FEATURES)

    # Emendado no ciclo 513 (2026-09-02, OD-93): o dono passou a fechar externas
    # destravadas uma a uma. A separacao continua a MESMA pergunta: um [X] numa linha de
    # record so existe com fecho DATADO citando a ordem ("CLOSED 20..") — completude nunca
    # e declaracao, e o registro de readiness continua sendo o unico lugar que declara.
    open_records = 0
    for directory in FEATURES.values():
        text = (directory / "tasks.md").read_text(encoding="utf-8")
        for state, _num, rest in _TASK_LINE.findall(text):
            if _EXTERNAL_RECORD in rest:
                if state.upper() == "X":
                    assert "CLOSED 20" in rest, (
                        f"record externo marcado sem fecho datado: {rest[:80]!r}"
                    )
                    continue
                open_records += 1
    assert open_records >= 4, open_records


# --------------------------------------------------------------------------- #
# Adversarial regressions for the completion scoping
#
# Each states one way the scoping could have become an escape hatch, and fails
# on the violation rather than merely passing on the current tree.
# --------------------------------------------------------------------------- #


def test_a_planning_feature_with_open_tasks_is_not_treated_as_finished() -> None:
    """(1) Open work means not finished, and the finished set must exclude it.

    The scoping exists so a feature in planning is not held to a completion claim. It must
    not achieve that by *calling* the feature finished, which would hand it every
    completed-feature guard as well.
    """
    assert not feature_is_complete(_IN_PROGRESS)
    assert not feature_is_complete(_NOTHING)
    assert feature_is_complete(_FINISHED)

    registry = {"planning": _IN_PROGRESS, "shipped": _FINISHED, "unstarted": _NOTHING}
    finished = [name for name, ledger in sorted(registry.items()) if feature_is_complete(ledger)]
    assert finished == ["shipped"], finished

    for feature in finished_features():
        open_tasks = [n for n, done in EXECUTABLE_TASK_STATES[feature].items() if not done]
        assert not open_tasks, f"{feature} is in the finished set with open work: {open_tasks}"


def test_a_completion_bound_feature_must_still_have_finished_everything() -> None:
    """(2) A named feature stays bound, and a regressed ledger fails.

    Driven with a synthetic regression so the rule is shown to fail on a violation rather
    than only to pass today: if `003` un-checked a task, the binding half must reject it.
    """
    assert set(COMPLETION_BOUND_FEATURES) <= set(FEATURES)
    for feature in COMPLETION_BOUND_FEATURES:
        assert feature_is_complete(EXECUTABLE_TASK_STATES[feature]), feature

    regressed = dict(EXECUTABLE_TASK_STATES["003-nl-analytics-interaction"])
    regressed[max(regressed)] = False
    assert not feature_is_complete(regressed), "a regressed ledger must fail the binding claim"


def test_readiness_independence_holds_regardless_of_completion() -> None:
    """(3) Completion is read from checkboxes; readiness from `docs/readiness/`.

    The scoping changed which features the completion half covers. It must not have made
    readiness depend on completion in either direction.

    ## RE-DERIVED on 2026-08-28, and the property is the same one

    It proved independence by asserting that **nothing** was declared — which held while
    nothing was, and stopped holding when the owner declared `d_24` under `OD-18`. A finished
    ledger declaring nothing is EVIDENCE of independence; it is not the property.

    **The property is that the two are read from different places and neither follows the
    other**, and it is now asserted that way: a feature whose ledger is complete may have
    undeclared capabilities, and a declared capability may sit under an open ledger. Written as
    a description of today's world, this node would need editing every time he signs something
    — and a check that needs editing to stay green is a check that stopped measuring.
    """
    assert feature_is_complete(_FINISHED)
    assert not feature_is_complete(_IN_PROGRESS)

    declared = [
        line.strip()
        for record in sorted((REPO / "docs" / "readiness").glob("*.yaml"))
        for line in record.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("declared:") and line.strip() != "declared: false"
    ]

    #: Completion does not imply readiness: features whose executable work is finished still
    #: have capabilities nobody declared. `004`'s ledger is complete and eleven of its twelve
    #: records are undeclared.
    undeclared = [
        line.strip()
        for record in sorted((REPO / "docs" / "readiness").glob("*.yaml"))
        for line in record.read_text(encoding="utf-8").splitlines()
        if line.strip() == "declared: false"
    ]
    assert undeclared, (
        "every capability across every record is declared; readiness would then be "
        "indistinguishable from completion and this node could not tell them apart"
    )

    #: And readiness does not imply completion either: a capability is declared while ledgers
    #: elsewhere are open. Asserted only when something IS declared, so the node stays honest
    #: on a repository where nothing has been signed yet.
    if declared:
        assert not feature_is_complete(_IN_PROGRESS), (
            "a capability is declared and every ledger is complete; the two would be moving "
            "together and this node measures that they do not"
        )

    for feature, directory in FEATURES.items():
        text = (directory / "tasks.md").read_text(encoding="utf-8")
        for state, num, rest in _TASK_LINE.findall(text):
            # Emendado no ciclo 513 (OD-93): um record fechado pelo dono carrega [X] COM
            # fecho datado; a independencia segue medida acima (declared vs completion vem
            # de arquivos diferentes) e um [X] sem fecho falha aqui.
            if _EXTERNAL_RECORD in rest and state.upper() == "X":
                assert "CLOSED 20" in rest, (
                    f"{feature} T{num} is a record marked complete without a dated closure"
                )


def test_the_completion_scope_cannot_hide_a_pending_task_in_a_finished_feature() -> None:
    """(4) No loophole: the bound set is pinned, so un-checking cannot buy an exemption.

    Two ways the scoping could have leaked, both closed here:

    * A feature could drop out of the claim by leaving work open. Closed because
      `COMPLETION_BOUND_FEATURES` is a literal tuple — asserted by reading this module's
      own source, the same way the manual-allowlist rule is asserted.
    * A finished feature could carry an unchecked executable task. Closed because
      membership in the finished set and "has no open executable task" are the same
      predicate, asserted live above and restated over the bound set here.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    assignment = source.split("COMPLETION_BOUND_FEATURES = (", 1)[1].split(")", 1)[0]
    for derived in ("feature_is_complete", "EXECUTABLE_TASK_STATES", "TASK_STATES", "FEATURES"):
        assert derived not in assignment, (
            f"COMPLETION_BOUND_FEATURES must be pinned literals, not derived from {derived}"
        )

    for feature in COMPLETION_BOUND_FEATURES:
        open_tasks = sorted(
            f"T{number}" for number, done in EXECUTABLE_TASK_STATES[feature].items() if not done
        )
        assert not open_tasks, f"{feature} is bound to the claim and has open work: {open_tasks}"
        assert feature in finished_features(), f"{feature} must also read as finished"


# --------------------------------------------------------------------------- #
# Focused regressions for the scoped terminal claim
#
# Driven with synthetic registries so each rule is shown to fail on a real
# violation rather than merely to pass on the current tree.
# --------------------------------------------------------------------------- #


def _present(*paths: str) -> Callable[[str], bool]:
    known = set(paths)
    return lambda path: path in known


def test_completed_feature_with_every_artifact_present_passes() -> None:
    promised = {"pkg/a.py": "001", "pkg/b.py": "002"}
    executable = {"001": True, "002": True}
    exists = _present("pkg/a.py", "pkg/b.py")
    assert feature_is_complete(executable)
    assert outstanding_permissions(promised, executable, exists) == []


def test_completed_feature_with_a_promised_artifact_missing_fails() -> None:
    promised = {"pkg/a.py": "001", "pkg/gone.py": "002"}
    executable = {"001": True, "002": True}
    faults = outstanding_permissions(promised, executable, _present("pkg/a.py"))
    assert faults == [("completed", "002", "pkg/gone.py")]


def test_in_progress_feature_with_a_missing_artifact_promised_by_an_open_task_passes() -> None:
    promised = {"pkg/done.py": "001", "pkg/todo.py": "002"}
    executable = {"001": True, "002": False}
    assert not feature_is_complete(executable)
    assert outstanding_permissions(promised, executable, _present("pkg/done.py")) == []


def test_in_progress_feature_with_an_undeclared_missing_artifact_fails() -> None:
    """An undeclared path is caught by the citation guard, not by permission.

    Exercised against the real tree so the two halves are shown to meet: `003`
    is in progress, and a path it never declares is still reported missing.
    """
    feature = "003-nl-analytics-interaction"
    if feature not in FEATURES:
        pytest.skip("feature not present")
    origin = FEATURES[feature] / "tasks.md"
    undeclared = "packages/analytics_interaction/src/analytics_interaction/not_declared.py"
    assert undeclared not in PROMISED[feature]
    assert missing_paths(f"`{undeclared}`", origin) == [undeclared]


def test_a_completed_task_cannot_authorize_a_missing_artifact() -> None:
    """The rule holds inside an unfinished feature too, not only at the end."""
    promised = {"pkg/broken.py": "001", "pkg/todo.py": "002"}
    executable = {"001": True, "002": False}
    faults = outstanding_permissions(promised, executable, _present())
    assert faults == [("completed", "001", "pkg/broken.py")]


def test_external_records_cannot_authorize_implementation_artifacts() -> None:
    """A record is not work, so it neither promises nor excuses.

    Both halves are checked: a number that is not an executable task cannot hold
    a permission open, and a real `[BLOCKED-EXTERNAL]` line contributes no
    promise even when its description cites a path.
    """
    promised = {"pkg/from_a_record.py": "099"}
    executable = {"001": False}
    faults = outstanding_permissions(promised, executable, _present())
    assert faults == [("unowned", "099", "pkg/from_a_record.py")]

    for feature, directory in FEATURES.items():
        text = (directory / "tasks.md").read_text(encoding="utf-8")
        for _state, num, description in _TASK_LINE.findall(text):
            if _EXTERNAL_RECORD not in description:
                continue
            assert num not in EXECUTABLE_TASK_STATES[feature], (
                f"{feature} T{num} is a record and must not be an executable task"
            )
            for cited in _CODE_PATH.findall(description):
                assert PROMISED[feature].get(_normalise(cited)) != num, (
                    f"{feature} T{num} is a record and must promise nothing"
                )


#: A synthetic promise, used only by the exactness regressions below.
#:
#: Path, task number and feature are all invented. **Nothing here depends on the state of
#: any real task or on any real artifact being absent** — which is the whole point.
#:
#: The previous version of these tests harvested their example from live data: they
#: required an open task promising a `.py` file that did not yet exist, and asserted that
#: requirement as a precondition. It held only while some feature still had unbuilt Python
#: work outstanding. When `003`'s remaining open tasks promised nothing but Markdown, the
#: precondition failed and reported a missing fixture as a broken rule.
#:
#: Synthetic data prevents another self-expiring fixture. The rule under test --
#: `_permitted_missing`'s exact-equality matching -- has nothing to do with whether a real
#: permission happens to be outstanding, so the fixture must not either.
#:
#: The path sits under a **real** derived root so `_repo_relative_candidates` expands the
#: citation exactly as it does in production; only the leaf is invented, and it is asserted
#: absent so a future file of that name cannot make these tests pass for the wrong reason.
_SYNTHETIC_FEATURE = "003-nl-analytics-interaction"
_SYNTHETIC_ROOT = "packages/analytics_interaction/src/analytics_interaction"
_SYNTHETIC_PATH = f"{_SYNTHETIC_ROOT}/_exactness_probe.py"

#: An open executable task id no feature uses. Written as text, like every other key in
#: the registry, and far above any real id so it cannot collide with one.
_SYNTHETIC_OPEN_TASK = "901"
_SYNTHETIC_DONE_TASK = "902"

#: A number that is a `[BLOCKED-EXTERNAL]` record rather than executable work: present in
#: `TASK_STATES` and absent from `EXECUTABLE_TASK_STATES`, which is exactly the shape a real
#: record has.
_SYNTHETIC_RECORD_TASK = "903"


@pytest.fixture
def synthetic_promise(monkeypatch: pytest.MonkeyPatch) -> str:
    """Register one synthetic promised path owned by one synthetic **open** task.

    Injected through the module-level registries the production helper already reads, so
    the regressions below exercise `missing_paths` and `_permitted_missing` unchanged
    rather than a re-implementation of them.

    ``monkeypatch.setitem`` on the nested dicts: the registries are shared module state, and
    a test that mutated them directly would leak a fabricated permission into every later
    test in the session.
    """
    assert not (REPO / _SYNTHETIC_PATH).exists(), (
        f"{_SYNTHETIC_PATH} exists; the exactness probe must name a file that does not"
    )
    assert _SYNTHETIC_FEATURE in FEATURES

    monkeypatch.setitem(PROMISED[_SYNTHETIC_FEATURE], _SYNTHETIC_PATH, _SYNTHETIC_OPEN_TASK)
    monkeypatch.setitem(TASK_STATES[_SYNTHETIC_FEATURE], _SYNTHETIC_OPEN_TASK, False)
    monkeypatch.setitem(EXECUTABLE_TASK_STATES[_SYNTHETIC_FEATURE], _SYNTHETIC_OPEN_TASK, False)
    return _SYNTHETIC_PATH


def _origin() -> Path:
    """The document a citation is read from. Its feature grants the permission."""
    return FEATURES[_SYNTHETIC_FEATURE] / "tasks.md"


# --- 1. the exact promised path is permitted while its task is open --------------


def test_an_exact_promised_path_is_permitted_while_its_task_is_open(
    synthetic_promise: str,
) -> None:
    """The control. Without it, every refusal below could mean nothing is ever permitted."""
    assert missing_paths(f"`{synthetic_promise}`", _origin()) == []
    assert _permitted_missing(synthetic_promise, _origin())


def test_exact_path_matching_remains_mandatory(synthetic_promise: str) -> None:
    """The rule, stated compactly in one place. **Name preserved deliberately.**

    This node existed before the correction and its assertion is unchanged in substance:
    a genuinely promised path is permitted, and every near miss of it is not. What changed
    is where the example comes from — synthetic data instead of a harvested live promise.

    The name is kept so the node ID survives. `002`'s ADR 0010 regression gate treats a
    vanished upstream node as a semantic change to `001`, and a rename here would read as
    one. The focused regressions below diagnose *which* variant leaked; this one is the
    single line that says the rule holds.
    """
    assert missing_paths(f"`{synthetic_promise}`", _origin()) == []
    for near in _variants(synthetic_promise).values():
        assert missing_paths(f"`{near}`", _origin()) == [near], (
            f"{near} must not inherit the permission granted to {synthetic_promise}"
        )


# --- 2-5. every near miss is refused -------------------------------------------


def _variants(exact: str) -> dict[str, str]:
    """Near misses of a promised path, each keeping an extension and a separator.

    Each must still be *extracted* as a citation by `_CODE_PATH` rather than skipped, or the
    assertion would pass because nothing was checked.
    """
    head, _, tail = exact.rpartition("/")
    stem, _, suffix = tail.rpartition(".")
    parent, _, folder = head.rpartition("/")
    return {
        "sibling-filename": f"{head}/{stem}2.{suffix}",
        "prefix-variant": f"{head}/x{stem}.{suffix}",
        "suffix-variant": f"{head}/{stem}_extra.{suffix}",
        "near-identical-directory": f"{parent}/{folder}s/{tail}",
        "different-root": f"unrelated/{exact}",
        "different-extension": f"{head}/{stem}.yaml",
        "trailing-separator-form": f"{head}/sub/{tail}",
    }


@pytest.mark.parametrize("kind", sorted(_variants(_SYNTHETIC_PATH)))
def test_no_near_miss_inherits_the_permission(kind: str, synthetic_promise: str) -> None:
    """**The rule.** Exact equality, so a typo cannot ride on somebody else's permission.

    Sibling name, prefix, suffix, near-identical directory, different root and different
    extension -- each is one edit from a genuinely promised path, and each is a different
    file. A fuzzy match here would excuse a missing artifact nobody promised.
    """
    near = _variants(synthetic_promise)[kind]
    assert _CODE_PATH.findall(f"`{near}`") == [near], "the variant was not extracted as a citation"
    assert missing_paths(f"`{near}`", _origin()) == [near], (
        f"{near} must not inherit the permission granted to {synthetic_promise}"
    )
    assert not _permitted_missing(near, _origin())


def test_a_normalised_near_match_is_still_a_near_match(synthetic_promise: str) -> None:
    """Leading slashes and backslashes normalise; the *name* does not.

    `_normalise` exists so a citation written with a leading slash or Windows separators
    compares equal to the promised key. It must not also make a different filename compare
    equal -- normalisation is spelling, not identity.
    """
    head, _, tail = synthetic_promise.rpartition("/")
    stem, _, suffix = tail.rpartition(".")

    # Same file, different spelling: permitted.
    assert missing_paths(f"`/{synthetic_promise}`", _origin()) == []

    # Different file, same spelling conventions: refused.
    for near in (f"/{head}/{stem}2.{suffix}", f"/{head}/{stem}.yaml"):
        assert missing_paths(f"`{near}`", _origin()) == [near.lstrip("/")] or missing_paths(
            f"`{near}`", _origin()
        ) == [near], near


# --- 6. a completed task's permission expires ----------------------------------


def test_a_completed_synthetic_task_grants_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """**The original defect this module was written for**, on synthetic data.

    A permission is excused only *while* its task is open. Once the task is complete and the
    artifact still is not there, the permission has outlived the work -- and the citation
    must be reported missing.
    """
    assert not (REPO / _SYNTHETIC_PATH).exists()
    monkeypatch.setitem(PROMISED[_SYNTHETIC_FEATURE], _SYNTHETIC_PATH, _SYNTHETIC_DONE_TASK)
    monkeypatch.setitem(TASK_STATES[_SYNTHETIC_FEATURE], _SYNTHETIC_DONE_TASK, True)
    monkeypatch.setitem(EXECUTABLE_TASK_STATES[_SYNTHETIC_FEATURE], _SYNTHETIC_DONE_TASK, True)

    assert not _permitted_missing(_SYNTHETIC_PATH, _origin())
    assert missing_paths(f"`{_SYNTHETIC_PATH}`", _origin()) == [_SYNTHETIC_PATH]

    faults = outstanding_permissions(
        {_SYNTHETIC_PATH: _SYNTHETIC_DONE_TASK},
        {_SYNTHETIC_DONE_TASK: True},
        lambda _path: False,
    )
    assert faults == [("completed", _SYNTHETIC_DONE_TASK, _SYNTHETIC_PATH)]


# --- 7. an external record authorizes nothing ----------------------------------


def test_a_blocked_external_record_grants_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A record is not work, so it can neither promise an artifact nor excuse one.

    Modelled at its real shape: present in `TASK_STATES` and **absent** from
    `EXECUTABLE_TASK_STATES`, because `_executable_task_states` filters records out. A
    record left in the permission mechanism would hold an excuse open forever -- it has no
    completion path, so its permission could never expire.
    """
    monkeypatch.setitem(TASK_STATES[_SYNTHETIC_FEATURE], _SYNTHETIC_RECORD_TASK, False)
    assert _SYNTHETIC_RECORD_TASK not in EXECUTABLE_TASK_STATES[_SYNTHETIC_FEATURE]

    faults = outstanding_permissions(
        {_SYNTHETIC_PATH: _SYNTHETIC_RECORD_TASK},
        dict(EXECUTABLE_TASK_STATES[_SYNTHETIC_FEATURE]),
        lambda _path: False,
    )
    assert faults == [("unowned", _SYNTHETIC_RECORD_TASK, _SYNTHETIC_PATH)]


def test_no_real_record_promises_an_artifact() -> None:
    """And the live registries agree: `_promised_artifacts` skips every record.

    The synthetic case above proves the *mechanism* rejects a record. This proves no real
    record reached the registry in the first place, which is the stronger property.
    """
    for feature, directory in FEATURES.items():
        text = (directory / "tasks.md").read_text(encoding="utf-8")
        for _state, num, description in _TASK_LINE.findall(text):
            if _EXTERNAL_RECORD not in description:
                continue
            for cited in _CODE_PATH.findall(description):
                assert PROMISED[feature].get(_normalise(cited)) != num, (
                    f"{feature} T{num} is a record and must promise nothing"
                )


# --- 8. an undeclared path is refused ------------------------------------------


def test_an_undeclared_path_is_refused(synthetic_promise: str) -> None:
    """A path nobody promised has no permission to inherit, near miss or not."""
    undeclared = f"{_SYNTHETIC_ROOT}/_never_promised_at_all.py"
    assert not (REPO / undeclared).exists()
    assert undeclared != synthetic_promise
    assert missing_paths(f"`{undeclared}`", _origin()) == [undeclared]
    assert not _permitted_missing(undeclared, _origin())


# --- the live guard remains, separately ---------------------------------------


def test_the_live_repository_guard_still_passes_independently() -> None:
    """**The synthetic tests replace the expired fixture, not the live check.**

    Every feature's real promises are still checked against its real task states and its
    real artifacts, with no synthetic data in scope: this test takes no fixture and patches
    nothing. A synthetic suite that had quietly replaced the repository-wide guard would
    pass while nothing checked the repository.
    """
    for feature in FEATURES:
        faults = outstanding_permissions(
            PROMISED[feature],
            EXECUTABLE_TASK_STATES[feature],
            lambda path, name=feature: _artifact_exists(name, path),
        )
        assert faults == [], (feature, faults)


def test_the_synthetic_probe_leaked_into_no_registry() -> None:
    """`monkeypatch` unwound, so no fabricated permission survives into another test.

    Ordered last by name for legibility rather than for correctness -- pytest tears the
    fixture down after each test, and this asserts that teardown actually happened.
    """
    assert _SYNTHETIC_PATH not in PROMISED[_SYNTHETIC_FEATURE]
    assert _SYNTHETIC_OPEN_TASK not in TASK_STATES[_SYNTHETIC_FEATURE]
    assert _SYNTHETIC_DONE_TASK not in TASK_STATES[_SYNTHETIC_FEATURE]
    assert _SYNTHETIC_RECORD_TASK not in TASK_STATES[_SYNTHETIC_FEATURE]
