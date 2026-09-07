"""No path reopens the model boundary — T085 (FR-094, FR-095; SC-055).

    The system MUST expose no flag, mode, configuration, deployment setting or
    debugging path that reopens the boundary. A future capability requiring
    values on the model side MUST reopen it through its own governed decision and
    its own feature, never through configuration of this one. — `FR-094`

Three ways a boundary gets reopened, and each has its own check:

* **widened inputs** — a parameter appears through which a value could arrive;
* **moved position** — the port becomes reachable after execution, so a result
  exists while it is callable;
* **constructed anyway** — something builds a provider while `D-20` is
  undeclared, whether through an environment variable, a flag, a default or a
  bundled adapter.

The third is the one that arrives most plausibly, because it always looks like
convenience: a default provider "for local development", an environment variable
"only read in tests", a fallback "so the port is never None". Each would make the
gate advisory.

`FR-095` requires the same content scan that guards audit events and telemetry,
so a value cannot reach a model through a field whose name sounds harmless — that
scan is the field-set and type-closure work in `T083` and `T084`; this file adds
the configuration half.
"""

from __future__ import annotations

import ast
import inspect
import tomllib
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.compliance.gates import require_model_participation
from analytics_interaction.interpretation import model_port
from analytics_interaction.interpretation.model_port import (
    InterpretationModelPort,
    narrow_candidates,
)

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
PACKAGE_ROOT = SRC.parents[1]
PYPROJECT = PACKAGE_ROOT / "pyproject.toml"
PORT = SRC / "interpretation" / "model_port.py"

#: Names a reopening switch would arrive under.
REOPEN_NAMES = (
    "allow_values",
    "enable_model",
    "force_model",
    "model_enabled",
    "bypass_gate",
    "skip_gate",
    "skip_readiness",
    "unsafe",
    "debug_mode",
    "dev_mode",
    "local_provider",
    "default_provider",
    "fallback_provider",
    "provider_url",
    "endpoint",
    "api_key",
    "api_base",
    "model_name",
    "max_tokens",
    "temperature",
    "token_limit",
    "cost_limit",
)

#: Provider SDKs, HTTP clients and credential loaders.
PROVIDER_DISTRIBUTIONS = (
    "openai",
    "anthropic",
    "google-generativeai",
    "vertexai",
    "cohere",
    "litellm",
    "langchain",
    "ollama",
    "transformers",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "python-dotenv",
)


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _identifiers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.alias):
            found.add(node.asname or node.name)
    return found


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


# --- inputs cannot widen -------------------------------------------------------


@pytest.mark.parametrize("name", REOPEN_NAMES)
def test_no_module_declares_a_reopening_switch(name: str) -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {identifier}"
        for path in _sources()
        for identifier in _identifiers(path)
        if name in identifier.lower()
    ]
    assert not offenders, f"a reopening switch exists: {offenders}"


def test_the_port_signature_takes_no_optional_widening_parameter() -> None:
    """Two parameters, both required, neither defaulted.

    A defaulted third parameter is how "just pass the result too, optionally"
    arrives without anybody noticing the boundary moved.
    """
    signature = inspect.signature(InterpretationModelPort.narrow)
    parameters = [p for name, p in signature.parameters.items() if name != "self"]
    assert len(parameters) == 2
    for parameter in parameters:
        assert parameter.default is inspect.Parameter.empty


def test_the_narrowing_entry_point_gates_before_it_does_anything_else() -> None:
    """Position within the function body, not just presence.

    A gate called after the provider would be a gate that ran after the cost was
    incurred. Read from the source so the ordering is checked rather than
    assumed.
    """
    source = inspect.getsource(narrow_candidates)
    body = source.split('"""')[2]
    gate = body.index("require_model_participation(")
    call = body.index("port.narrow(")
    assert gate < call, "the readiness gate does not precede the provider call"


# --- position cannot move ------------------------------------------------------


def test_the_port_is_not_reachable_from_any_execution_module() -> None:
    """`FR-093` from the other direction: nothing post-execution imports it.

    `T084` proves the port cannot reach execution. This proves execution cannot
    reach the port — which is what "sits entirely before execution" means when
    the orchestrator eventually exists.
    """
    offenders: list[str] = []
    for path in _sources():
        relative = path.relative_to(SRC).as_posix()
        if not relative.startswith(("execution/", "comparison/", "answer/", "audit/")):
            continue
        for imported in _imports(path):
            if "model_port" in imported:
                offenders.append(f"{relative} imports {imported}")
    assert not offenders, f"the model port is reachable after execution: {offenders}"


# --- construction cannot happen anyway -----------------------------------------


@pytest.mark.parametrize("distribution", PROVIDER_DISTRIBUTIONS)
def test_no_provider_sdk_or_http_client_is_declared(distribution: str) -> None:
    """Runtime **and** dev. A provider reachable only from tests is still declared."""
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    declared = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(extra)

    names = {
        requirement.split("==")[0].split(">=")[0].split("[")[0].strip().lower()
        for requirement in declared
    }
    assert distribution not in names


@pytest.mark.parametrize("distribution", PROVIDER_DISTRIBUTIONS)
def test_no_provider_sdk_or_http_client_is_imported(distribution: str) -> None:
    root = distribution.replace("-", "_")
    offenders = [
        f"{path.relative_to(SRC).as_posix()} imports {imported}"
        for path in _sources()
        for imported in _imports(path)
        if imported == root or imported.startswith(root + ".")
    ]
    assert not offenders, f"a provider SDK is imported: {offenders}"


#: The process environment, named exactly. Matched as **identifiers**, not as
#: substrings: an earlier form flagged anything whose rendered source contained
#: ``environ``, which made ``ExecutionEnvironment`` and ``self._environment`` into
#: violations. A token scan that fires on a word is a scan that gets narrowed
#: under pressure until it stops firing at all — so this one matches the two
#: names that actually read the environment, and the planted cases below prove
#: the narrowing left no hole.
ENVIRONMENT_READERS = frozenset({"environ", "getenv", "environb"})


def _environment_reads(source: str, filename: str = "<test>") -> list[str]:
    """Every read of the process environment, by identifier."""
    tree = ast.parse(source, filename=filename)
    found: list[str] = []
    for node in ast.walk(tree):
        name = (
            node.attr
            if isinstance(node, ast.Attribute)
            else node.id
            if isinstance(node, ast.Name)
            else ""
        )
        if name in ENVIRONMENT_READERS:
            found.append(ast.unparse(node))
    return found


def test_no_module_reads_the_environment_for_a_provider() -> None:
    """An environment variable is the commonest way a default provider appears."""
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {rendered}"
        for path in _sources()
        for rendered in _environment_reads(path.read_text(encoding="utf-8"), str(path))
    ]
    assert not offenders, f"the environment is read: {offenders}"


@pytest.mark.parametrize(
    "planted",
    [
        "import os\nKEY = os.environ['ANTHROPIC_API_KEY']\n",
        "import os\nKEY = os.getenv('OPENAI_API_KEY')\n",
        "from os import environ\nKEY = environ['MODEL_PROVIDER']\n",
        "from os import getenv\nKEY = getenv('MODEL_PROVIDER', 'ollama')\n",
        "import os\nKEY = os.environb[b'MODEL_PROVIDER']\n",
    ],
)
def test_the_environment_scan_catches_a_planted_read(planted: str) -> None:
    """The narrowing is not a hole: attribute, bare name and bytes forms all fire."""
    assert _environment_reads(planted)


@pytest.mark.parametrize(
    "innocent",
    [
        "class ExecutionEnvironment:\n    pass\n",
        "def bind(environment):\n    return environment\n",
        "def submit(self):\n    return self._environment\n",
    ],
)
def test_the_environment_scan_does_not_fire_on_the_word(innocent: str) -> None:
    """And it is not a substring match. ``environment`` is not ``environ``."""
    assert not _environment_reads(innocent)


def test_the_package_ships_no_provider_implementation() -> None:
    """The mutation test for a hidden provider.

    Any non-Protocol class declaring ``narrow`` would be one — whatever it is
    called and wherever it lives.
    """
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if any("Protocol" in ast.unparse(base) for base in node.bases):
                continue
            if any(
                isinstance(child, ast.FunctionDef) and child.name == "narrow" for child in node.body
            ):
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {node.name}")
    assert not offenders, f"a provider implementation ships in src/: {offenders}"


def test_the_port_parameter_has_no_default() -> None:
    """A defaulted port would be a provider chosen by this package."""
    parameter = inspect.signature(narrow_candidates).parameters["port"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_the_gate_takes_no_argument_that_could_skip_it() -> None:
    """``records`` is injectable for tests; there is no ``force`` beside it."""
    parameters = inspect.signature(require_model_participation).parameters
    assert set(parameters) == {"records"}
    assert parameters["records"].kind is inspect.Parameter.KEYWORD_ONLY


def test_the_port_module_declares_no_module_level_mutable_state() -> None:
    """A module-level provider slot is a hidden construction waiting to happen."""
    tree = ast.parse(PORT.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        value = node.value
        if isinstance(value, ast.List | ast.Dict | ast.Set):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
            names = [ast.unparse(target) for target in targets]
            if names != ["__all__"]:
                offenders.append(", ".join(names))
    assert not offenders, f"module-level mutable state in the port: {offenders}"


def test_the_guard_would_catch_a_planted_default_provider() -> None:
    """A denylist never shown to fire proves nothing."""
    planted = ast.parse(
        "\n".join(
            (
                "class LocalProvider:",
                "    def narrow(self, question, candidates):",
                "        return None",
            )
        )
    )
    concrete = [
        node.name
        for node in ast.walk(planted)
        if isinstance(node, ast.ClassDef)
        and not any("Protocol" in ast.unparse(base) for base in node.bases)
        and any(
            isinstance(child, ast.FunctionDef) and child.name == "narrow" for child in node.body
        )
    ]
    assert concrete == ["LocalProvider"]


def test_the_guard_would_catch_a_planted_environment_read() -> None:
    planted = ast.parse("import os\nkey = os.environ['OPENAI_API_KEY']\n")
    rendered = {
        ast.unparse(node)
        for node in ast.walk(planted)
        if isinstance(node, ast.Attribute | ast.Subscript)
    }
    assert any("environ" in entry for entry in rendered)


def test_the_module_names_no_provider_at_all() -> None:
    """`BO-4`: the baseline's `llm.primary_provider` is neither adopted nor contradicted."""
    source = PORT.read_text(encoding="utf-8").lower()
    for provider in ("openai", "anthropic", "gemini", "ollama", "claude", "gpt-", "llama"):
        assert provider not in source, f"the port names a provider: {provider}"


def test_the_module_is_a_protocol_and_helpers_only() -> None:
    """Enumerated, so anything new has to be argued for rather than added."""
    assert sorted(model_port.__all__) == [
        "CandidateOption",
        "CandidateSelection",
        "CandidateSet",
        "DelimitedQuestionData",
        "InterpretationModelPort",
        "narrow_candidates",
        "validate_selection",
    ]
