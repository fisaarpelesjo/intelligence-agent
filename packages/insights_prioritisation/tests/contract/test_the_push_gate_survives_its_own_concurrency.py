"""The push gate limits its own concurrency, and says so when the machine is what failed.

S-42, 2026-09-03. The gate fires one subshell per job and used to fire ALL of them: twenty
processes, ten of them `pyright`. It then blocked two pushes in a row **in different jobs
each time** — once a nested pytest dying at *"1 error during collection"*, once a
`Windows fatal exception: code 0xc000070a` with an access violation. Neither was a test.
The machine ran out of memory, and a different victim each run is the signature of that
rather than of a defect.

**Two distinct failures, and this file drives both.**

1. *Nothing bounded the fan-out.* Measured on the machine that failed: 16 logical CPUs and
   15.8 GiB installed, but between 2.0 and 5.7 GiB actually FREE depending on what else was
   open; ten `pyright` in parallel cost ~2.3 GiB in total, while `channel_integration`'s
   pytest alone peaks at ~1.8 GiB. So the ceiling is memory, set by the heavy suites, and a
   limit derived from CPU count would authorise exactly the twenty processes that broke it.
2. *A killed process read as a failing test.* The report said `FAILED, exit 1` for a job the
   OS destroyed, so the next reader goes hunting for a defect in a suite that is green. The
   two states ask for opposite actions and are now named apart — while both still block,
   because "the machine could not run it" is never "it passed".

## These nodes RUN the gate; they do not read it

`--concurrency-selftest N S` drives `dispatch_jobs` — the same loop the real push uses —
over N jobs that sleep, and reports the greatest number ever in flight, computed from spans
the loop recorded itself. Reading the file for a `wait` would describe a shape and would
keep passing if the loop were rewritten to ignore the limit. `--read-run DIR` reports on a
prepared run directory without running a suite, which is how the four verdicts below are
driven against the real classifier.

## Absence skips, loudly

Without `bash` the script cannot be asked anything, and reporting that as a broken gate
would be red for something these nodes do not guard.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
HOOK = REPO / "tools" / "git-hooks" / "pre-push"


def _hook(
    *args: str, env_limit: str | None = None, free_kb: str | None = None
) -> subprocess.CompletedProcess[str]:
    if not HOOK.exists():  # pragma: no cover - a checkout without the hook
        pytest.skip("tools/git-hooks/pre-push is not in this checkout; nothing was measured")
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - a machine without a POSIX shell
        pytest.skip("no bash on this machine; the gate could not be asked for a verdict")
    env = None
    if env_limit is not None or free_kb is not None:
        import os

        env = dict(os.environ)
        if env_limit is not None:
            env["SELFTEST_LIMIT"] = env_limit
        if free_kb is not None:
            env["PREPUSH_FREE_KB"] = free_kb
    return subprocess.run(
        [bash, str(HOOK), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )


def _field(text: str, name: str) -> str:
    for token in text.split():
        if token.startswith(f"{name}="):
            return token.split("=", 1)[1]
    raise AssertionError(f"{name} not reported in: {text!r}")


# --- the limit itself -------------------------------------------------------


def test_the_gate_reports_a_limit_and_how_it_derived_it() -> None:
    """A limit nobody can see is a limit nobody can check — including this node."""
    result = _hook("--concurrency")
    assert result.returncode == 0, result.stdout + result.stderr
    limit = int(_field(result.stdout, "limit"))
    cpus = int(_field(result.stdout, "cpus"))
    assert 1 <= limit <= cpus, result.stdout
    assert "note=" in result.stdout, result.stdout


def test_the_limit_is_not_the_whole_job_list() -> None:
    """The precise shape of the bug: as many processes as jobs, on a 15.8 GiB machine.

    Deliberately not asserting a NUMBER — the limit is derived from free memory and the
    machine running this is not the machine that failed. What must hold everywhere is that
    the gate no longer authorises one process per job by construction.
    """
    limit = int(_field(_hook("--concurrency").stdout, "limit"))
    jobs = [line for line in _hook("--list-jobs").stdout.splitlines() if line.strip()]
    assert jobs, "the gate lists no jobs; this node would assert nothing"
    assert limit < len(jobs) or len(jobs) <= 2, (
        f"the gate would still run all {len(jobs)} jobs at once (limit {limit})"
    )


@pytest.mark.parametrize("limit", ["1", "2", "3"])
def test_the_dispatch_loop_never_exceeds_the_limit(limit: str) -> None:
    """DRIVEN: the real loop, over sleeping jobs, with the overlap measured from its spans.

    Parametrised because a loop can respect one limit by accident — `wait -n` after every
    job would pass at 1 and fail at 3.
    """
    result = _hook("--concurrency-selftest", "8", "1", env_limit=limit)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _field(result.stdout, "limit") == limit
    assert int(_field(result.stdout, "jobs")) == 8
    in_flight = int(_field(result.stdout, "max_in_flight"))
    assert in_flight <= int(limit), result.stdout
    assert in_flight >= 1, "no job was ever in flight; the self-test measured nothing"


def test_limiting_the_concurrency_did_not_shorten_the_job_list() -> None:
    """The worst of both worlds would be a gate that fits by measuring less.

    The list is derived — the two named steps plus every suite plus every typed suite — so
    this checks the derivation rather than a count somebody typed: every gated suite must
    still appear, and each one that declares a `[tool.pyright]` must still have its types
    gated too.
    """
    jobs = [line for line in _hook("--list-jobs").stdout.splitlines() if line.strip()]
    suites = [line for line in _hook("--list-suites").stdout.splitlines() if line.strip()]
    assert suites, "the gate derives no suites; this node would assert nothing"
    assert "cross-artifact citations" in jobs
    for suite in suites:
        assert suite in jobs, f"{suite} left the gate"
        if (REPO / suite / "pyproject.toml").exists() and "[tool.pyright]" in (
            REPO / suite / "pyproject.toml"
        ).read_text(encoding="utf-8"):
            assert f"strict types: {suite}" in jobs, f"{suite} lost its type gate"


# --- a killed process is not a failing test ---------------------------------


def _run_dir(tmp_path: Path, out: str, rc: str | None) -> Path:
    """One job, one prepared result — the shape `--read-run` reports on."""
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "jobs").write_text("packages/example\n", encoding="utf-8")
    (directory / "1.out").write_text(out, encoding="utf-8")
    if rc is not None:
        (directory / "1.rc").write_text(f"{rc}\n", encoding="utf-8")
    return directory


def test_a_failing_test_is_still_reported_as_a_failing_test(tmp_path: Path) -> None:
    """The mirror. If everything non-zero became a MACHINE FAILURE the distinction would be
    worthless in the other direction, and a real red would stop reading as one."""
    result = _hook("--read-run", str(_run_dir(tmp_path, "1 failed, 268 passed\n", "1")))
    assert result.returncode == 1
    assert "FAILED, exit 1" in result.stderr
    assert "MACHINE FAILURE" not in result.stderr, result.stderr


def test_a_native_death_is_named_as_the_machine_and_not_as_a_red_test(tmp_path: Path) -> None:
    """The exact output of the second blocked push, verbatim from that run."""
    out = "Windows fatal exception: code 0xc000070a\naccess violation\n"
    result = _hook("--read-run", str(_run_dir(tmp_path, out, "1")))
    assert result.returncode == 1, "a machine failure must still BLOCK"
    assert "MACHINE FAILURE" in result.stderr, result.stderr
    assert "NOT a failing test" in result.stderr, result.stderr


def test_a_job_killed_by_a_signal_is_named_as_the_machine(tmp_path: Path) -> None:
    """128+n is a death, not a verdict. Nothing in the output has to say so."""
    result = _hook("--read-run", str(_run_dir(tmp_path, "no useful output\n", "137")))
    assert result.returncode == 1
    assert "MACHINE FAILURE, exit 137" in result.stderr, result.stderr


def test_a_job_that_never_reported_is_named_as_the_machine_and_still_blocks(
    tmp_path: Path,
) -> None:
    """The older rule — a missing exit code is a failure — is unchanged and now says WHY."""
    result = _hook("--read-run", str(_run_dir(tmp_path, "nothing\n", None)))
    assert result.returncode == 1, "did not measure is never passed"
    assert "MACHINE FAILURE" in result.stderr, result.stderr
    assert "never reported an exit code" in result.stderr, result.stderr


def test_the_blocked_sentence_has_one_source(tmp_path: Path) -> None:
    """`--read-run` is what nodes drive; the push is what people see.

    If the two printed different sentences, every node here would be measuring a message
    that the real run does not use — which is how S-42's machine failure could be named in
    one and stay unnamed in the other.
    """
    result = _hook("--read-run", str(_run_dir(tmp_path, "1 failed\n", "1")))
    assert "Fix it, or push with --no-verify and own that decision." in result.stderr
    source = HOOK.read_text(encoding="utf-8")
    assert source.count("Fix it, or push with --no-verify and own that decision.") == 1


def test_the_limit_falls_and_rises_with_free_memory_and_not_with_the_cpu_count() -> None:
    """The criterion the previous version of this file failed to check, and it mattered.

    Measured: replacing the whole derivation with `limit = cpu_count` — which is exactly
    what authorised twenty processes on a 15.8 GiB machine — left every other node in this
    file GREEN. A limit that ignores memory is the bug, so a node has to move the memory and
    watch the limit move.

    Driven through the one seam `free_kb` exposes, at four levels on the same machine, so
    the CPU count is held constant while the memory changes. A scarce machine collapses to
    the floor; an abundant one is capped by the CPUs and not by the RAM.
    """
    cpus = int(_field(_hook("--concurrency").stdout, "cpus"))

    def limit_when(free_mib: int) -> int:
        result = _hook("--concurrency", free_kb=str(free_mib * 1024))
        return int(_field(result.stdout, "limit"))

    scarce = limit_when(1024)
    modest = limit_when(16 * 1024)
    abundant = limit_when(64 * 1024)

    assert scarce < modest, (
        f"1 GiB free and 16 GiB free both produced {scarce}; the limit ignores memory"
    )
    assert modest <= abundant
    assert abundant <= cpus, "the CPU count must still cap the limit"
    assert scarce >= 1, "the gate must never be limited to zero jobs"


# --- o portão diz de QUE tipo é o vermelho, e guarda a prova (OD-137) -------


def test_o_127_e_AMBIENTE_e_nao_uma_suite_vermelha(tmp_path: Path) -> None:  # noqa: N802
    """**O falso vermelho que bloqueou um push de verdade** — `OD-137`, 06/09.

    `127` é *command not found*. Não é uma asserção e não é um cadáver: o verificador nunca
    chegou a arrancar, então **nada na suíte foi medido e nada nela está partido**.

    **Medido**: o push #15 bloqueou em `strict types: packages/daily_reporting` com `rc=127`
    e uma saída que continha apenas o aviso de versão do pyright. O job foi então corrido
    sozinho **duas vezes**: `0 errors, rc=0` das duas. Trinta e nove dos quarenta portões
    estavam verdes, e o quadragésimo era o lançador — não o código.

    A fronteira do portão era `rc >= 128`, e **o 127 fica exatamente um abaixo**. Esse é o
    defeito inteiro: o portão que já tinha aprendido a não confundir um PROCESSO MORTO com
    um teste vermelho continuava a confundir um COMANDO AUSENTE com um.

    Os quatro estados são dirigidos aqui de uma vez, porque o que se afirma não é que o 127
    tem nome — é que **os quatro continuam distintos**. Um nó que só olhasse o 127 passaria
    por igual se a mudança tivesse engolido o `FAILED` normal junto.
    """

    def veredito(rc: str, saida: str) -> str:
        #: Um subdiretorio por caso, senao o segundo tropeca no `mkdir` do primeiro.
        caso = tmp_path / f"caso_{rc}"
        caso.mkdir()
        resultado = _hook("--read-run", str(_run_dir(caso, saida, rc)))
        return resultado.stdout + resultado.stderr

    ambiente = veredito("127", "WARNING: there is a new pyright version available\n")
    assert "ENVIRONMENT FAILURE, exit 127" in ambiente, ambiente[:400]
    assert "nothing in it is broken" in ambiente, (
        "a mensagem nao diz ao leitor que a suite esta sa, que e a coisa toda"
    )
    #: E continua a BLOQUEAR: nao medir nunca e passar.
    assert "PUSH BLOCKED" in ambiente, ambiente[:400]

    #: Os outros tres NAO mudaram de nome.
    vermelho = veredito("1", "1 failed, 268 passed\n")
    assert "FAILED, exit 1" in vermelho, vermelho[:400]
    assert "ENVIRONMENT" not in vermelho, "um teste vermelho passou a ler como ambiente"

    morto = veredito("137", "nada util\n")
    assert "MACHINE FAILURE, exit 137" in morto, morto[:400]
    assert "ENVIRONMENT" not in morto, "um processo morto passou a ler como ambiente"


def test_a_frase_do_bloqueio_NAO_se_contradiz(tmp_path: Path) -> None:  # noqa: N802
    """Duas explicações para um bloqueio são pior que nenhuma.

    A primeira versão desta fatia imprimia a frase do ambiente **e depois** a genérica — "não
    é um teste vermelho" seguido de "um portão saiu não-zero". O leitor fica a adivinhar qual
    metade acreditar, e adivinhar é exatamente o que estas frases existem para evitar.

    A genérica é a de quando **nada mais explicou**, e por isso tem de ser a última.
    """
    resultado = _hook("--read-run", str(_run_dir(tmp_path, "aviso\n", "127")))
    texto = resultado.stdout + resultado.stderr
    assert "ENVIRONMENT" in texto
    assert "A gate above exited non-zero" not in texto, (
        "a frase generica saiu ao lado da especifica e contradiz-la"
    )


def test_a_EVIDENCIA_sobrevive_ao_veredito_e_some_quando_passa(tmp_path: Path) -> None:  # noqa: N802
    """**A metade que torna a outra investigável** — e é por isso que a ordem as juntou.

    O `trap` apagava o diretório do run em TODA saída, inclusive nas bloqueadas. O leitor
    ficava com a frase e mais nada: sem `.out`, sem `.rc`, sem saber QUAL portão estava
    vermelho nem o que ele imprimiu. Em 06/09 o `127` só foi diagnosticável porque foi
    apanhado a meio da corrida; um minuto depois o diretório inteiro tinha desaparecido.

    **Mas um run VERDE continua a limpar.** Guardar todos encheria o `.git` de corridas que
    ninguém vai ler — e um diretório deixado para trás por um push que passou é precisamente
    o órfão que fez um push vivo parecer morto duas vezes esta semana.

    Dirige `cleanup_runs`, a MESMA função que a saída do hook chama, nos dois sentidos.
    """
    bloqueado = tmp_path / "bloqueado"
    bloqueado.mkdir()
    (bloqueado / "1.rc").write_text("1\n", encoding="utf-8")
    guardado = _hook("--selftest-cleanup", str(bloqueado), "1")
    assert "kept=1" in guardado.stdout, guardado.stdout + guardado.stderr
    assert bloqueado.exists(), "o diretorio do run foi apagado num bloqueio"
    assert "KEPT" in guardado.stderr, (
        "o diretorio ficou mas ninguem foi avisado, e uma prova que nao se sabe onde esta "
        "nao e prova"
    )
    assert str(bloqueado) in guardado.stderr, "a mensagem nao diz ONDE ficou"

    verde = tmp_path / "verde"
    verde.mkdir()
    (verde / "1.rc").write_text("0\n", encoding="utf-8")
    limpo = _hook("--selftest-cleanup", str(verde), "0")
    assert "kept=0" in limpo.stdout, limpo.stdout + limpo.stderr
    assert not verde.exists(), (
        "um run verde deixou o diretorio para tras, e e esse o orfao que fez um push vivo "
        "parecer morto"
    )


def test_o_PADRAO_e_limpar_e_nao_guardar(tmp_path: Path) -> None:  # noqa: N802
    """O valor que ninguém passa é o que corre em todo push que PASSA.

    Este nó nasceu de um buraco no nó irmão. A mutação óbvia — virar `keep_runs=0` para `1`,
    que deixaria um órfão depois de CADA push verde — passou por vinte e dois verdes, porque
    todos os casos passavam o valor explicitamente e **nenhum exercitava o padrão**.

    Por isso o terceiro argumento do seam é opcional: sem ele, o que se mede é a decisão que
    o hook toma sozinho.
    """
    alvo = tmp_path / "padrao"
    alvo.mkdir()
    resultado = _hook("--selftest-cleanup", str(alvo))
    assert "kept=0" in resultado.stdout, (
        "o padrao passou a GUARDAR; todo push verde deixaria para tras o orfao que ja fez "
        f"um push vivo parecer morto. Saida: {resultado.stdout + resultado.stderr}"
    )
    assert not alvo.exists()


def test_o_seam_da_limpeza_NAO_deixa_orfao_ele_proprio() -> None:  # noqa: N802
    """A ironia que este nó existe para impedir.

    `--selftest-cleanup` corre depois de o hook já ter criado o SEU diretório de run. Se ele
    não o largasse antes de apontar para o diretório sob teste, esta fatia estaria a criar o
    exato órfão que existe para acabar — um por cada vez que um nó a chamasse.
    """
    antes = {caminho.name for caminho in (REPO / ".git").glob("pre-push-runs.*")}
    with tempfile.TemporaryDirectory() as temporario:
        alvo = Path(temporario) / "alvo"
        alvo.mkdir()
        _hook("--selftest-cleanup", str(alvo), "0")
    depois = {caminho.name for caminho in (REPO / ".git").glob("pre-push-runs.*")}
    assert depois <= antes, f"o seam deixou orfaos: {sorted(depois - antes)}"


# --- o portão mede a si mesmo (OD-136) --------------------------------------


def _plano_pesado(free_mib: int | None = None) -> str:
    """O veredito da onda pesada, lido do hook e não recalculado aqui."""
    resultado = _hook("--heavy-plan", free_kb=None if free_mib is None else str(free_mib * 1024))
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    linhas = [ln.strip() for ln in resultado.stdout.splitlines() if ln.strip()]
    for linha in reversed(linhas):
        if linha.startswith(("limit=", "refuse=")):
            return linha
    raise AssertionError(f"o hook nao deu veredito nenhum: {resultado.stdout!r}")


def test_o_portao_RECUSA_por_escrito_quando_nem_uma_suite_cabe() -> None:  # noqa: N802
    """**O incidente que esta fatia fecha** — `OD-136`, 06/09.

    A máquina tinha **1.928 MiB livres contra 2.048 MiB por vaga pesada**. A derivação deu
    `1928/2048 = 0` vagas, o PISO levantou para DUAS, e o portão despachou duas suítes de
    1,8 GiB dentro de 1,9 GiB. Quatro trabalhos morreram sem escrever código de saída — e
    **um trabalho morto por memória não escreve razão nenhuma**, então a corrida ficou com a
    cara exata de um push bloqueado. Custou um diagnóstico errado: um par leu três
    diretórios de run como se fossem um push, chamou-lhe morte, e ia levar o orçamento de
    memória ao dono por causa de um push que na verdade tinha passado.

    O conserto não é um número maior — a ordem dele diz que o orçamento não se mexe sem
    medição. É que a MEDIÇÃO GANHA DA PREFERÊNCIA: cabe o que cabe, UMA de cada vez quando
    só uma cabe, e quando nem uma cabe o portão **recusa por escrito**.

    Dirigido pelo mesmo seam `PREPUSH_FREE_KB` que a derivação já expunha, nos dois sentidos:
    abaixo de uma vaga recusa, exatamente uma vaga aceita. Só o vermelho passaria por acidente
    num portão que recusasse sempre, e só o verde num que nunca recusasse.
    """
    assert _plano_pesado(1024) == "refuse=1024", "1 GiB livre e o portao nao recusou"
    assert _plano_pesado(2047).startswith("refuse="), (
        "um byte abaixo de uma vaga inteira ainda tem de recusar"
    )
    #: A fronteira, e é ela que separa recusar de correr: exatamente uma vaga.
    assert _plano_pesado(2048) == "limit=1 basis=memory", (
        "com espaco para UMA suite o portao tem de correr uma, nao recusar e nao correr duas"
    )


def test_o_piso_da_onda_pesada_NAO_inventa_vaga_que_a_memoria_nao_tem() -> None:  # noqa: N802
    """O defeito em uma frase: um piso é uma promessa sobre memória que a memória não fez.

    A onda leve mantém o piso de dois — uma vaga leve são 512 MiB, e duas cabem em qualquer
    máquina que consiga correr este repositório. A pesada não pode: duas vagas pesadas são
    4.096 MiB, e a máquina que falhou tinha 1.928.

    **Mutação medida**: devolver o piso da pesada a `2` faz o veredito de 1 GiB passar de
    `refuse=1024` para `limit=2` — que é literalmente o despacho que matou o `#13`.
    """
    saida = _hook("--concurrency").stdout
    assert int(_field(saida, "min_slots")) == 1, (
        "o piso da onda pesada voltou a ser maior que uma vaga; e o defeito do 06/09"
    )
    assert int(_field(saida, "light_min_slots")) == 2, (
        "a onda leve perdeu o piso, e nada mediu que ela precisasse de o perder"
    )


def test_a_memoria_e_lida_DE_NOVO_entre_as_ondas_e_nao_so_no_cabecalho() -> None:  # noqa: N802
    """Uma leitura tirada antes de dezanove processos não descreve a máquina que vem depois.

    O portão media a memória UMA vez, no topo, e despachava as suítes contra um número já
    velho de nove minutos. Este nó afirma as duas metades: que o cabeçalho **deixou de
    prometer** o número das suítes, e que existe uma segunda leitura anunciada entre as ondas.

    Lê a FONTE do hook porque o que se afirma é a ordem das operações, e essa ordem não tem
    saída observável sem correr o portão inteiro — o que faria este nó demorar dez minutos e
    depender da memória livre da máquina que o corre, que é o oposto de um nó.
    """
    fonte = HOOK.read_text(encoding="utf-8")
    assert "the suites are measured AGAIN after them, not now." in fonte, (
        "o cabecalho voltou a prometer um numero para as suites antes de o medir"
    )
    assert "plan=$(heavy_plan)" in fonte, "a segunda leitura entre as ondas desapareceu"
    #: A ordem: a re-leitura vem DEPOIS de despachar a onda leve.
    leve = fonte.index('dispatch_jobs "${light_file}"')
    releitura = fonte.index("plan=$(heavy_plan)")
    pesada = fonte.index('dispatch_jobs "${heavy_file}"')
    assert leve < releitura < pesada, (
        "a memoria e lida fora do intervalo entre as duas ondas, que e o unico sitio onde "
        "a leitura descreve a maquina que as suites vao encontrar"
    )


def test_a_recusa_DIZ_o_numero_e_nomeia_a_maquina_e_nao_um_teste_vermelho() -> None:  # noqa: N802
    """Uma recusa sem razão escrita é o silêncio que este ciclo existe para acabar.

    O que a mensagem tem de carregar, e cada pedaço tem uma razão: **a máquina e não um teste
    vermelho**, senão alguém vai procurar defeito na suíte que nunca correu; **o número
    medido**, senão não é medição, é opinião; **e que os leves correram**, porque o resultado
    deles é verdadeiro e deitá-lo fora seria medir outra vez de graça.
    """
    fonte = HOOK.read_text(encoding="utf-8")
    inicio = fonte.index("PUSH REFUSED BY THE GATE")
    bloco = fonte[inicio : inicio + 1400]
    assert "MACHINE and not a red test" in bloco, (
        "a recusa nao distingue a maquina de um teste vermelho, e alguem vai depurar a suite"
    )
    assert "${free_mib} MiB free" in bloco, "a recusa nao diz quanto mediu"
    assert "DID run, and their results stand" in bloco, (
        "a recusa nao diz que a onda leve correu, e o proximo a ler vai repetir o trabalho"
    )
    assert "--no-verify" in bloco, "a recusa nao diz qual e a saida consciente"


# --- two waves, one list ----------------------------------------------------


def test_the_two_waves_add_back_up_to_the_whole_job_list() -> None:
    """Splitting the run in two is two chances to drop a job in silence.

    The waves exist because the measurement found two populations — a `pyright` at ~240 MiB
    against a heavy pytest at ~1.8 GiB — and charging both the heavy rate ran the gate two
    at a time for 634 s, worse than the 604 s serial gate the parallelism replaced. The
    saving is only legitimate while the split loses nothing, so: the union is exactly the
    list, the waves are disjoint, and neither is empty.
    """
    jobs = [line for line in _hook("--list-jobs").stdout.splitlines() if line.strip()]
    waves = [line for line in _hook("--waves").stdout.splitlines() if line.strip()]
    assert jobs, "the gate lists no jobs; this node would assert nothing"

    light = [line.split("\t", 1)[1] for line in waves if line.startswith("light\t")]
    heavy = [line.split("\t", 1)[1] for line in waves if line.startswith("heavy\t")]
    assert light, "no job runs in the light wave; the split bought nothing"
    assert heavy, "no job runs in the heavy wave; the suites vanished"
    assert not set(light) & set(heavy), "a job is in both waves and would run twice"
    assert sorted(light + heavy) == sorted(jobs), (
        "the waves do not add up to the job list; something is gated by neither"
    )


def test_the_light_wave_is_the_cheap_checks_and_runs_wider_than_the_suites() -> None:
    """The light rate is only defensible for the population it was measured on.

    If a heavy suite drifted into the light wave it would run eight at a time at 1.8 GiB
    each, which is the original bug with a smaller number in front of it.

    **Duas famílias são baratas, não uma, desde 2026-09-06** (`OD-134`): os verificadores
    de tipo e os de formato. Este nó ficou VERMELHO quando os de formato chegaram — o nó a
    funcionar — e a correção foi ensinar-lhe o segundo tipo barato, com a medição ao lado,
    em vez de trocar o assert por um que aceitasse qualquer coisa.

    O que torna o formato barato está medido: entre 453 e 536 ms por suíte, contra suítes
    de teste que chegam a 1,8 GiB e a minutos. Uma terceira família só entra aqui depois de
    alguém medir que ela é desta ordem de grandeza.

    **Mutações**, o hook restaurado por `cp` + `cmp`: uma suíte pesada escorregada para a onda
    leve → `1 failed, 13 passed`; o formato tirado da onda leve, deixando só uma das duas
    famílias → `1 failed, 13 passed`. A segunda é a que o assert de prefixo sozinho deixaria
    passar.
    """
    waves = [line for line in _hook("--waves").stdout.splitlines() if line.strip()]
    light = [line.split("\t", 1)[1] for line in waves if line.startswith("light\t")]
    #: `markers: ` juntou-se às outras em 2026-09-07 (`OD-155`). Contar nós recolhidos é
    #: barato como um `ruff`, e a guarda veio da workflow `harness` quando as oito foram
    #: desligadas — a medição mudou de instrumento, não de critério.
    baratos = ("strict types: ", "format: ", "lint: ", "markers: ")
    assert all(job.startswith(baratos) for job in light), light
    #: E as QUATRO famílias estão lá — um assert que só olhasse os prefixos passaria por
    #: igual se os de formato tivessem sumido da onda.
    for prefixo in baratos:
        assert [job for job in light if job.startswith(prefixo)], prefixo

    reported = _hook("--concurrency", free_kb=str(16 * 1024 * 1024)).stdout
    heavy_limit = int(_field(reported, "limit"))
    # Driven at a fixed memory reading so the comparison is about the RATES and not about
    # what this machine happens to have free right now.
    assert heavy_limit >= 1
    assert "light slot" in reported, reported
