"""Run every CI workflow in ``.github/workflows`` on this machine, before spending an Actions minute.

**It reads `.github/workflows` and derives the commands.** It does not carry a copy of them. A second
list maintained by hand is a list that lies the day a workflow changes, and asserting something
without resolving it against the artefact is the exact class three review cycles closed here.

**And this prose used to say "six" — F136.** A seventh workflow was added and five sentences here
went on asserting six, one of them the merge criterion below. The printed summary had already been
made derived, so the count that a reader *ran* was right while the count they *read* was wrong, which
is worse than both being wrong: the stale one reads as confirmed. **The fix is not six becoming
seven** — that ages again on the eighth. **Prose states no count at all**, and the one place that
needs a number derives it from the directory at runtime.

**This is NOT the gate.** The evidence a merge requires is **one green run per workflow in
`.github/workflows`**, produced by a third party in a clean environment. This tells you whether you
broke something *before* you spend the minutes; it certifies nothing, because whoever writes a change
is not who certifies it.

Two measured facts force adaptation rather than verbatim execution, and both are reported rather than
hidden:

* the steps invoke ``../../.venv/bin/python`` — a **Linux** path. On Windows the interpreter is
  ``.venv/Scripts/python.exe``, so a verbatim run fails on the path alone;
* one harness step runs ``python -m venv .venv``, and executing that here would **recreate the
  virtualenv the running bot is using**. Environment construction is skipped for that reason.

Usage:
    python tools/local-ci/run_local_ci.py                 # every workflow in the directory
    python tools/local-ci/run_local_ci.py harness catalog  # by name
    python tools/local-ci/run_local_ci.py --list           # what would run, without running
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"

#: The workflows are `bash`, and this refuses rather than falling back to another shell: a run that
#: silently used `cmd.exe` would report failures that are the shell's, not the code's.
BASH = shutil.which("bash") or ""

#: A step whose command matches one of these builds the environment rather than checking the code.
#: Skipped, and every skip is named in the report — a silent skip would turn "they all passed
#: locally" into a claim about steps that never ran.
ENVIRONMENT_MARKERS = ("python -m venv", "pip install", "python -m pip")

#: A step whose command needs the GitHub runner: a `${{ }}` expression only Actions expands, or a
#: variable only the runner sets. **Checked BEFORE the environment markers, and the order matters.**
#: `nl-analytics`'s node-ID preservation step creates a baseline virtualenv *and* reads
#: `${{ steps.baseline.outputs.sha }}` — classifying it as "builds the environment" would file a real
#: regression check under the wrong reason, and a wrong label that reads as true is worse than a
#: missing one. This category exists because that mislabel happened here first.
RUNNER_MARKERS = (
    "${{",
    "$RUNNER_TEMP",
    "$GITHUB_WORKSPACE",
    "$GITHUB_OUTPUT",
    "$GITHUB_ENV",
    #: `S-62`, 2026-09-07. Fora do runner esta variavel vem VAZIA e o `>>` falha com rc=1 e
    #: *No such file or directory* -- medido. Sem ela aqui, um passo que so escrevesse no
    #: GITHUB_PATH seria arquivado como vermelho-de-CODIGO, que e o mislabel que esta categoria
    #: existe para evitar. Nota de ordem: `classify` testa esta tupla ANTES da do ambiente,
    #: entao o passo do venv da `every-package.yml` passa daqui em diante a ser recusado por
    #: este marcador em vez do do venv. As duas respostas significam SALTADO, e e a recusa --
    #: nao a etiqueta -- que impede `python -m venv` de esmagar o .venv de quem desenvolve.
    "$GITHUB_PATH",
)

#: **The only hand-maintained list in this file, and it is here because it cannot be derived.**
#: These steps assert something about the CI RUNNER rather than about the code — that the interpreter
#: is the declared floor. Measured: the runner is pinned to 3.12 and this machine's virtualenv is
#: 3.13.2, so the step fails here for a true reason that says nothing about the change. Reported in
#: its own column instead of being folded into code failures, because a red that means "this machine
#: is not the runner" and a red that means "you broke something" must not add up to one number.
#: Matched on the step's exact name, so a renamed or new step lands in code failures rather than
#: quietly inheriting this exemption.
CI_ENVIRONMENT_ASSERTIONS = frozenset(
    {"Confirm the interpreter matches the declared floor"}
)

#: The Linux interpreter path the workflows use, and what it is on this platform.
POSIX_INTERPRETER = "/.venv/bin/python"
WINDOWS_INTERPRETER = "/.venv/Scripts/python.exe"


#: What a pytest run says about tests it did not run. Matched on the summary line, and the reasons
#: are read from the `SKIPPED [n] path: reason` lines when the step asked for them.
_TESTS_SKIPPED = re.compile(r"(\d+) skipped")
_SKIP_REASON = re.compile(r"^SKIPPED \[(\d+)\] (.+)$", re.M)


def tests_skipped_in(output: str) -> int:
    """How many TESTS a passing step did not run.

    **This is the rule of `verdict` descending one level**, and it took three cycles to arrive.
    The runner already refused to print `VERDE` when a STEP was skipped, for the right reason
    written in its own docstring — *a skip makes a label assert more than was measured*. But a step
    whose pytest skipped twenty-one tests **exits zero**, and the runner read that step as measured
    in full.

    Measured 2026-08-31: the application-default credential expired mid-cycle and turned
    `anomaly_investigation` from **381 passed / 3 failed** into **376 passed / 8 skipped**. Zero
    failures everywhere, twenty-one tests not run, and the three reds that hold this repository's
    push are among the ones that vanished. **It is the third time that credential has done this** —
    on 2026-08-30 it hid four reds of `006` and became `OD-22`. A defect that returns a third time
    is not luck; it is a missing instrument.
    """
    return sum(int(count) for count in _TESTS_SKIPPED.findall(output))


def skip_reasons_in(output: str) -> list[str]:
    """The reasons a step printed, when it was asked with `-rs`. Empty is not proof of none."""
    return [f"{count} x {where}" for count, where in _SKIP_REASON.findall(output)]


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "failed" | "skipped" | "ci-environment"
    detail: str = ""
    #: TESTS the step's own pytest did not run, even though the step exited zero.
    tests_skipped: int = 0


@dataclass
class WorkflowResult:
    name: str
    steps: list[StepResult] = field(default_factory=list)
    translated: int = 0

    @property
    def failed(self) -> StepResult | None:
        return next((s for s in self.steps if s.status == "failed"), None)

    @property
    def counts(self) -> tuple[int, int, int, int]:
        ok = sum(1 for s in self.steps if s.status == "ok")
        skipped = sum(1 for s in self.steps if s.status == "skipped")
        failed = sum(1 for s in self.steps if s.status == "failed")
        environment = sum(1 for s in self.steps if s.status == "ci-environment")
        return ok, skipped, failed, environment

    @property
    def verdict(self) -> str:
        """`F117`. **`VERDE` only when nothing was skipped**, because in CI vocabulary green means
        *everything ran and passed* — and this runner cannot run every step. Saying `VERDE` beside four
        skips claimed more than was measured, which is the same family as `F114`–`F116`: a label that
        asserts more than the instrument reached. A wrong label that reads as true is worse than a
        missing one.
        """
        _ok, skipped, failed, environment = self.counts
        if failed:
            return "VERMELHO"
        #: **And the same rule one level down**: a step that exited zero having skipped tests did
        #: not measure what its label claims. It is not a failure — a legitimate skip exists — but
        #: an INVISIBLE skip must not exist.
        if skipped or environment or self.tests_skipped:
            return "PARCIAL"
        return "VERDE"

    @property
    def tests_skipped(self) -> int:
        """Tests not run inside steps that exited zero."""
        return sum(step.tests_skipped for step in self.steps)


def expand_env_expressions(text: str, env: dict[str, str]) -> str:
    """Expand ``${{ env.NAME }}`` from the workflow's own ``env:`` block, and nothing else.

    Only this one expression form. Anything else a workflow can write — `steps.*.outputs`,
    `github.sha`, `runner.*` — is left untouched **on purpose**, so `classify` still sees a `${{` and
    files the step under "needs the GitHub runner" instead of running it against a value we invented.
    """
    for name, value in env.items():
        for spelling in (f"${{{{ env.{name} }}}}", f"${{{{env.{name}}}}}"):
            text = text.replace(spelling, value)
    return text


def translate(command: str) -> tuple[str, bool]:
    """Point the interpreter at this platform's path, and say whether it had to."""
    if platform.system() == "Windows" and POSIX_INTERPRETER in command:
        return command.replace(POSIX_INTERPRETER, WINDOWS_INTERPRETER), True
    return command, False


def classify(command: str) -> str | None:
    """Why this step cannot run here, or ``None`` when it can.

    Runner first: a step can be both, and the honest reason is the one that would still stop it if
    the other were solved.
    """
    if any(marker in command for marker in RUNNER_MARKERS):
        return "needs the GitHub runner"
    if any(marker in command for marker in ENVIRONMENT_MARKERS):
        return "builds the environment"
    return None


def load_workflow(
    path: Path,
) -> tuple[str, dict[str, Any], list[dict[str, Any]], str | None]:
    """Name, env, steps, and the job-level default working directory.

    **That last one is why the harness failed on the first real run.** `harness.yml` sets
    ``defaults.run.working-directory`` on the job, and reading only per-step values ran its commands
    from the repository root, where ``../../.venv`` points outside the repository. A step-level value
    still wins over it, exactly as Actions resolves it.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    name = str(document.get("name") or path.stem)
    env = {str(k): str(v) for k, v in (document.get("env") or {}).items()}
    default_directory: str | None = (
        (document.get("defaults") or {}).get("run") or {}
    ).get("working-directory")
    jobs = document.get("jobs") or {}
    steps: list[dict[str, Any]] = []
    for job in jobs.values():
        env.update({str(k): str(v) for k, v in (job.get("env") or {}).items()})
        job_default = ((job.get("defaults") or {}).get("run") or {}).get(
            "working-directory"
        )
        if job_default:
            default_directory = str(job_default)
        steps.extend(job.get("steps") or [])
    return name, env, steps, default_directory


def run_workflow(path: Path, *, dry_run: bool) -> WorkflowResult:
    name, env, steps, default_directory = load_workflow(path)
    result = WorkflowResult(name=name)
    # The workflows call a bare `python`, which on the runner is the interpreter `setup-python`
    # installed with the packages already `pip install -e`'d. Here that would resolve to the global
    # interpreter, which has none of them — measured: `semantic_catalog` was not importable. So the
    # repository's own virtualenv goes to the front of PATH. Declared, like the interpreter path
    # translation, rather than assumed.
    venv_bin = REPO / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin")
    environment = {
        **os.environ,
        **env,
        "PATH": f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }

    for step in steps:
        command = step.get("run")
        if not command:
            # `uses:` — checkout and interpreter setup. This machine already has both.
            continue
        label = str(step.get("name") or command.strip().splitlines()[0])[:70]
        command = expand_env_expressions(command, env)

        if reason := classify(command):
            result.steps.append(StepResult(label, "skipped", reason))
            continue

        command, was_translated = translate(command)
        result.translated += int(was_translated)

        if dry_run:
            result.steps.append(StepResult(label, "ok", "not executed (--list)"))
            continue

        step_env = {
            **environment,
            **{str(k): str(v) for k, v in (step.get("env") or {}).items()},
        }
        # The workflows are written for `bash`: `set -uo pipefail`, `$(...)`, `wc`, `grep`. On Windows
        # `shell=True` would hand them to `cmd.exe`, which fails on the first construct — so bash is
        # invoked explicitly rather than assumed.
        # And `working-directory` is relative to the repository, not to this process.
        directory = step.get("working-directory") or default_directory
        if directory:
            directory = expand_env_expressions(str(directory), env)
            if "${{" in directory or not (REPO / directory).is_dir():
                result.steps.append(
                    StepResult(
                        label, "skipped", f"working-directory nao resolve: {directory}"
                    )
                )
                continue
        completed = subprocess.run(  # noqa: S603 -- the command comes from the repo's own workflow
            [BASH, "-c", command],
            cwd=REPO / directory if directory else REPO,
            env=step_env,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            output = completed.stdout + completed.stderr
            skipped_tests = tests_skipped_in(output)
            reasons = skip_reasons_in(output)
            detail = "; ".join(reasons) if reasons else ""
            if skipped_tests and not detail:
                detail = "o passo nao pediu -rs, entao os motivos nao foram lidos"
            result.steps.append(
                StepResult(label, "ok", detail, tests_skipped=skipped_tests)
            )
            continue

        tail = (completed.stdout + completed.stderr).strip().splitlines()
        status = "ci-environment" if label in CI_ENVIRONMENT_ASSERTIONS else "failed"
        result.steps.append(StepResult(label, status, "\n".join(tail[-12:])))
        if status == "ci-environment":
            # Not a stop: this red says "this machine is not the runner", so the steps after it are
            # still worth running. Folding it into a stop would hide every check behind it.
            continue
        # CI stops the job at the first failure; so does this, or the report would describe a run
        # nobody would have got.
        break

    return result


def main() -> int:
    # Read once, and everything below counts from this -- the help string, the run, and the
    # closing sentence. Two globs would be two answers the day they disagree.
    available = sorted(WORKFLOWS.glob("*.yml"))

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "workflows",
        nargs="*",
        # Derived, never a literal -- F136. This said "all six" while the directory held
        # seven. A number written here ages the moment a workflow is added, and the reader
        # has no way to tell a stale one from a true one.
        help=f"file stems; default is all {len(available)} in {WORKFLOWS.relative_to(REPO)}",
    )
    parser.add_argument(
        "--list", action="store_true", help="show what would run, without running"
    )
    args = parser.parse_args()

    if not BASH and not args.list:
        print(
            "bash nao encontrado no PATH, e os workflows sao bash. Abortando.",
            file=sys.stderr,
        )
        return 2

    paths = available
    if args.workflows:
        wanted = set(args.workflows)
        paths = [p for p in paths if p.stem in wanted]
        missing = wanted - {p.stem for p in paths}
        if missing:
            print(f"nao existe: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    print(f"lidos de {WORKFLOWS.relative_to(REPO)}: {len(paths)} workflows")
    print(f"plataforma: {platform.system()}\n")

    # **Reported as each workflow finishes, not accumulated for the end.** A full run takes longer
    # than ten minutes, and the first version printed only at the end — so an interrupted run left
    # NOTHING, not even the workflows that had already passed. A report that does not exist is worse
    # than a partial one.
    results: list[WorkflowResult] = []
    red = 0
    partial = 0
    for path in paths:
        r = run_workflow(path, dry_run=args.list)
        results.append(r)
        ok, skipped, failed, environment = r.counts
        verdict = r.verdict
        red += int(verdict == "VERMELHO")
        partial += int(verdict == "PARCIAL")
        not_run = skipped + environment
        suffix = f" -- {not_run} passos NAO rodaram aqui" if not_run else ""
        if r.tests_skipped:
            suffix += (
                f" -- {r.tests_skipped} TESTES pulados dentro de passos que sairam zero"
            )
        print(
            f"[{verdict}{suffix}] {r.name}: {ok} ok, {skipped} pulados, {failed} falhos, "
            f"{environment} de ambiente do CI, {r.translated} traduzidos",
            flush=True,
        )
        for step in r.steps:
            if step.status == "skipped":
                print(f"    pulado: {step.name} ({step.detail})", flush=True)
            elif step.status == "ci-environment":
                print(f"    ambiente do CI, nao o codigo: {step.name}", flush=True)
            elif step.tests_skipped:
                #: **Named, one by one.** A count without the step's name tells nobody where to
                #: look, and a skip nobody can locate is the invisible skip under another name.
                print(
                    f"    {step.tests_skipped} TESTES pulados em: {step.name}"
                    f"{f' ({step.detail})' if step.detail else ''}",
                    flush=True,
                )
        if bad := r.failed:
            print(f"    FALHOU em: {bad.name}", flush=True)
            for line in bad.detail.splitlines():
                print(f"      | {line}", flush=True)

    total_ok = sum(r.counts[0] for r in results)
    total_skipped = sum(r.counts[1] for r in results)
    total_environment = sum(r.counts[3] for r in results)
    total_tests_skipped = sum(r.tests_skipped for r in results)
    total_translated = sum(r.translated for r in results)
    green = len(results) - red - partial
    print(
        f"\n{red} vermelhos | {partial} parciais | {green} verdes  "
        f"(VERDE exige zero passos nao rodados E zero testes pulados)"
    )
    print(
        f"executados {total_ok} | pulados {total_skipped} | ambiente do CI {total_environment} | "
        f"testes pulados {total_tests_skipped} | traduzidos {total_translated}"
    )
    if total_skipped or total_environment:
        print(
            f"NENHUM workflow rodou por inteiro aqui: {total_skipped + total_environment} passos "
            "ficaram de fora, nomeados acima."
        )
    if total_tests_skipped:
        #: The sentence this instrument existed to make impossible, now that it can see one level
        #: down. On 2026-08-31 an expired credential turned three reds into eight skips and every
        #: suite reported zero failures.
        print(
            f"E {total_tests_skipped} TESTES foram pulados dentro de passos que sairam com codigo "
            "zero, nomeados acima. Zero falhas NAO e o mesmo que tudo medido."
        )
    # Derived, never a literal. The sentence said "os seis verdes" until a seventh
    # workflow was added, at which point it was quietly wrong -- and a stale label
    # that reads as true is worse than no label. The count comes from what was read.
    total_workflows = len(results)
    print(
        f"Isto NAO e o portao: a evidencia do merge sao os {total_workflows} verdes no GitHub."
    )
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
