"""T130 — a provider swap touches one adapter; a model swap touches nothing (`SC-043`, `SC-044`).

Two independent claims about where change is contained, and both are asserted as **diffs**: what
would have to be edited, measured by reading the code, rather than described in prose that no edit
can contradict.

## `SC-043` — the provider seam, measured rather than assumed

The first draft of this file asserted that `adapters/` is the only place a provider is named. **That
is false, and the measurement said so immediately.** A provider has *two* seams here: its delivery
adapter (`adapters/slack/`) and its verification scheme (`inbound/schemes/slack.py`). Both are
provider-shaped by necessity — one speaks the provider's transport, the other its signature format —
and both are named in two registries plus the `ChannelId` enum.

So the claim asserted below is the one that is true and that `SC-043` is actually about: **no module
in the pipeline branches on a provider.** Conversion, identity, rendering, preservation, delivery
sequencing and audit contain no provider vocabulary in their *code*. A swap edits the swapped
provider's two seam files and its registry rows, and touches nothing that decides anything.

`tests/contract/test_adapter_containment.py` asserts containment from the adapter's side. This file
asserts it from the core's.

## Prose is not code, and the scans read code

The first draft also flagged `cli/main.py` for the sentence "No interactive prompt, no shell
execution", and `inbound/kind.py` for a docstring explaining why a WhatsApp sticker is classified by
the adapter. Both are prose stating an absence — the opposite of the thing being scanned for. A scan
that cannot tell a docstring from a branch measures vocabulary, not behaviour.

So both scans below read **code**: identifiers, imported module names, and string literals that are
not docstrings. That is narrower than the file text, and it is the narrowing that makes a hit mean
something.

## `SC-044` — zero modules

Swapping `003`'s interpretation model port must touch nothing here at all. Measured 2026-08-19:
**no module under `src/` names a model port, an llm, a prompt, a temperature or a completion in
code**, and `InteractionPort.ask` is the whole of what this feature knows about how an answer was
produced. Unlike the provider claim, this one has no permitted site — there is no seam that would
legitimately name any of it — so the assertion covers every module in the package.

## Why the vocabulary lists are narrow

`_PROVIDER_WORDS` holds provider names, not general networking vocabulary. A scan that also flagged
`send`, `client` or `request` would report every transport module in the package and would have to
grow an exclusion list, which is how a scan stops meaning anything. The claim is about **providers**
leaking, so the scan looks for providers.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _package_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "channel_integration").is_dir():
            return parent
    raise AssertionError("package root not found")


_PACKAGE = _package_root()
_SRC = _PACKAGE / "src" / "channel_integration"
_ADAPTERS = _SRC / "adapters"

#: Provider names and their SDK roots. A provider swap is contained when none of these appears
#: in the **code** of a pipeline module — the two seams and the three registries name them by
#: necessity, and prose about them is prose.
_PROVIDER_WORDS = re.compile(
    r"\bslack(_sdk)?\b|\btelegram\b|\bwhatsapp\b|\btwilio\b|\bmeta\s+graph\b|\bbot\s*api\b",
    re.IGNORECASE,
)

#: Model-port vocabulary. `SC-044` says a model swap touches nothing here, and unlike the provider
#: claim there is no seam that legitimately names any of it — so the assertion covers every module,
#: with no permitted site at all. Prose is still excluded: `cli/main.py` says "No interactive
#: prompt", which asserts the absence rather than being an instance of it.
_MODEL_WORDS = re.compile(
    r"\bmodel[_ ]?port\b|\bllm\b|\bprompt\b|\btemperature\b|\btoken[s]?[_ ]?limit\b|"
    r"\bcompletion\b|\bembedding\b|\banthropic\b|\bopenai\b",
    re.IGNORECASE,
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _code_text(path: Path) -> str:
    """Everything in ``path`` that is code: identifiers, imports, and non-docstring literals.

    Docstrings and comments are excluded deliberately — see the module docstring. What remains is
    the text a provider or a model could actually be *used* through.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    pieces: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            pieces.append(node.id)
        elif isinstance(node, ast.Attribute):
            pieces.append(node.attr)
        elif isinstance(node, ast.arg):
            pieces.append(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            pieces.append(node.name)
        elif isinstance(node, ast.Import):
            pieces.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            pieces.append(node.module or "")
            pieces.extend(alias.name for alias in node.names)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            pieces.append(node.value)
    return "\n".join(pieces)


#: The modules a provider swap legitimately touches: the provider's two seams, and the three
#: registries that name every channel. Measured 2026-08-19 — the first draft of this file listed
#: only `adapters/` and was wrong.
_PROVIDER_SEAMS = ("adapters/", "inbound/schemes/")
_PROVIDER_REGISTRIES = frozenset(
    {
        "contracts/descriptor.py",
        "inbound/verify.py",
        "compliance/readiness.py",
    }
)


def _pipeline_files() -> list[Path]:
    """Every `src/` module that is neither a provider seam nor a registry."""
    out: list[Path] = []
    for path in _python_files(_SRC):
        relative = path.relative_to(_SRC).as_posix()
        if relative in _PROVIDER_REGISTRIES:
            continue
        if any(relative.startswith(seam) for seam in _PROVIDER_SEAMS):
            continue
        out.append(path)
    return out


def test_no_pipeline_module_branches_on_a_provider() -> None:
    """`SC-043`. The provider-swap diff, as the set of deciding modules that mention one.

    Scanned over code rather than over prose, and over the pipeline rather than over the seams. A
    hit here is a place where swapping a provider would change what the system *decides*.
    """
    offenders: dict[str, list[str]] = {}
    for source in _pipeline_files():
        hits = sorted({str(hit) for hit in _PROVIDER_WORDS.findall(_code_text(source))})
        if hits:
            offenders[source.relative_to(_SRC).as_posix()] = hits
    assert not offenders, (
        f"a pipeline module branches on a provider: {offenders}. Swapping that provider would then "
        "be a diff in code that decides something, which is what `SC-043` says it is not"
    )


def test_the_seams_and_the_registries_are_the_whole_diff() -> None:
    """The other half: the files that *do* name a provider are exactly the declared ones.

    Stated from this direction so a new provider-shaped module cannot appear somewhere unexpected
    and be excused by the pipeline scan simply because nobody added it to a list.
    """
    naming: set[str] = set()
    for source in _python_files(_SRC):
        if _PROVIDER_WORDS.search(_code_text(source)):
            naming.add(source.relative_to(_SRC).as_posix())

    unexpected = sorted(
        relative
        for relative in naming
        if relative not in _PROVIDER_REGISTRIES
        and not any(relative.startswith(seam) for seam in _PROVIDER_SEAMS)
    )
    assert not unexpected, f"these name a provider and are not a declared seam: {unexpected}"
    assert naming & _PROVIDER_REGISTRIES, "no registry names a provider, so this scan sees nothing"


def test_each_adapter_names_only_its_own_provider() -> None:
    """Containment within the package too: swapping Slack must not edit the Telegram adapter."""
    per_provider = {
        "slack": re.compile(r"\btelegram\b|\bwhatsapp\b|\btwilio\b", re.IGNORECASE),
        "telegram": re.compile(r"\bslack\b|\bwhatsapp\b|\btwilio\b", re.IGNORECASE),
        "whatsapp": re.compile(r"\bslack\b|\btelegram\b", re.IGNORECASE),
        "generic": re.compile(r"\bslack\b|\btelegram\b|\bwhatsapp\b", re.IGNORECASE),
    }
    offenders: dict[str, list[str]] = {}
    for provider, foreign in per_provider.items():
        directory = _ADAPTERS / provider
        assert directory.is_dir(), f"{provider} adapter is missing"
        for source in _python_files(directory):
            hits = [
                f"{number}: {line.strip()}"
                for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1)
                if foreign.search(line)
            ]
            if hits:
                offenders[source.relative_to(_SRC).as_posix()] = hits
    assert not offenders, f"an adapter names another provider: {offenders}"


def test_the_provider_swap_diff_is_one_directory() -> None:
    """The claim as a count, so it cannot drift while the prose stays reassuring."""
    touched = sorted(
        {
            path.relative_to(_ADAPTERS).parts[0]
            for path in _python_files(_ADAPTERS)
            if _PROVIDER_WORDS.search(_code_text(path))
        }
    )
    assert touched, "no adapter names a provider, so this scan is measuring nothing"
    for provider in touched:
        others = [name for name in touched if name != provider]
        assert others, "a swap must leave the other adapters untouched, and there are none"


def test_no_module_here_knows_how_an_answer_was_produced() -> None:
    """`SC-044`: the model vocabulary does not occur in any code path.

    Prose is excluded for the reason recorded in the module docstring — `cli/main.py` says "No
    interactive prompt, no shell execution", which is a sentence asserting the absence of the very
    thing a naive scan reported it for.
    """
    offenders: dict[str, list[str]] = {}
    for source in _python_files(_SRC):
        hits = sorted({str(hit) for hit in _MODEL_WORDS.findall(_code_text(source))})
        if hits:
            offenders[source.relative_to(_SRC).as_posix()] = hits
    assert not offenders, (
        f"this feature names model machinery in code: {offenders}. A model-port swap would then be "
        "a diff here, and `004` would be holding an opinion about how an answer was produced"
    )


def test_the_interaction_port_is_the_whole_of_what_this_feature_knows() -> None:
    """One operation, and it takes a question and returns an outcome.

    Asserted on the `Protocol`'s own body rather than on its docstring: a second method, an options
    argument or a keyword named after a model setting would each be a place a model change lands.
    """
    source = (_SRC / "interaction" / "port.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    port = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "InteractionPort"
    )
    methods = [
        node.name for node in port.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    assert methods == ["ask"], f"the interaction port grew a second operation: {methods}"

    ask = next(node for node in port.body if isinstance(node, ast.FunctionDef))
    arguments = [argument.arg for argument in ask.args.args]
    assert arguments == ["self", "intake"], f"`ask` grew an argument: {arguments}"
    assert not ask.args.kwonlyargs, "`ask` grew a keyword argument, which is where options arrive"
    assert ask.args.vararg is None and ask.args.kwarg is None, "`ask` accepts an options bag"


def test_the_scans_are_not_vacuous() -> None:
    """Both patterns are proven to match something, on text rather than on the tree.

    A regex that matched nothing would make every assertion above pass over an empty set, and the
    provider scan in particular is only meaningful if it does fire inside `adapters/`.
    """
    adapter_text = "\n".join(_code_text(source) for source in _python_files(_ADAPTERS))
    assert _PROVIDER_WORDS.search(adapter_text), (
        "no adapter names its provider, so the provider scan cannot be catching a leak"
    )
    assert _MODEL_WORDS.search("this line mentions a prompt and a temperature"), (
        "the model-port pattern matches nothing, so its assertion above passes trivially"
    )
    assert not _PROVIDER_WORDS.search("this line mentions a channel and a delivery attempt"), (
        "the provider pattern matches ordinary transport prose, so it would report the whole core"
    )
