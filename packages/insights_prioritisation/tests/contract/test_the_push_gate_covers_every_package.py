"""Every package with tests is gated by the hook — the `G-1` lesson applied to a gate.

**The defect this closes was measured, not imagined.** `tools/git-hooks/pre-push` named
one package by hand — `anomaly_investigation`, written on the `005` branch and carried
to every branch cut from it. On this branch the gate therefore measured **another
feature's suite and never this one**: a push was blocked over an expired credential
belonging to somebody else's tests, while this package's own tests were never run by any
gate at all.

## This file DRIVES the hook. It does not describe it.

The hook prints its derived list on demand — ``pre-push --list-suites`` — and this
node **runs that** and compares it against what is on disk. A node that re-implemented
the derivation here would pass while the hook's own rule rotted, which is exactly the
shape `G-1` cost the `005` branch a cycle to find: *a check that describes a structure
instead of driving a behaviour*.

**Acceptance, as the reviewer stated it:** remove this branch's package from the derived
coverage and this node must fail. Measured before this file was handed back.

## Absence skips, and a real answer of "no" fails

The hook is a POSIX shell script. On a machine with no `bash` it cannot be asked what it
covers, and reporting that as a coverage hole would be a node going red for something
that is not the thing it guards — the `F135` shape. Missing `bash` skips loudly; a hook
that answers and answers WRONG fails.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
HOOK = REPO / "tools" / "git-hooks" / "pre-push"


def _gated_packages() -> list[str]:
    """What the hook itself says it gates, as repo-relative paths. **Asked, never re-derived.**"""
    if not HOOK.exists():  # pragma: no cover - a checkout without the hook
        pytest.skip("tools/git-hooks/pre-push is not in this checkout; nothing was measured")
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - a machine without a POSIX shell
        pytest.skip("no bash on this machine; the hook could not be asked what it covers")
    result = subprocess.run(
        [bash, str(HOOK), "--list-suites"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"the hook could not list its packages: {result.stderr.strip()[:200]}")
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def _suites_on_disk() -> list[str]:
    """Every directory on disk that has a suite, wherever it lives.

    **Two levels from the root, and neither root is named here either.** The claim is
    about ALL of them: the bot harness lives in `tools/` and was ungated for as long as
    this file only looked under `packages/`, which is a node asserting coverage over half
    the repository.
    """
    return sorted(
        f"{parent.name}/{directory.name}"
        for parent in REPO.iterdir()
        if parent.is_dir() and not parent.name.startswith(".")
        for directory in parent.iterdir()
        if directory.is_dir() and (directory / "tests").is_dir()
    )


def _gated_jobs() -> list[str]:
    """Every job the hook will actually run, asked of the hook.

    `--list-suites` answers the DERIVED half. The gate also runs two steps no derivation
    covers -- the citation guard and the strict type check -- and a node that read only the
    derived half would report full coverage of a list it had seen two thirds of.
    """
    if not HOOK.exists():  # pragma: no cover - a checkout without the hook
        pytest.skip("tools/git-hooks/pre-push is not in this checkout; nothing was measured")
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - a machine without a POSIX shell
        pytest.skip("no bash on this machine; the hook could not be asked what it runs")
    result = subprocess.run(
        [bash, str(HOOK), "--list-jobs"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"the hook could not list its jobs: {result.stderr.strip()[:200]}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def test_the_repository_has_packages_with_tests_to_cover() -> None:
    """**Vacuity guard.** With nothing to cover, every assertion below is trivially true."""
    present = _suites_on_disk()
    assert present, "no package on disk has a tests/ directory; the checks below measure nothing"
    assert len(present) > 1, (
        "only one package has tests, so a hook naming one by hand would look correct here "
        "and this node could not tell the two apart"
    )


def test_every_package_with_tests_is_gated() -> None:
    """The claim, driven off the hook's own answer.

    A package that exists with a suite and is **not** in the hook's list is a package
    whose tests no push ever runs — which is what this branch was living with.
    """
    uncovered = sorted(set(_suites_on_disk()) - set(_gated_packages()))
    assert not uncovered, (
        f"these packages have tests and no push gates them: {uncovered}. The hook derives "
        "its list; a package outside it is a suite nobody runs before a push."
    )


def test_the_two_suites_that_were_ungated_are_gated_now() -> None:
    """**The one the old hook missed, named so the regression cannot be silent.**

    `insights_prioritisation` was invisible to the gate on the branch that owns it. If
    that ever becomes true again, this fails first and by name.
    """
    gated = _gated_packages()
    assert "packages/insights_prioritisation" in gated, (
        "this branch's own package is not gated by the push hook, which is the exact "
        "defect measured in cycle 361"
    )
    assert "apps/telegram-bot" in gated, (
        "the bot harness is not gated by the push hook. It was ungated until cycle 367, "
        "and the node that guards the .env backend declaration lives in it -- a node no "
        "gate runs guards nothing"
    )


def test_the_hook_gates_nothing_that_does_not_exist() -> None:
    """The other direction, and it is not symmetry for its own sake.

    A name in the list with no package behind it would make the hook try to run a suite
    that is not there — and, worse, would let somebody read the list as coverage the
    repository does not have.
    """
    phantom = sorted(set(_gated_packages()) - set(_suites_on_disk()))
    assert not phantom, f"the hook names packages that do not exist here: {phantom}"


def test_the_cross_artifact_gate_was_not_dropped() -> None:
    """**Widening the gate must not quietly narrow it somewhere else.**

    The citation guard has caught a bad citation twice. It is a single named test rather
    than a package suite, so no derivation covers it, and it has to survive the change
    that made everything else derived.
    """
    body = HOOK.read_text(encoding="utf-8")
    assert "test_cross_artifact_links.py" in body, (
        "the cross-artifact citation guard is no longer run by the push hook"
    )


def test_the_gate_type_checks_and_not_only_tests() -> None:
    """**The gate measured tests and never types, and both were red at once.**

    Measured on 2026-08-27: `run_local_ci.py harness` reported 19 strict `pyright` errors in
    three files this hook had just run green. Nothing was wrong with either measurement --
    they measure different properties. What was wrong is that only one of them ran on a
    push, so *green here* was read as *the code is fine*, for three cycles.

    So a type check is one of the jobs, and this node asks the HOOK for its job list rather
    than reading the file for the word `pyright`: a node that grepped the text would pass on
    a hook that defined the step and never ran it, which is the `G-1` defect -- describing a
    structure instead of driving a behaviour.

    **And the set is compared against the DERIVATION rather than against a number.** This node
    once asserted there was exactly ONE type-check step, which was true for one cycle and
    became false the moment the gate widened to every suite that declares a checker. A count
    written into a node is the same debt as a name written into a gate: re-deriving it is the
    fix, and loosening it to "at least one" would have been the wrong one -- that version
    passes while five suites silently stop being checked.

    The criterion is the suite's own `pyproject.toml`: a suite declaring `[tool.pyright]` is
    type-gated, and one that declares no checker is NOT given one. Both directions are
    asserted, because each fails for a different reason -- a suite dropped from the step is
    coverage lost, and a suite added without a checker is a step that cannot run.
    """
    jobs = _gated_jobs()
    typed = sorted(job.split(":", 1)[1].strip() for job in jobs if job.startswith("strict types:"))
    assert typed, (
        f"no job type-checks anything; the gate measures tests only, and its jobs are {jobs}"
    )
    declaring = sorted(
        suite
        for suite in _suites_on_disk()
        if "[tool.pyright]" in (REPO / suite / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert typed == declaring, (
        f"the gate type-checks {typed}, and the suites that declare a checker are {declaring}; "
        "a suite that declares one and is not checked is coverage nobody has, and a suite "
        "checked without declaring one is a step that cannot run"
    )


def test_every_job_the_gate_runs_is_one_it_can_reach() -> None:
    """A job list is only worth what its entries resolve to.

    The derived suites are covered above. This closes the pair: every job is either one of
    those suites, or one of the named steps -- so a hand-written step appearing here is a
    decision somebody has to make in this file as well.

    **The prefixed kinds are UNWRAPPED rather than skipped**, and the difference is the point:
    `format: packages/nao_existe` would have been waved through by a rule that only looked at
    the prefix. Measured on 2026-09-06 — this node went red when the format jobs arrived,
    which is the node working, and the repair was to teach it the fourth kind instead of
    widening the skip.
    """
    named_steps = {"cross-artifact citations"}
    #: `markers: ` entrou em 2026-09-07 com a `OD-155`: a guarda dos marcadores vivia so na
    #: workflow `harness`, apanhou cinco nos sem marcador que este portao deixou passar durante
    #: quatro commits, e as workflows foram desligadas por ordem dele. Mover a medicao para o
    #: unico instrumento que ainda corre e o que impede a ordem de trocar um vermelho falso por
    #: um cego.
    prefixes = ("strict types: ", "format: ", "lint: ", "markers: ")
    for job in _gated_jobs():
        if job in named_steps:
            continue
        subject = job
        for prefix in prefixes:
            if job.startswith(prefix):
                subject = job[len(prefix) :]
                break
        assert subject in _suites_on_disk(), f"the gate runs {job!r}, which is not on disk"


def test_the_derivation_is_the_hook_s_and_not_a_copy_of_it_here() -> None:
    """**Proof this file drives rather than describes.**

    The list is obtained by executing the hook. If this file computed the rule itself,
    every assertion above would keep passing while the hook gated one package by hand —
    which is precisely how the defect survived.
    """
    body = HOOK.read_text(encoding="utf-8")
    assert "--list-suites" in body, (
        "the hook no longer answers --list-suites, so this file cannot ask it what it "
        "covers and would have to guess"
    )
    assert "gated_suites" in body


def _run_hook(*argumentos: str) -> subprocess.CompletedProcess[str]:
    """Chama o hook e devolve a corrida inteira — quem quiser o código de saída lê dele."""
    if not HOOK.exists():  # pragma: no cover - um checkout sem o hook
        pytest.skip("tools/git-hooks/pre-push nao esta neste checkout; nada foi medido")
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - uma maquina sem shell POSIX
        pytest.skip("nao ha bash nesta maquina; o hook nao pode ser dirigido")
    return subprocess.run(
        [bash, str(HOOK), *argumentos],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _suites_declaring_ruff() -> list[str]:
    """As suítes cujo `pyproject.toml` declara `[tool.ruff]`, lidas do disco.

    Este é o único lugar onde a regra é reescrita fora do hook, e de propósito: um nó que
    perguntasse ao hook *quais* ele formata e depois afirmasse que são essas estaria a
    comparar a resposta dele consigo mesma. A fonte aqui é o arquivo de cada suíte.
    """
    return sorted(
        suite
        for suite in _gated_packages()
        if "[tool.ruff]" in (REPO / suite / "pyproject.toml").read_text(encoding="utf-8")
    )


def test_o_portao_formata_toda_suite_que_declara_o_formatador() -> None:
    """**O buraco que esta fatia fecha** — `OD-134`, 06/09.

    O `ruff` era o único verificador que este portão nunca rodava. Em 06/09 o bot carregava
    sete arquivos que o formatador reescreveria e vinte achados de lint, entrados em 04/09 e
    empurrados **duas vezes por vinte portões verdes** — porque nada aqui olhava. *Verde por
    não medir* é o mesmo defeito que este arquivo já pagou por outro instrumento.

    **O que passou a custar, medido:** dez verificações, entre 453 e 536 ms cada, 4,9 s somados
    em série. Elas andam na onda LEVE, em paralelo com os verificadores de tipo, contra um
    portão que já leva cerca de quinze minutos — abaixo de um por cento.

    **Mutações**, cada uma vermelha num nó diferente, o hook restaurado por `cp` + `cmp`:
    a função de formato trocada por uma que não verifica nada → `1 failed, 10 passed`; os
    trabalhos de formato removidos da lista → `2 failed, 9 passed`; o formato mandado para a
    onda pesada → `1 failed, 10 passed`.
    """
    trabalhos = _gated_jobs()
    formatadas = {job[len("format: ") :] for job in trabalhos if job.startswith("format: ")}
    assert formatadas == set(_suites_declaring_ruff()), (
        "o portao formata um conjunto diferente das suites que declaram o formatador"
    )
    assert formatadas, "nenhuma suite declara [tool.ruff]; o portao novo nao mediria nada"


def test_o_portao_de_formato_BLOQUEIA_um_arquivo_desformatado(tmp_path: Path) -> None:  # noqa: N802
    """**Um portão que nunca foi visto barrar não é portão** — e é isto que o prova.

    Planta uma suíte de mentira com um arquivo que o formatador reescreveria, e dirige a
    MESMA função que o job do push usa (`--format-check`). Vermelho com o arquivo torto,
    verde depois de formatado — os dois sentidos, porque só o verde passaria por acidente
    num portão que não faz nada.

    A suíte vive em `tmp_path` e não na árvore: plantar um arquivo torto no repositório de
    verdade, durante um push de outro agente, é o incidente de 04/09 outra vez.
    """
    suite = tmp_path / "suite_de_mentira"
    suite.mkdir()
    (suite / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 100\ntarget-version = "py312"\n', encoding="utf-8"
    )
    torto = suite / "torto.py"
    #: Duas linhas que o formatador junta numa só. Nada de sintaxe inválida: o que se mede é
    #: o FORMATO, e um arquivo que nem compila mediria outra coisa.
    torto.write_text("x = (\n    1\n)\n", encoding="utf-8")

    vermelho = _run_hook("--format-check", str(suite))
    assert vermelho.returncode != 0, (
        f"o portao aceitou um arquivo desformatado; saida: {vermelho.stdout.strip()[:200]}"
    )

    torto.write_text("x = 1\n", encoding="utf-8")
    verde = _run_hook("--format-check", str(suite))
    assert verde.returncode == 0, (
        f"o portao recusou um arquivo ja formatado; saida: {verde.stdout.strip()[:200]}"
    )


def test_o_portao_LINTA_toda_suite_que_declara_o_ruff() -> None:  # noqa: N802
    """**A segunda metade do `ruff`, e a ordem que a trouxe** — `OD-135`, 06/09.

    O portão de formato entrou em 06/09 NOMEANDO o buraco que deixava: `ruff check` era medido
    pelo CI e à mão e por nada aqui. Nomear em vez de preencher foi deliberado — alargar um
    portão além da ordem que o criou é como um portão deixa de ser dele. Ele deu a ordem, e o
    buraco fecha pela palavra dele.

    **A derivação é UMA SÓ.** O critério do formatador e o do lint é a MESMA linha
    `[tool.ruff]`, então os dois tipos de trabalho saem da mesma função no hook. Uma segunda
    função lendo a mesma declaração seriam duas cópias de uma regra — o defeito sobre o qual
    este arquivo e o hook gastam o seu comprimento a avisar.

    **Medido antes de ligar**, 06/09 12:4x: as dez suítes respondem `All checks passed!`, então
    este portão não bloqueia o próximo push — a mesma medição que o `OD-134` fez antes de
    entregar, e pela mesma razão.
    """
    trabalhos = _gated_jobs()
    lintadas = {job[len("lint: ") :] for job in trabalhos if job.startswith("lint: ")}
    assert lintadas == set(_suites_declaring_ruff()), (
        "o portao linta um conjunto diferente das suites que declaram o ruff"
    )
    assert lintadas, "nenhuma suite declara [tool.ruff]; o portao novo nao mediria nada"
    #: E as duas metades cobrem o MESMO conjunto, que é o que "uma derivação só" quer dizer.
    formatadas = {job[len("format: ") :] for job in trabalhos if job.startswith("format: ")}
    assert lintadas == formatadas, (
        "formato e lint saem de criterios diferentes; a derivacao deixou de ser uma so"
    )


def test_o_portao_de_lint_BLOQUEIA_um_achado(tmp_path: Path) -> None:  # noqa: N802
    """**Um portão que nunca foi visto barrar não é portão** — o mesmo argumento do formato.

    Planta uma suíte de mentira com um achado que o `ruff check` reporta e o `ruff format`
    NÃO vê — um import que ninguém usa, `F401`. A escolha importa: um arquivo torto provaria
    de novo o portão do formato, e o que aqui se afirma é que a metade do LINT morde sozinha.

    Dirige a MESMA função que o job do push usa (`--lint-check`). Vermelho com o achado, verde
    depois de removido — os dois sentidos, porque só o verde passaria por acidente num portão
    que não faz nada.

    Em `tmp_path` e não na árvore: plantar um achado no repositório de verdade, durante o push
    de outro agente, é o incidente de 04/09 outra vez.
    """
    suite = tmp_path / "suite_de_mentira"
    suite.mkdir()
    (suite / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 100\ntarget-version = "py312"\n', encoding="utf-8"
    )
    achado = suite / "com_achado.py"
    #: `import os` sem uso: o linter reporta F401, e o formatador acha o arquivo impecável —
    #: que é exatamente a diferença entre as duas metades.
    achado.write_text("import os\n", encoding="utf-8")

    #: Primeiro a prova de que é o LINT que morde, e não o formato disfarçado.
    formato = _run_hook("--format-check", str(suite))
    assert formato.returncode == 0, (
        "o formatador reclamou do arquivo, entao este no mediria o portao errado; "
        f"saida: {formato.stdout.strip()[:200]}"
    )

    vermelho = _run_hook("--lint-check", str(suite))
    assert vermelho.returncode != 0, (
        f"o portao aceitou um achado de lint; saida: {vermelho.stdout.strip()[:200]}"
    )
    assert "F401" in vermelho.stdout, (
        f"o portao falhou por outra coisa que nao o achado plantado; saida: {vermelho.stdout[:200]}"
    )

    achado.write_text("x = 1\n", encoding="utf-8")
    verde = _run_hook("--lint-check", str(suite))
    assert verde.returncode == 0, (
        f"o portao recusou um arquivo limpo; saida: {verde.stdout.strip()[:200]}"
    )


def test_o_formato_anda_na_onda_LEVE_e_toda_vaga_esta_em_exatamente_uma() -> None:  # noqa: N802
    """A regra de onda mora numa função só, e este nó soma as duas de volta.

    Duas cópias de uma regra são duas regras à espera de discordar — o próprio hook diz isso
    sobre listas, e depois tinha o `if` da onda escrito duas vezes. Agora `wave_of` responde
    às duas, e o que se afirma aqui é que nenhum trabalho se perdeu na divisão.
    """
    resultado = _run_hook("--waves")
    assert resultado.returncode == 0, resultado.stderr.strip()[:200]
    ondas: dict[str, list[str]] = {"light": [], "heavy": []}
    for linha in resultado.stdout.splitlines():
        if "\t" not in linha:
            continue
        onda, job = linha.split("\t", 1)
        if onda.strip() in ondas:
            ondas[onda.strip()].append(job.strip())
    trabalhos = _gated_jobs()
    assert sorted(ondas["light"] + ondas["heavy"]) == sorted(trabalhos), (
        "a divisao em ondas perdeu ou duplicou um trabalho"
    )
    #: O formato e o lint são mais baratos que o tipo, então andam com os leves. As duas
    #: famílias são afirmadas UMA A UMA: um assert sobre a união passaria por igual se uma
    #: delas tivesse sumido inteira da onda.
    for prefixo in ("format: ", "lint: "):
        familia = [job for job in trabalhos if job.startswith(prefixo)]
        assert familia, f"nenhum trabalho {prefixo!r}; a familia sumiu da lista"
        assert set(familia) <= set(ondas["light"]), (
            f"{prefixo!r} saiu da onda leve, e o custo medido nao justifica a pesada"
        )
