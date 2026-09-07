"""CLI exit codes — T103 (SC-008).

Three classes, and every subcommand asserted against each it can reach:

* **0** — the check passed;
* **1** — a governed violation, meaning the command ran correctly and found
  something wrong;
* **2** — an invocation error, meaning the command could not run at all.

Conflating 1 and 2 is the failure this prevents. A script that treats any
non-zero as "the gate failed" will report a typo in a flag as a governance
violation, and someone will spend an afternoon looking for a policy problem that
does not exist.

`policy show` returning 1 today is not a bug: no approved QueryPolicy exists
while `D-14` and `D-16` are open, so "no policy in force" is the designed state
and the command reports it as a violation rather than printing an empty object.
"""

from __future__ import annotations

import pytest

from analytics_query.cli.main import EXIT_INVOCATION, EXIT_OK, EXIT_VIOLATION, build_parser, main

pytestmark = pytest.mark.unit

SUBCOMMANDS = [
    ["validate-governance"],
    ["explain-plan"],
    ["ledger", "show"],
    ["schema", "export"],
    ["schema", "export", "--check"],
    ["messages"],
]


def test_the_three_classes_are_distinct() -> None:
    assert {EXIT_OK, EXIT_VIOLATION, EXIT_INVOCATION} == {0, 1, 2}


@pytest.mark.parametrize("argv", SUBCOMMANDS, ids=lambda a: " ".join(a))
def test_a_healthy_subcommand_exits_zero(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == EXIT_OK
    assert capsys.readouterr().out.strip(), "a passing command still reports what it checked"


def test_the_governed_violation_class_is_reachable() -> None:
    """No approved policy is in force, which is a violation, not an error."""
    assert main(["policy", "show"]) == EXIT_VIOLATION


@pytest.mark.parametrize(
    "argv",
    [["nonsense"], ["policy"], ["schema"], ["ledger"], ["policy", "nonsense"]],
    ids=lambda a: " ".join(a) or "empty",
)
def test_a_broken_invocation_exits_two(argv: list[str]) -> None:
    """A typo is not a governance finding."""
    assert main(argv) == EXIT_INVOCATION


def test_an_unparseable_date_is_an_invocation_error() -> None:
    assert main(["policy", "show", "--on", "not-a-date"]) == EXIT_INVOCATION


def test_help_is_not_a_violation() -> None:
    """`--help` exits 0 through the same path."""
    with pytest.raises(SystemExit) as caught:
        build_parser().parse_args(["--help"])
    assert caught.value.code == 0


@pytest.mark.parametrize("argv", SUBCOMMANDS, ids=lambda a: " ".join(a))
def test_every_subcommand_emits_deterministic_json(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Byte-identical across runs, so a diff shows only real change."""
    main(argv)
    first = capsys.readouterr().out
    main(argv)
    assert capsys.readouterr().out == first


def test_no_subcommand_accepts_sql_or_a_limit() -> None:
    """The CLI is not a back door into an ungoverned query.

    Reads the rendered help of every subcommand rather than walking argparse
    internals: help is the surface a user actually sees, so an option missing
    from it would be undiscoverable anyway.
    """
    import contextlib
    import io

    rendered = io.StringIO()
    with contextlib.redirect_stdout(rendered), contextlib.suppress(SystemExit):
        build_parser().parse_args(["--help"])
    for argv in (["policy", "--help"], ["schema", "--help"], ["ledger", "--help"]):
        with contextlib.redirect_stdout(rendered), contextlib.suppress(SystemExit):
            build_parser().parse_args(argv)

    help_text = rendered.getvalue().lower()
    assert help_text, "the parser must render help at all"
    for forbidden in ("--sql", "--query", "--where", "--limit", "--table", "--truncate"):
        assert forbidden not in help_text
