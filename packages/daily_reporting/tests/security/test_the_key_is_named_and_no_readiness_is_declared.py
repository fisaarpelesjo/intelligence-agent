"""The key is named and never its value, and nothing here declares readiness — `T827`, `T828`.

Both tasks ask for the same thing in two subjects, and both ask for the part that is easy to
skip: **not that the tree is clean today, but that something bites when it stops being.**
A rule nothing enforces is prose, and prose that no node reads aged three times in one day on
this branch — `S-5`, `S-6`, and a gate that read green because its nodes were skipping.

## `T827` — the value of a secret-bearing key is never asserted about

`FR-202`, the standing constraint. `007` states it in two docstrings — *"no node asserts about
the value of a secret-bearing key, only about the key"* — and **a docstring is exactly what
`S-5` proved cannot hold a rule up.** The key's NAME is the contract; what it holds is the
owner's. A node that asserted the value would put the value in a file, in a diff, and in
every CI log that ever prints a failure.

## `T828` — no production readiness is declared and no readiness record is written

`FR-819`. **And the subtlety is worth stating, because getting it backwards would be the
defect:** this asserts that NOBODY declared readiness for this feature. It is not itself a
declaration, it cannot become one, and it takes no position on the records `001` through
`004` own — `d_24` is `004`'s, signed by the owner, and none of this feature's business.

## What these guards do NOT catch, declared rather than left to be found

**This paragraph was wrong when it was first written, and `S-7a` is what it cost.** It said
the escapes were indirection, and named none. Four direct forms escaped —
``token.startswith('123')``, ``token.endswith('xyz')``, ``len(token) == 45`` and
``token[:3] == '123'`` — because the predicate only walked comparisons and only recognised a
secret as a bare operand. **None of those is indirection**: same file, same expression, one
wrapper. They are caught now, and *"it escapes and nobody said which"* is what the sentence
below refuses to be.

What still escapes, **named**: a value assembled from pieces that are individually innocent
(``assert token[0] == 'a'`` is caught, ``assert first + second == 'ab'`` is not, when neither
half reaches a secret read); and a value reached through a helper defined in another module,
because the sweep reads one file at a time and does not follow a call into its definition.

And `T828` sees declarations in the readiness records and writes in this feature's source; a
declaration made somewhere neither of those covers is outside its reach.

**Each guard bites one recurring shape**, which is the same limit the `S-5` guard writes down
about itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: `tests/security/` -> `tests/` -> package.
PACKAGE = Path(__file__).resolve().parents[2]
TESTS = PACKAGE / "tests"
SOURCE = PACKAGE / "src" / "daily_reporting"


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


REPO = _repository_root()
READINESS = REPO / "docs" / "readiness"

#: This feature, as the records name features. **Asserted to exist below** rather than
#: trusted: a rename that made this string match nothing would turn `T828` into a node that
#: passes by looking for something that is not there — the vacuity `S-6` was about.
THIS_FEATURE = "008-daily-report-and-rule-alerts"

#: A key is secret-bearing by the SHAPE of its name, not by appearing in a list. A list is an
#: enumeration nothing forces to stay complete, which is what `S-4` was; a pattern covers the
#: key somebody adds next week without anybody remembering this file.
SECRET_NAME_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "API_KEY",
    "CHAT_ID",
)


def names_a_secret(text: str) -> bool:
    """Does ``text`` name a secret-bearing key?"""
    upper = text.upper()
    return any(marker in upper for marker in SECRET_NAME_MARKERS)


def _reads_a_secret(node: ast.expr, bound: set[str]) -> bool:
    """Is ``node`` ITSELF a read of a secret-bearing key, or a name bound from one?"""
    if isinstance(node, ast.Name):
        return node.id in bound or names_a_secret(node.id)
    if isinstance(node, ast.Subscript):
        key = node.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return names_a_secret(key.value)
        if isinstance(key, ast.Name):
            return names_a_secret(key.id)
        return False
    if isinstance(node, ast.Call):
        called = node.func
        if isinstance(called, ast.Attribute) and called.attr in {"get", "getenv"}:
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return names_a_secret(first.value)
            if isinstance(first, ast.Name):
                return names_a_secret(first.id)
        return False
    return False


def _reaches_a_secret(node: ast.expr, bound: set[str]) -> bool:
    """Does ``node`` reach a secret-bearing read **anywhere inside it**?

    **`S-7a`, and this recursion is the whole repair.** The first version asked whether an
    operand *was* a secret read, so anything wrapped around one hid it: ``len(token) == 45``
    is a comparison whose operand is a `Call`, and ``token[:3] == '123'`` is a `Subscript`
    whose slice is an `ast.Slice` rather than a constant. Neither is indirection — same file,
    same expression, one wrapper — and both put the secret's shape in the diff exactly the way
    ``==`` does.
    """
    if _reads_a_secret(node, bound):
        return True
    return any(
        _reaches_a_secret(child, bound)
        for child in ast.iter_child_nodes(node)
        if isinstance(child, ast.expr)
    )


def _is_a_value_literal(node: ast.expr) -> bool:
    """A literal that would BE the secret, or part of it, if the assertion held.

    ``None`` and the booleans are not values in this sense: *the key is absent* and *the key
    is present* are statements about the key, which is exactly what stays permitted.
    """
    return (
        isinstance(node, ast.Constant)
        and node.value is not None
        and not isinstance(node.value, bool)
        and isinstance(node.value, str | int | float)
    )


def assertions_about_a_secret_value(source: str) -> list[tuple[int, str]]:
    """Every assertion in ``source`` that puts a secret-bearing read next to a literal.

    **The pure predicate, so every direction can be driven without a repository.** It reads
    the syntax tree rather than the file's text: a node that forbade a list of words would
    contain that list and accuse itself, which is the self-reference
    `test_nothing_is_signed_and_nothing_is_written.py` had to avoid in this same directory.

    Two shapes, and the second is the one `S-7a` added:

    * a **comparison** with a secret-reaching operand on one side and a value literal on the
      other — ``token == 'abc'``, ``'abc' in token``, ``len(token) == 45``, ``token[:3] == '1'``;
    * a **call on the secret itself** carrying a literal argument — ``token.startswith('123')``,
      ``token.endswith('xyz')``, ``token.count('-')``. No method list: any call whose receiver
      reaches a secret and whose argument is a literal is asking a question whose answer is
      part of the value. **A list of method names would be an enumeration nothing forces to
      stay complete**, which is what `S-4` was.
    """
    tree = ast.parse(source)

    #: Names bound from a secret-bearing read, so `recipient = env[KEY]` followed by an
    #: assertion about `recipient` is seen for what it is.
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _reaches_a_secret(node.value, set()):
            bound.update(target.id for target in node.targets if isinstance(target, ast.Name))

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        for inner in ast.walk(node.test):
            if isinstance(inner, ast.Compare):
                operands = [inner.left, *inner.comparators]
                reads = [side for side in operands if _reaches_a_secret(side, bound)]
                literals = [side for side in operands if _is_a_value_literal(side)]
                if reads and literals:
                    found.append((node.lineno, ast.unparse(inner)))
            elif isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                receiver = inner.func.value
                arguments = [*inner.args, *(keyword.value for keyword in inner.keywords)]
                if _reaches_a_secret(receiver, bound) and any(
                    _is_a_value_literal(argument) for argument in arguments
                ):
                    found.append((node.lineno, ast.unparse(inner)))
    return found


def readiness_records() -> list[Path]:
    return sorted(path for path in READINESS.glob("*.yaml"))


#: The one record that predates the schema header, named with its reason and **verified
#: below rather than trusted**. `docs/readiness/external-readiness.yaml` is `001`'s and was
#: written before records carried `feature:`, which `004`'s `readiness.py` already records.
#:
#: It is safe to exempt for one reason and the reason is checked: the file must not mention
#: this feature at all. A record for `008` could not hide here, because hiding here requires
#: being named here, and being named here is a decision somebody makes in a diff.
RECORDS_WITHOUT_A_FEATURE_LINE: dict[str, str] = {
    "external-readiness.yaml": "001's record, written before the schema header existed",
}


def features_that_own_a_record() -> dict[str, str | None]:
    """Which feature each readiness record names — **every record, or ``None``**.

    **`S-7b`.** The first version simply did not insert a record whose `feature:` line it
    could not find, so four records produced three owners and the fourth vanished. A record
    of THIS feature whose line was missing, indented or spelled differently would have been
    invisible, and the node above would have stayed green saying nobody declared anything.

    **A sweep that drops what it cannot read and reports clean is the shape of `S-4`, of
    `S-6`, and of the gate that read green because its nodes were skipping** — so nothing is
    dropped: what cannot be read comes back as ``None`` and is answered for by name.
    """
    owners: dict[str, str | None] = {}
    for path in readiness_records():
        owners[path.name] = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("feature:"):
                owners[path.name] = line.split(":", 1)[1].strip()
                break
    return owners


def _test_modules() -> list[Path]:
    return sorted(
        path
        for path in TESTS.rglob("*.py")
        if "__pycache__" not in path.parts and path.resolve() != Path(__file__).resolve()
    )


def _source_modules() -> list[Path]:
    return sorted(path for path in SOURCE.rglob("*.py") if "__pycache__" not in path.parts)


def test_the_sweeps_reach_something() -> None:
    """A sweep over nothing forbids nothing — the `F115` shape, stated before the sweeps are.

    **`S-7b` moved one of these from the input to the output.** It asserted that at least three
    readiness records were FOUND, which is the entry to the reading; the blind spot was on the
    way out, where four records produced three owners and nobody counted the difference.
    """
    assert len(_test_modules()) >= 8, f"the test sweep found {len(_test_modules())} modules"
    assert len(_source_modules()) >= 10, f"the source sweep found {len(_source_modules())}"

    records = readiness_records()
    owners = features_that_own_a_record()
    assert len(records) >= 3, f"the readiness sweep found {len(records)} records"
    #: **The output, one entry per record, no silent drop.**
    assert len(owners) == len(records), (
        f"{len(records)} records produced {len(owners)} entries; a record the reading dropped "
        "is a record that cannot be answered for"
    )
    assert sum(1 for feature in owners.values() if feature is not None) >= 3, (
        f"only {sorted(name for name, f in owners.items() if f is not None)} named a feature"
    )
    #: And the feature id must name something, or `T828` looks for what is not there.
    assert (REPO / "specs" / THIS_FEATURE).is_dir(), (
        f"{THIS_FEATURE} names no spec directory; this node would pass by finding nothing"
    )


def test_no_node_of_this_feature_asserts_about_a_secret_value() -> None:
    """`T827`. The key is named; what it holds is the owner's."""
    offending: list[str] = []
    for path in _test_modules():
        for line, comparison in assertions_about_a_secret_value(path.read_text(encoding="utf-8")):
            offending.append(f"{path.relative_to(PACKAGE).as_posix()}:{line}: {comparison}")
    assert not offending, (
        "these assert about the VALUE of a secret-bearing key rather than about the key, and "
        "a value asserted here is a value in the diff and in every CI log that prints the "
        "failure:\n" + "\n".join(offending)
    )


def test_the_secret_value_guard_bites() -> None:
    """**Read this before believing the node above** — the mutation `T827`'s criterion names.

    A guard that matched nothing would report a clean feature forever. Every shape below was
    driven one at a time: the six the reviewer wrote out in `S-7a`, and the ones that must
    stay permitted.

    **Four of these passed when this file was first written**, and none of them was
    indirection: ``startswith``, ``endswith``, ``len(...) ==`` and a slice are direct
    assertions, same file, same expression. `startswith` is the second most obvious way to
    write the forbidden thing after ``==``, and a secret compared by prefix reaches the diff
    and the CI log exactly as one compared by equality.
    """
    prelude = "def test_decorative():\n    tok = os.environ['TELEGRAM_BOT_TOKEN']\n    assert "
    for forbidden in (
        "tok == 'abc'",
        "'abc' in tok",
        "tok.startswith('123')",
        "tok.endswith('xyz')",
        "len(tok) == 45",
        "tok[:3] == '123'",
        "tok.count('-') == 4",
    ):
        caught = assertions_about_a_secret_value(prelude + forbidden + "\n")
        assert caught, f"the guard does not see {forbidden!r}, which is the thing it forbids"

    #: Reached without a bound name, straight off the read.
    for direct in (
        "def t():\n    assert environment['TELEGRAM_ALLOWED_CHAT_ID'] == '123456789'\n",
        "def t():\n    assert environment.get(RECIPIENT_CHAT_ID) == '42'\n",
        "def t():\n    assert environment['TELEGRAM_BOT_TOKEN'].startswith('123')\n",
    ):
        assert assertions_about_a_secret_value(direct), f"not caught: {direct!r}"

    #: What must stay permitted: statements about THE KEY.
    for permitted in (
        "def t():\n    assert environment['TELEGRAM_ALLOWED_CHAT_ID'] is not None\n",
        "def t():\n    assert RECIPIENT_KEY == 'TELEGRAM_ALLOWED_CHAT_ID'\n",
        "def t():\n    assert environment.get('TELEGRAM_BOT_TOKEN') is None\n",
        "def t():\n    assert 'TELEGRAM_BOT_TOKEN' in environment\n",
        "def t():\n    assert rendered == 'a line with no secret in it'\n",
    ):
        assert not assertions_about_a_secret_value(permitted), (
            f"an assertion about the KEY was refused: {permitted!r}"
        )


def test_every_readiness_record_is_answered_for() -> None:
    """`S-7b`. **A record the reading cannot name is refused, never dropped.**

    The reading returns one entry per record and ``None`` where it found no `feature:` line.
    Exactly one file may answer ``None``, it is named in `RECORDS_WITHOUT_A_FEATURE_LINE` with
    its reason, and the exemption is checked rather than trusted: the exempt file must not
    mention this feature at all, and an exemption for a file that has grown a `feature:` line
    is dead weight that fails here.
    """
    owners = features_that_own_a_record()
    unnamed = sorted(name for name, feature in owners.items() if feature is None)
    unexplained = [name for name in unnamed if name not in RECORDS_WITHOUT_A_FEATURE_LINE]
    assert not unexplained, (
        f"{unexplained} declare no feature and are named nowhere; a record this reading "
        "cannot name could be a declaration for any feature, including this one"
    )

    for name, reason in RECORDS_WITHOUT_A_FEATURE_LINE.items():
        path = READINESS / name
        assert path.is_file(), f"{name} is exempted and does not exist; the reason was {reason!r}"
        assert name in unnamed, (
            f"{name} now declares a feature and no longer needs the exemption; a name for a "
            "situation that has passed is a decision pretending to still be one"
        )
        #: **This is what makes the exemption safe**, and it is measured, not asserted in prose.
        assert THIS_FEATURE not in path.read_text(encoding="utf-8"), (
            f"{name} is exempted from naming a feature and mentions {THIS_FEATURE}"
        )


def test_this_feature_declares_no_readiness_and_owns_no_record() -> None:
    """`T828`. **Asserting that nobody declared, which is not itself a declaration.**

    The four records belong to `001` through `004`. This feature owns none, and what those
    records declare is their owners' business — `d_24` is `004`'s, signed by him.
    """
    owners = features_that_own_a_record()
    assert THIS_FEATURE not in owners.values(), (
        f"{sorted(name for name, feature in owners.items() if feature == THIS_FEATURE)} "
        f"declare readiness for {THIS_FEATURE}; this feature declares none"
    )


def test_nothing_under_this_feature_writes_a_readiness_record() -> None:
    """`T828`, the other half: a declaration cannot be made by writing one either."""
    offending: list[str] = []
    for path in _source_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = node.func
                reached = (
                    called.attr
                    if isinstance(called, ast.Attribute)
                    else called.id
                    if isinstance(called, ast.Name)
                    else ""
                )
                if reached not in {"open", "write_text", "write_bytes", "dump", "safe_dump"}:
                    continue
                where = f"{path.relative_to(PACKAGE).as_posix()}:{node.lineno}"
                offending.append(f"{where}: {reached}(...)")
    assert not offending, (
        "these write a file, and a feature that writes cannot be asserted to write no "
        "readiness record by reading its source:\n" + "\n".join(offending)
    )


def test_the_readiness_guard_bites(tmp_path: Path) -> None:
    """**Read this before believing the two nodes above** — `T828`'s mutation, both halves.

    Driven against a temporary directory rather than the repository, because **creating a
    readiness record here is exactly what `T828` forbids**: proving a guard by making the
    thing it exists to prevent would be the defect.

    Two records are written, and the second is the half `S-7b` was about: a record naming this
    feature **with** a `feature:` line, and one **without**. The first must be seen as a
    declaration; the second must not be silently dropped.
    """
    global READINESS
    original = READINESS
    try:
        for path in original.glob("*.yaml"):
            (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

        with_a_line = tmp_path / "daily-reporting-external-readiness.yaml"
        with_a_line.write_text(
            "schema_version: 1\nkind: external_readiness_record\n"
            f"feature: {THIS_FEATURE}\ncapabilities: []\n",
            encoding="utf-8",
        )
        READINESS = tmp_path  # pyright: ignore[reportConstantRedefinition] -- the test swaps the tree and restores it
        owners = features_that_own_a_record()
        assert owners.get(with_a_line.name) == THIS_FEATURE
        with pytest.raises(AssertionError, match="declare readiness for"):
            test_this_feature_declares_no_readiness_and_owns_no_record()

        #: The half that used to vanish: no `feature:` line at all.
        with_a_line.unlink()
        without_a_line = tmp_path / "something-external-readiness.yaml"
        without_a_line.write_text(
            f"schema_version: 1\nkind: external_readiness_record\n# {THIS_FEATURE}\n",
            encoding="utf-8",
        )
        owners = features_that_own_a_record()
        assert without_a_line.name in owners, "the record without a feature line was dropped"
        assert owners[without_a_line.name] is None
        with pytest.raises(AssertionError, match="named nowhere"):
            test_every_readiness_record_is_answered_for()
    finally:
        READINESS = original  # pyright: ignore[reportConstantRedefinition] -- the test swaps the tree and restores it

    #: And the tree as it stands must be the clean side of the same comparison.
    assert THIS_FEATURE not in features_that_own_a_record().values()
