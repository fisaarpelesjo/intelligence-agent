"""O caminho que a `every-package.yml` CRIA é o que o `pre-push` SONDA — `S-61`, `S-62`.

## O acordo que estava à mão

A forma final do ciclo 569 está certa em tempo de execução: o venv nasce do interpretador do
`setup-python`, entra no `GITHUB_PATH`, o `pip install -e` cai lá dentro, e o `.pth` das
editáveis passa a estar no site-packages que o pyright auto-descobre. Um interpretador só.

**Mas o NOME `.venv` está escrito à mão em três sítios** — o passo do workflow, as duas linhas
que o hook sonda, e a convenção que o pyright auto-descobre — e nada os ligava. Um rename num
deles devolvia o portão ao estado de 2026-08-25 **em silêncio**, porque `pre-push SKIPPED` lê
como passagem em todo o lado onde não há um nó a pedir bloqueio. Foi exactamente esse silêncio
que escondeu sete nós até 2026-09-07.

## Porque o segundo nó afirma a PROPRIEDADE e não o rótulo

O reviewer pediu que se afirmasse `classify(...) == "builds the environment"`. **Medi antes de
escrever e não o faço assim**: acrescentar `$GITHUB_PATH` a `RUNNER_MARKERS` -- que é a cura do
`S-62`, no mesmo diff -- muda a resposta para `needs the GitHub runner`, porque `classify` testa
os marcadores do runner ANTES dos do ambiente. As duas respostas significam *saltado*, e é isso
que protege o `.venv` desta máquina de ser esmagado por `python -m venv`.

Afirmar o rótulo seria fixar um acidente de ordem entre duas tuplas. O que importa é que o
executor local RECUSE correr o passo, seja em que categoria for.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
WORKFLOW = REPO / ".github" / "workflows" / "every-package.yml"
HOOK = REPO / "tools" / "git-hooks" / "pre-push"
EXECUTOR = REPO / "tools" / "local-ci" / "run_local_ci.py"

#: O passo, pelo nome com que o workflow o declara.
STEP = "One interpreter, where every gate looks for it"


def _step_command() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = next(iter(document["jobs"].values()))["steps"]
    for step in steps:
        if step.get("name", "").startswith(STEP.split(",")[0]):
            return step["run"]
    message = f"{WORKFLOW.name} não declara o passo {STEP!r}; o venv deixou de ser criado"
    raise AssertionError(message)


def _executor():
    """O executor local, carregado como módulo.

    Registado em `sys.modules` ANTES de executar: os `@dataclass` dele resolvem anotações pelo
    módulo e rebentam com `AttributeError: 'NoneType'` se ele não estiver lá. Medido.
    """
    spec = importlib.util.spec_from_file_location("run_local_ci", EXECUTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_local_ci"] = module
    spec.loader.exec_module(module)
    return module


def test_the_workflow_builds_the_interpreter_the_hook_probes() -> None:
    """O mesmo caminho dos dois lados, lido de cada ficheiro e não escrito aqui."""
    created = re.findall(r"python -m venv (\S+)", _step_command())
    assert created, "o passo deixou de criar um venv"

    probed = re.findall(r'^PY="\$\{ROOT\}/([^/]+)/', HOOK.read_text(encoding="utf-8"), re.M)
    assert probed, "o hook deixou de sondar um caminho de interpretador"

    assert set(created) == set(probed), (
        f"o workflow cria {sorted(set(created))} e o hook sonda {sorted(set(probed))}. "
        "Um rename num dos lados devolve o portão a 'pre-push SKIPPED' -- e isso lê como "
        "passagem, que foi o silêncio que escondeu sete nós até 2026-09-07"
    )


def test_the_local_executor_refuses_to_build_the_environment_here() -> None:
    """O executor não corre `python -m venv .venv` nesta máquina.

    Se corresse, esmagava o `.venv` de quem desenvolve. **A propriedade é RECUSAR**, não a
    categoria com que recusa -- ver o docstring do módulo.
    """
    verdict = _executor().classify(_step_command())
    assert verdict is not None, (
        "o executor local passou a considerar este passo corrível aqui, e ele corre "
        "`python -m venv .venv`: esmagaria o interpretador desta máquina"
    )


def test_the_runner_variable_is_named_as_one() -> None:
    """`$GITHUB_PATH` é variável que só o runner põe — `S-62`.

    Medido: fora do runner ela vem vazia e o `>>` falha com rc=1 e *No such file or directory*.
    Sem estar na tupla, um passo futuro que só escrevesse nela seria arquivado como
    vermelho-de-CÓDIGO, que é precisamente o mislabel que a categoria existe para evitar.
    """
    assert "$GITHUB_PATH" in _executor().RUNNER_MARKERS, (
        "$GITHUB_PATH não está em RUNNER_MARKERS; um passo que só escreva nela falha rc=1 fora "
        "do runner e o relatório chama-lhe defeito do código"
    )


#: Os varrimentos que têm de correr mesmo depois de um irmão ficar vermelho. Os passos de
#: AMBIENTE não entram: se a instalação falhar, medir o resto não mede nada.
SWEEPS = (
    "Format check",
    "Lint,",
    "Strict type check",
    "Tests,",
    "Every directory under packages declares a manifest",
)


def _steps() -> list[dict[str, object]]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return list(next(iter(document["jobs"].values()))["steps"])


def test_a_red_sweep_does_not_hide_the_sweeps_after_it() -> None:
    """O GitHub para o JOB no primeiro PASSO vermelho — e isso escondia oito varrimentos.

    Sem esta condição, **um único achado do `ruff format` impedia as NOVE suítes de correr**, e
    "não chegou lá" lia-se como "nada a relatar". É a mesma família que este repositório passou
    três ciclos a fechar DENTRO de cada varrimento: exigi-la no laço dos nove pacotes e não
    entre os passos era uma inconsistência, e era minha.

    **A mutação que prova o nó** é tornar um ficheiro torto num pacote: antes, o job morria no
    `Format check` e nenhuma suíte corria; agora os cinco varrimentos correm e o job nomeia
    todos os que falharam.
    """
    missing = [
        str(step.get("name"))
        for step in _steps()
        if any(str(step.get("name", "")).startswith(s) for s in SWEEPS)
        and "cancelled()" not in str(step.get("if", ""))
    ]
    assert not missing, (
        f"estes varrimentos escondem-se atrás do primeiro vermelho: {missing}. "
        "O GitHub para o job no primeiro passo que falha, e um achado do ruff impediria as nove "
        "suítes de correr -- 'não chegou lá' não é 'nada a relatar'"
    )


def test_no_step_turns_a_failure_into_a_non_failure() -> None:
    """A condição faz correr; **não faz passar** — e a distinção é a decisão inteira.

    `continue-on-error` transforma FALHA em NÃO-FALHA e continua proibido; dois nós irmãos
    exigem-no dos workflows deles (`analytics_interaction` sobre `nl-analytics.yml`,
    `channel_integration` sobre `multichannel.yml`, medido). Uma condição de passo não
    transforma nada: cada varrimento continua a falhar e o job continua vermelho.

    `always()` é vetado à letra por esses dois nós e por isto: um job cancelado à mão não deve
    continuar a gastar runner. Daí `!cancelled()`.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    for step in _steps():
        assert "continue-on-error" not in step, f"{step.get('name')} engole a própria falha"
        assert str(step.get("if", "")).strip() != "always()", f"{step.get('name')} é always()"
    assert "continue-on-error: true" not in text
    assert "|| true" not in text, "um passo engole a própria falha"
