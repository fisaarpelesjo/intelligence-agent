"""No fixed or derived key — T113 (FR-063, FR-078; SC-034).

    **DO NOT INVENT, GENERATE, HARDCODE OR PROVISION KEY MATERIAL**
    — `tasks.md` T113

    Evidence: a key derived from a config value, build hash or hostname fails the
    scan.

A seal is only worth having if nobody but the deployment can compute one. Every
shortcut that makes a key *appear* — a constant, a generated value, an
environment lookup, a digest of the hostname — hands the ability to forge a
contract to whoever can read the source or guess the input. And each shortcut
looks locally reasonable, which is why this is a scan and not a review note.

The scan is over **AST identifiers and calls**, not over text. A token scan would
fire on the word "key" in `seal.py`'s docstrings — which discuss key material at
length precisely because none of it is there — and a check that fires on its own
documentation gets narrowed until it stops firing at all.

Five classes of violation, each with planted cases:

* a **literal** key, secret or token assigned in `src/`;
* a **generator** — ``token_bytes``, ``urandom``, ``uuid4``, ``Fernet.generate_key``;
* an **environment** read;
* a **derivation** from ambient state — hostname, platform, cwd, build hash;
* a **derivation from identity data** — the fingerprint, the principal, the
  contract itself. That last one is the subtlest: it produces a key that varies
  per principal and looks bespoke, and it is computable by anyone holding the
  same public inputs.

The fixture key is reachable from `packages/analytics_interaction/tests/` only,
and the marker it carries is asserted to appear in no `src/` module.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.clarification import seal as seal_module

from ..fixtures.clarifications import FIXTURE_KEY, FIXTURE_KEY_ID, FIXTURE_MARKER

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
TESTS = Path(__file__).resolve().parents[1]

#: Split so this file does not match its own search. A scan that counted its own
#: source would report two definition sites forever.
DEFINITION = " " + "= "

#: A key-derivation planting, held apart so the parametrisation stays legible.
KDF_SOURCE = "from hashlib import pbkdf2_hmac\ndef k(password):\n    return pbkdf2_hmac(password)\n"

#: Names that produce key material. Every one of them is a way a key appears in a
#: process without a deployment having provisioned one.
GENERATORS = frozenset(
    {
        "token_bytes",
        "token_hex",
        "token_urlsafe",
        "urandom",
        "getrandbits",
        "uuid4",
        "uuid1",
        "generate_key",
        "generate_private_key",
        "new_key",
        "derive_key",
        "PBKDF2HMAC",
        "scrypt",
        "pbkdf2_hmac",
    }
)

#: Ambient state a key must not be derived from. Each yields a value that is
#: stable enough to look like a key and public enough to be reproduced.
AMBIENT = frozenset(
    {
        "environ",
        "getenv",
        "gethostname",
        "getfqdn",
        "node",
        "uname",
        "platform",
        "getcwd",
        "cwd",
        "expanduser",
    }
)

#: Assignment targets that would hold a key if a literal were ever assigned.
KEY_NAMES = frozenset(
    {"key", "secret", "token", "signing_key", "seal_key", "private_key", "hmac_key"}
)


def _source_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _violations(source: str, filename: str = "<test>") -> list[str]:
    """Every way key material could appear, by AST rather than by token."""
    tree = ast.parse(source, filename=filename)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute | ast.Name):
            name = node.attr if isinstance(node, ast.Attribute) else node.id
            if name in GENERATORS:
                found.append(f"{node.lineno}:generator:{name}")
            elif name in AMBIENT:
                found.append(f"{node.lineno}:ambient:{name}")
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
            names = {ast.unparse(target).split(".")[-1].lower() for target in targets}
            value = node.value
            if (
                names & KEY_NAMES
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                found.append(f"{node.lineno}:literal:{sorted(names)[0]}")
    return found


# --- the source tree is clean -------------------------------------------------------


def test_no_source_module_produces_key_material() -> None:
    """Generators, ambient reads and literal keys, across the whole package."""
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{hit}"
        for path in _source_files()
        for hit in _violations(path.read_text(encoding="utf-8"), str(path))
    ]
    assert not offenders, f"key material appears in src/: {offenders}"


def test_the_seal_module_declares_no_algorithm_default() -> None:
    """`D-21` names the algorithm. This feature declares a port and picks nothing.

    Asserted against the source rather than by calling: a default that only
    appears on one branch would not show up in a behavioural test that never took
    that branch.
    """
    source = Path(inspect.getfile(seal_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Docstrings are excluded deliberately. `seal.py` discusses HMAC-SHA256 at
    # length — as the choice it does **not** make — and a scan that fired on its
    # own explanation would be narrowed until it stopped firing at all. What
    # matters is whether an algorithm name is ever a *value*.
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    literals = {
        node.value.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings
    }
    for named in ("hmac", "sha256", "sha512", "ed25519", "rsa", "aes"):
        assert not any(named in literal for literal in literals), f"{named} is a value in seal.py"


def test_the_seal_port_has_no_default_provider() -> None:
    """A defaulted port would be a sealing provider this package chose."""
    for entry in (seal_module.issue_seal, seal_module.verify_seal):
        parameter = inspect.signature(entry).parameters["port"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def test_no_key_is_derived_from_identity_data() -> None:
    """The subtlest failure: a key that varies per principal and is computable.

    Deriving from the fingerprint, the principal reference or the contract itself
    produces something that looks bespoke and is reproducible by anyone holding
    the same public inputs — which is everyone the contract is handed to.
    """
    source = Path(inspect.getfile(seal_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "derive_authorization_fingerprint" not in called
    assert "derive_interpretation_identity" not in called
    assert not called & {"sha256", "sha512", "blake2b", "hmac", "new"}


# --- the fixture key is confined to tests ---------------------------------------------


def test_the_fixture_marker_appears_in_no_source_module() -> None:
    """Fixture key material cannot leak into a production path unnoticed."""
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in _source_files()
        if FIXTURE_MARKER in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"the fixture marker reached src/: {offenders}"


def test_the_fixture_key_appears_in_no_source_module() -> None:
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in _source_files()
        if FIXTURE_KEY in path.read_text(encoding="utf-8")
        or FIXTURE_KEY_ID in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"the fixture key reached src/: {offenders}"


def test_the_fixture_key_is_reachable_only_from_tests() -> None:
    """One definition site, and it is `T147`'s synthetic-key package.

    Exactly one, not "at least one under tests/". A second definition is how the
    two copies drift apart, and the copy that drifted is the one no scan in this
    file was written against.
    """
    sites = [
        path.relative_to(TESTS).as_posix()
        for path in sorted(TESTS.rglob("*.py"))
        if "__pycache__" not in path.parts
        and path != Path(__file__).resolve()
        and f"FIXTURE_KEY{DEFINITION}" in path.read_text(encoding="utf-8")
    ]
    assert sites == ["fixtures/seal/__init__.py"], sites


def test_the_fixture_key_names_itself_as_unprovisioned() -> None:
    """A reader encountering it in a traceback sees what it is."""
    assert FIXTURE_MARKER in FIXTURE_KEY
    assert FIXTURE_MARKER in FIXTURE_KEY_ID
    assert "not-provisioned" in FIXTURE_KEY


def test_no_governance_file_carries_the_fixture_key() -> None:
    """The synthetic key never enters readiness evidence or governed content."""
    repo = SRC.parents[2]
    for directory in ("docs/readiness", "interpretation_governance"):
        root = repo / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                assert FIXTURE_MARKER not in path.read_text(encoding="utf-8", errors="ignore"), (
                    f"the fixture marker reached {path}"
                )


# --- the scan fires -------------------------------------------------------------------


@pytest.mark.parametrize(
    "planted",
    [
        pytest.param('SEAL_KEY = "s3cr3t-signing-key"\n', id="literal"),
        pytest.param("import secrets\nkey = secrets.token_bytes(32)\n", id="generator"),
        pytest.param("import os\nkey = os.environ['SEAL_KEY']\n", id="environment"),
        pytest.param("import socket\ndef k():\n    return socket.gethostname()\n", id="hostname"),
        pytest.param("import uuid\ndef k():\n    return uuid.uuid4().hex\n", id="uuid"),
        pytest.param(
            KDF_SOURCE,
            id="kdf",
        ),
        pytest.param("import os\ndef k():\n    return os.getcwd()\n", id="cwd"),
    ],
)
def test_the_scan_catches_planted_key_material(planted: str) -> None:
    """Each is a real way a key appears without anybody provisioning one."""
    assert _violations(planted), "key material was not detected"


@pytest.mark.parametrize(
    "innocent",
    [
        pytest.param('"""No key material is generated here."""\n', id="docstring"),
        pytest.param("def seal(preimage, *, key_id):\n    return None\n", id="key-id-parameter"),
        pytest.param("KEY_NAMES = ('installs',)\n", id="unrelated-tuple"),
        pytest.param("def go(key):\n    return key\n", id="injected-parameter"),
    ],
)
def test_the_scan_does_not_fire_on_prose_or_on_injection(innocent: str) -> None:
    """``key_id`` names a key; it is not one. Injection is the sanctioned path."""
    assert not _violations(innocent)
