"""Fixtures stay in the tests — T070 (FR-072; SC-034).

The fixtures in `tests/fixtures/` describe a world that does not exist: descriptors that are
**enabled**, verification material that **verifies**, a pseudonymisation key that **works**. In
production none of that is true — `D-22` to `D-26` and `D-31` are undeclared, so the real path
resolves nothing and refuses.

That gap is the reason containment is a security property rather than hygiene. A fixture reachable
from `src` would be an enabled channel with working credentials, selectable by whoever can set a
flag, and every refusal this feature relies on would become optional.

So three things are asserted:

* **no `src` module references a fixture** — by import scan and by name scan, because a fixture can
  be reached by importing it or by re-implementing its name;
* **no flag, environment variable or mode selects one** — a ``FIXTURE_MODE`` env var would be a
  supported way to turn the refusals off;
* **`enabled` is not settable from configuration** — the descriptor's flag is derived from the
  readiness record, and the fixture may set it *because it is a fixture*, stated here so the
  exception is visible rather than discovered.

The complement is asserted too: the fixtures **are** importable from tests. A containment test that
passed because the fixtures did not exist would be worthless.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_PACKAGE = Path(__file__).resolve().parents[2]
_SRC = _PACKAGE / "src" / "channel_integration"
_FIXTURES = _PACKAGE / "tests" / "fixtures"


#: Every public name the fixture modules export. Assembled from the modules themselves, so a new
#: fixture is covered the moment it is added rather than when someone remembers to list it here.
def _fixture_names() -> set[str]:
    names: set[str] = set()
    for source in sorted(_FIXTURES.glob("*.py")):
        for match in re.finditer(
            r"^(?:def|class)\s+(\w+)", source.read_text(encoding="utf-8"), re.M
        ):
            names.add(match.group(1))
        for match in re.finditer(
            r"^(FIXTURE_\w+|AT)\s*[:=]", source.read_text(encoding="utf-8"), re.M
        ):
            names.add(match.group(1))
    return {name for name in names if not name.startswith("_")}


def test_the_fixtures_exist_and_export_something() -> None:
    """Without this, every containment assertion below would pass over an empty set."""
    names = _fixture_names()
    assert len(names) >= 10, f"only {len(names)} fixture names were found: {sorted(names)}"
    assert "FIXTURE_MATERIAL" in names
    assert "descriptor_for" in names
    assert "fixture_pseudonymiser" in names


def test_no_src_module_imports_a_fixture() -> None:
    """The direct route."""
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if re.match(r"^\s*(?:from|import)\s+", line) and (
                "fixture" in line.lower() or re.search(r"\btests?\b", line)
            ):
                offenders.append(f"{source.relative_to(_SRC)}:{number}: {line.strip()}")
    assert not offenders, offenders


def test_no_src_module_references_a_fixture_name() -> None:
    """The indirect route: reaching a fixture by re-declaring its name.

    Docstrings are included deliberately. A `src` docstring that names `FIXTURE_MATERIAL` is a sign
    the boundary is being reasoned across, and the cost of the stricter rule is that prose in `src`
    refers to fixtures by description rather than by identifier.
    """
    names = _fixture_names()
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for name in sorted(names):
            if re.search(rf"\b{re.escape(name)}\b", text):
                offenders.append(f"{source.relative_to(_SRC)}: {name}")
    assert not offenders, offenders


def _code_identifiers_and_literals(source: Path) -> set[str]:
    """Every identifier and non-docstring string literal in ``source``.

    Parsed rather than grepped, because several `src` modules **explain** this rule in prose and a
    line scan cannot tell an explanation from a switch. Excluding docstrings is what lets the rule
    below be about code while the modules stay free to say why the rule exists.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    # Identified by node identity rather than by value: `ast.get_docstring` returns the *cleaned*
    # text, which never equals the raw constant, so a value comparison would silently match nothing.
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.keyword):
            # ``**kwargs`` carries no name, and an unnamed argument names no fixture.
            found.add(node.arg or "")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            found.add(node.value)
    return found


def _limitation_statements(source: Path) -> frozenset[str]:
    """Every string assigned to a `*_LIMITATION` name in ``source``.

    Read by :mod:`ast` rather than by pattern, so the exclusion is anchored to the assignment that
    declares the disclaimer instead of to any sentence that happens to look like one.
    """
    if not source.is_file():
        return frozenset()
    module = ast.parse(source.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.Assign):
            continue
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if not any(name.endswith("_LIMITATION") for name in names):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.add(value.value)
    return frozenset(found)


def test_no_flag_environment_variable_or_mode_selects_a_fixture() -> None:
    """`FR-072`: not "off by default" — unselectable.

    Over **code** only: no identifier, keyword argument or string literal names a fixture, a
    simulator, a sandbox, a demo, a mock or a test mode. A module may describe the rule in its
    docstring — several do, because the rule is the reason those modules are shaped as they are.
    """
    forbidden = re.compile(r"FIXTURE|SANDBOX|DRY_RUN|TEST_MODE|DEMO|MOCK|STUB|FAKE", re.IGNORECASE)
    #: `SIMULAT` is checked separately, and in **two** declared places rather than one — review
    #: finding AA caught the earlier comment claiming one while the list held two:
    #:
    #: * `cli/simulate.py`, the module `T151` declares;
    #: * `cli/main.py`, because `T150` declares a `simulate` subcommand and it imports the
    #:   simulator's disclaimer constant, so the word necessarily appears in the parser wiring.
    #:
    #: Anywhere else is a failure, and being authorized in those two is not the same as being
    #: unchecked: the two assertions that follow constrain what the simulator may do.
    simulator = re.compile(r"SIMULAT", re.IGNORECASE)
    permitted_simulator_paths = {"cli/simulate.py", "cli/main.py"}

    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        relative = source.relative_to(_SRC).as_posix()
        disclaimers = _limitation_statements(source)
        for token in sorted(_code_identifiers_and_literals(source)):
            if token in disclaimers:
                # The `FR-099` disclaimer has to say it used fixture payloads. Excluding it here is
                # not a loophole: the assertion below requires it to say exactly that, so the one
                # literal permitted to name fixtures is the one that must.
                continue
            if forbidden.search(token):
                offenders.append(f"{relative}: {token!r}")
            if simulator.search(token) and relative not in permitted_simulator_paths:
                offenders.append(
                    f"{relative}: {token!r} (simulator naming outside the two declared modules)"
                )
    assert not offenders, offenders


def test_the_only_literal_permitted_to_name_fixtures_is_the_one_required_to() -> None:
    """The other half of the exclusion above, so it stays an exclusion and not a hole.

    Exactly one `*_LIMITATION` statement lives in the simulator module, and it must disclose both
    that fixture payloads were used and that no provider was contacted. If somebody softened that
    sentence, the scan above would stop excluding it — and this fails first, with the reason.
    """
    statements = _limitation_statements(_SRC / "cli" / "simulate.py")
    assert len(statements) == 1, f"expected one limitation statement, found {len(statements)}"
    statement = next(iter(statements))
    for required in ("fixture", "não contata nenhum provedor", "não é evidência"):
        assert required in statement, f"the simulator disclaimer no longer says {required!r}"


def test_the_declared_simulator_selects_no_fixture_and_relaxes_nothing() -> None:
    """The compensating assertion for the narrowing above (`FR-072`, `R-19`).

    A declared simulator is not a fixture mode, and the difference is checkable rather than a matter
    of intent: it must take the recorded payload as a **parameter**, reach no path under `tests/`,
    and call the same production functions the real path calls. A simulator holding its own
    payloads, or its own lenient conversion, would be the "off by default" arrangement `FR-072`
    refuses.
    """
    simulate = _SRC / "cli" / "simulate.py"
    assert simulate.is_file(), "T151 declares this module"
    module = ast.parse(simulate.read_text(encoding="utf-8"))

    functions = {node.name: node for node in ast.walk(module) if isinstance(node, ast.FunctionDef)}
    for name in ("simulate_conversion", "simulate_rendering"):
        assert name in functions, f"{name} is missing"
        arguments = functions[name].args
        assert arguments.args or arguments.posonlyargs, (
            f"{name} takes no positional payload, so it must be sourcing one itself"
        )

    #: The production functions, called by name. A simulator that reimplemented conversion would
    #: satisfy every assertion above while diverging from what production does.
    called = {
        node.func.id
        for node in ast.walk(module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"convert", "render_for_channel"} <= called, (
        f"the simulator does not call the production entry points; it calls {sorted(called)}"
    )

    #: Checked over **imports** rather than over the file's text: this module's docstring explains
    #: why it does not reach `tests/`, and a text scan flags that explanation as the thing it warns
    #: about — the defect class this feature has already corrected four times.
    imported: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [name for name in imported if "test" in name.lower()], (
        f"the simulator imports test material: {imported}"
    )


def test_no_governed_document_in_src_carries_fixture_material() -> None:
    """The governed content files ship with the package and are a place material could hide."""
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*")):
        if source.is_dir() or source.suffix in {".py", ".pyc"}:
            continue
        text = source.read_text(encoding="utf-8", errors="ignore")
        for token in ("fixture", "not-a-credential", "secret", "token"):
            if token in text.lower():
                offenders.append(f"{source.relative_to(_SRC)}: {token}")
    assert not offenders, offenders


def test_the_enabled_flag_is_not_settable_from_configuration_in_src() -> None:
    """The fixture may set ``enabled`` because it is a fixture. `src` may not.

    Stated as an explicit exception, so a reader does not have to infer why the fixture is allowed
    to do the one thing this test forbids.
    """
    fixture_text = (_FIXTURES / "channels.py").read_text(encoding="utf-8")
    assert "enabled" in fixture_text, "the fixture is expected to set the flag it is exempt on"

    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            if re.search(r"enabled\s*=\s*(?:True|1|['\"])", code):
                offenders.append(f"{source.relative_to(_SRC)}:{number}: {line.strip()}")
    assert not offenders, offenders


def test_the_fixtures_are_importable_from_the_tests() -> None:
    """The complement. Containment must not be satisfied by fixtures that do not work."""
    from channel_integration.contracts.descriptor import ChannelId

    from ..fixtures.channels import FIXTURE_MATERIAL, descriptor_for
    from ..fixtures.identity import fixture_pseudonymiser

    assert descriptor_for(ChannelId.SLACK).enabled is True
    assert FIXTURE_MATERIAL.active
    assert fixture_pseudonymiser().key_version == "fixture-key-1"


def test_the_fixture_directory_is_not_packaged() -> None:
    """A wheel that shipped the fixtures would ship an enabled channel with working material."""
    manifest = (_PACKAGE / "pyproject.toml").read_text(encoding="utf-8")
    assert 'packages = ["src/channel_integration"]' in manifest
    assert (
        "tests" not in manifest.split("[tool.hatch.build.targets.wheel]", 1)[1].split("\n\n", 1)[0]
    )
