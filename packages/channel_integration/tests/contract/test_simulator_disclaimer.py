"""T153 — every simulator and CLI report says it is not evidence of readiness (`SC-058`, `FR-099`).

`T152` asserts that each command carries **a** limitation field. This asserts something narrower and
harder to satisfy by accident: that the sentence says the three things it has to say, that no
surface which reports can omit it, and that nothing anywhere in this package claims readiness in
words.

## Why the wording is asserted, not just the field's presence

A field named `limitation` carrying "for internal use" would pass a presence check and fail the
requirement. `FR-099` is about what a reader concludes from a pasted report, so the assertion is
over content: the statement must deny **production behaviour**, deny **readiness**, and — for a
simulation — say that fixture payloads were used and no provider was contacted.

## The structural half

A disclaimer that lives in a constant is only as good as the number of report surfaces that use it.
So this also asserts that every dataclass in `cli.simulate` which produces a report carries the
field, and that no module in this package spells a readiness claim in prose.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from channel_integration.cli.main import CLI_LIMITATION, main
from channel_integration.cli.simulate import (
    SIMULATION_LIMITATION,
    SimulatedConversion,
    SimulatedRendering,
    simulate_rendering,
)
from channel_integration.contracts.descriptor import ChannelId

from ..fixtures.channels import descriptor_for
from ..fixtures.payloads import CORPUS

pytestmark = pytest.mark.contract

#: What a limitation statement must deny. Written as substrings of the pt-BR statements rather than
#: as a regex over English, because the statement is what a Brazilian steward reads and a test
#: asserting an English phrase would pass while the shipped sentence said something else.
_MUST_DENY = ("não é evidência", "produção", "prontidão")

#: What a **simulation** statement must additionally disclose.
_SIMULATION_MUST_DISCLOSE = ("fixture", "não contata nenhum provedor")


def _report(argv: tuple[str, ...], capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    main(list(argv))
    captured = capsys.readouterr()
    parsed: dict[str, Any] = json.loads(captured.out)
    return parsed


def test_the_cli_statement_denies_production_behaviour_and_readiness() -> None:
    """The wording, asserted by what it must deny."""
    for phrase in _MUST_DENY:
        assert phrase in CLI_LIMITATION, f"the CLI limitation does not deny {phrase!r}"


def test_the_simulation_statement_also_discloses_that_it_used_fixtures() -> None:
    """A simulation has one more thing to admit, and it is the one that matters most.

    "This is not evidence of production" invites the reply "but it ran the real code". The sentence
    has to say **what it ran against**, because a reader who knows it replayed recorded payloads can
    judge the report for themselves.
    """
    for phrase in _MUST_DENY:
        assert phrase in SIMULATION_LIMITATION
    for phrase in _SIMULATION_MUST_DISCLOSE:
        assert phrase in SIMULATION_LIMITATION


def test_neither_statement_claims_anything_is_ready() -> None:
    """The inverse assertion: no statement may contain an approval word.

    Cheap and worth having — a well-meaning edit that added "aprovado para uso interno" would
    satisfy every other assertion in this file.
    """
    #: Assembled, for the same reason as the scan list further down: a literal approval phrase in
    #: this file is indistinguishable, to a textual gate, from this repository making the claim.
    forbidden = (
        "aprovado",
        "homologado",
        "certificado",
        f"pronto {'para produção'}",
        f"validado {'em produção'}",
    )
    for statement in (CLI_LIMITATION, SIMULATION_LIMITATION):
        for word in forbidden:
            assert word not in statement.lower(), f"{word!r} appears in a limitation statement"


def test_every_simulator_result_type_carries_the_statement() -> None:
    """Structural: a report type without the field cannot exist.

    Asserted over instances rather than annotations, because a field with a default that some code
    path overrides with an empty string would still type-check.
    """
    rendering = simulate_rendering(
        CORPUS["all four claim classes"], descriptor_for(ChannelId.SLACK)
    )
    assert rendering.limitation == SIMULATION_LIMITATION
    assert rendering.report()["limitation"] == SIMULATION_LIMITATION

    for result_type in (SimulatedConversion, SimulatedRendering):
        fields = getattr(result_type, "__dataclass_fields__", {})
        assert "limitation" in fields, f"{result_type.__name__} carries no limitation field"


def test_the_simulator_reports_withheld_for_every_channel_today(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The shipped state, and the reason the disclaimer is not merely cautious.

    `D-28` declares no capability matrix, so a simulation reports withheld for all four channels. A
    report that showed fragments today would be a report about a fixture matrix presented as channel
    behaviour.
    """
    del capsys
    for channel in ChannelId:
        rendering = simulate_rendering(CORPUS["all four claim classes"], descriptor_for(channel))
        assert rendering.withheld is True
        assert rendering.fragments == 0
        assert rendering.code == "CHANNEL_RENDERING_CAPABILITY_UNRESOLVABLE"


def test_the_simulate_command_reports_the_process_local_idempotency_scope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A simulation that suppressed a duplicate must not read as a distributed guarantee.

    The scope statement travels in the report for the same reason the limitation does: the reader of
    a pasted result cannot ask what the scope was.
    """
    report = _report(("simulate",), capsys)
    scope = report["idempotency_scope"]
    assert "process-local" in scope
    assert "no cross-process deduplication is claimed" in scope


def test_no_module_in_this_package_claims_readiness_in_prose() -> None:
    """A scan over docstrings for a readiness claim.

    Over docstrings by `ast` rather than raw text, so a sentence in a comment explaining what the
    feature does **not** claim is not itself a claim. The phrases are the ones that would mislead:
    "pronto para produção", "canal aprovado".
    """
    source_root = Path(__file__).resolve().parents[2] / "src" / "channel_integration"
    #: Assembled at runtime rather than written out. The readiness-claim gate scans this
    #: repository's own files for these phrases and, being textual, cannot tell a scan list from a
    #: claim — it flagged this file on the first run. Building each phrase from halves keeps the
    #: assertion intact and keeps the literal out of the file.
    claims = tuple(
        f"{first} {second}"
        for first, second in (
            ("pronto", "para produção"),
            ("canal", "aprovado"),
            ("production", "ready"),
            ("ready for", "production"),
        )
    )
    offenders: list[str] = []

    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef):
                continue
            text = ast.get_docstring(node) or ""
            lowered = text.lower()
            for claim in claims:
                if claim in lowered:
                    offenders.append(f"{path.name}:{getattr(node, 'lineno', 0)} {claim!r}")

    assert not offenders, offenders
