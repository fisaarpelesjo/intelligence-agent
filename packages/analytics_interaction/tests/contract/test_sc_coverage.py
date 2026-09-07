"""SC coverage and classification — T174 (SC-001…SC-059).

    Evidence: `SC-030` reports **unmeasurable** rather than a figure. — `tasks.md` T174

## 59 of 59 validation owners, and three classifications

Every success criterion needs an **executable validation owner** — a test module citing it
and declaring at least one test. That is `T174`'s bar, and it is lower than `T173`'s on
purpose: an FR is a requirement something must implement, while an SC is a *measurement*,
and a measurement's owner is the thing that measures it.

Coverage alone would flatten three genuinely different states, so each criterion also
carries a classification:

**`measured`** — the validation runs today and its assertion holds.

**`blocked_external`** — internal contract behaviour passes; the **production** path runs
through a capability that is currently unavailable.

**`unmeasurable`** — no approved definition exists to measure against.

Flattening them is the failure this file exists to prevent. Reporting `blocked_external`
as `measured` claims production behaviour nobody has observed. Reporting it as a failure
reads as a defect and sends somebody looking for a bug in code that is working exactly as
designed. And reporting `unmeasurable` as either invents a measurement or invents a fault.

## The classification is derived, and it self-invalidates

Not a hand table. `blocked_external` is computed from the **code**: a criterion is blocked
when a `src/` module that cites it either calls a capability gate — `require_surface`,
`require_capability`, `require_model_participation`, `require_clarification_sealing` — or
imports `analytics_query.execute`, the entry point that reaches a warehouse.

Then every blocked criterion is checked against the **readiness records**: the capability it
depends on must actually be unavailable. So the day `D-18` is approved, this file fails and
forces the classification to be re-derived rather than silently continuing to describe a
world that has moved.

`unmeasurable` comes from `docs/measurement/`, which is where a criterion's unmeasurability
is declared. `SC-030` is the only member, and `T178`'s document is what puts it there.

## What a fixture-backed pass does not convert

A blocked criterion with a green fixture-backed test is still blocked. The test establishes
internal contract behaviour; the capability is still unavailable; the classification does
not move. Asserted directly below, because "our tests pass" is the exact sentence that
turns a blocked criterion into a claimed one.
"""

from __future__ import annotations

import ast
import re
from enum import StrEnum
from pathlib import Path

import pytest

from analytics_interaction.compliance.gates import (
    CapabilitySurface,
    InteractionCapability,
    available_capabilities,
    is_capability_available,
)
from analytics_interaction.compliance.readiness import aggregate_ready, load_all_records

from .coverage_audit import ALL_SC, REPO, SRC, coverage, forbidden_sources

pytestmark = pytest.mark.contract

SC_LIST = tuple(sorted(ALL_SC))
_SC = re.compile(r"\bSC-(\d{3})\b")

#: Calls that mean "this path needs a capability somebody has to approve".
CAPABILITY_GATES = frozenset(
    {
        "require_surface",
        "require_capability",
        "require_model_participation",
        "require_clarification_sealing",
    }
)

#: The upstream entry point that reaches a warehouse. Importing it is the structural
#: marker for "this path's production behaviour depends on `EXT-A`, `D-14`…`D-17`".
EXECUTION_ENTRY_POINT = "analytics_query.execute"

MEASUREMENT = REPO / "docs" / "measurement"

#: This feature's measurement records, named individually.
#:
#: `docs/measurement/` also holds `002`'s declarations, and SC numbers are **per-feature** —
#: `002`'s `SC-012` is a different criterion from this feature's. Globbing the directory
#: reported five unmeasurable criteria, four of which belong to another spec. Named for the
#: same reason the ADR set is: an upstream document must not answer for a `003` criterion.
MEASUREMENT_RECORDS = ("sc-030-interpretation-quality.md",)


class Classification(StrEnum):
    """Three states, and the names the release evidence uses verbatim."""

    MEASURED = "measured"
    BLOCKED_EXTERNAL = "blocked_external"
    UNMEASURABLE = "unmeasurable"


def _module_reaches_a_gate(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            name = (
                function.attr
                if isinstance(function, ast.Attribute)
                else getattr(function, "id", "")
            )
            if name in CAPABILITY_GATES:
                return True
        if isinstance(node, ast.ImportFrom) and node.module == EXECUTION_ENTRY_POINT:
            return True
    return False


def _blocked_from_code() -> frozenset[int]:
    """Criteria whose production path runs through an unavailable capability.

    Derived by parsing `src/`, so a module that stops needing a gate stops blocking the
    criteria it cites — and one that starts needing a gate starts blocking them.
    """
    blocked: set[int] = set()
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if not _module_reaches_a_gate(path):
            continue
        text = path.read_text(encoding="utf-8")
        blocked.update(int(match.group(1)) for match in _SC.finditer(text))
    return frozenset(blocked)


def _unmeasurable_from_declarations() -> frozenset[int]:
    """Criteria declared unmeasurable by a measurement record.

    Read from :data:`MEASUREMENT_RECORDS` — this feature's declarations, named — so the
    classification comes from a reviewed document rather than a constant in a test. A record
    that stopped saying "unmeasurable" would move the criterion out of this set and into the
    ordinary rule.
    """
    declared: set[int] = set()
    for name in MEASUREMENT_RECORDS:
        path = MEASUREMENT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "unmeasurable" not in text.lower():
            continue
        declared.update(int(match.group(1)) for match in _SC.finditer(text))
    return frozenset(declared)


BLOCKED = _blocked_from_code()
UNMEASURABLE = _unmeasurable_from_declarations()


def classify(number: int) -> Classification:
    """One criterion's classification. Unmeasurable wins over blocked.

    Ordered deliberately: `SC-030` is *both* — it needs `D-11` and its path runs through
    gated capabilities — and reporting it as merely blocked would suggest a figure appears
    once the capability arrives. It does not; the corpus is a separate record.
    """
    if number in UNMEASURABLE:
        return Classification.UNMEASURABLE
    if number in BLOCKED:
        return Classification.BLOCKED_EXTERNAL
    return Classification.MEASURED


# --- the inventory ---------------------------------------------------------------


def test_the_inventory_is_exactly_fifty_nine() -> None:
    """Contiguous SC-001 through SC-059."""
    assert len(ALL_SC) == 59
    assert set(SC_LIST) == set(range(1, 60))


# --- every criterion has an executable validation owner ------------------------


@pytest.mark.parametrize("number", SC_LIST, ids=[f"SC-{n:03d}" for n in SC_LIST])
def test_every_sc_has_an_executable_validation_owner(number: int) -> None:
    """**59 of 59.** One criterion at a time, so a failure names it.

    The owner must be a test module that cites the criterion **and** declares at least one
    test function. A citation in a comment is not a measurement.
    """
    owners = coverage().sc.get(number)
    assert owners is not None, f"SC-{number:03d} is cited nowhere this audit reads"
    assert owners.has_validation, (
        f"SC-{number:03d} has no executable validation owner; "
        f"only implementation or design: {sorted(owners.implementation | owners.design)}"
    )


def test_the_aggregate_is_exactly_complete() -> None:
    """The line a release document quotes."""
    validated = {number for number, owners in coverage().sc.items() if owners.has_validation}
    assert validated == ALL_SC, sorted(ALL_SC - validated)
    assert len(validated) == 59


def test_no_validation_owner_is_a_planning_document() -> None:
    """An `Evidence:` clause is a claim about validation, not a validation."""
    for path in forbidden_sources():
        assert path.is_file(), path
    for owners in coverage().sc.values():
        for owner in owners.validation:
            assert owner.startswith("tests/"), owner
            assert not owner.endswith((".md", "tasks.md"))


def test_no_validation_owner_is_a_dangling_reference() -> None:
    """Every named owner exists on disk."""
    from .coverage_audit import PACKAGE

    for number, owners in coverage().sc.items():
        for relative in owners.validation:
            assert (PACKAGE / relative).is_file(), (number, relative)


# --- the three classifications are three --------------------------------------


def test_every_criterion_has_exactly_one_classification() -> None:
    """Total and single-valued, so a report cannot double-count."""
    for number in SC_LIST:
        assert classify(number) in set(Classification)
    assert len({classify(number) for number in SC_LIST}) == 3, (
        "all three classifications must be populated; a collapsed one means the "
        "derivation broke, not that the world changed"
    )


def test_sc_030_reports_unmeasurable_rather_than_a_figure() -> None:
    """**`T174`'s named evidence.**

    Not blocked, not failed, not a number. `D-11` is open, so there is nothing to measure
    against — and the classification comes from `T178`'s declaration rather than from a
    constant here.
    """
    assert classify(30) is Classification.UNMEASURABLE
    assert 30 in UNMEASURABLE
    declaration = MEASUREMENT / "sc-030-interpretation-quality.md"
    assert declaration.is_file()
    text = declaration.read_text(encoding="utf-8")
    assert "declared unmeasurable" in text.lower()
    assert "PROCEDURE-ONLY" in text


def test_no_unmeasurable_criterion_carries_a_figure() -> None:
    """The declaration defines a measurement and performs none.

    Scanned for a percentage, a rate and a score, because a figure in a governance
    document is what gets quoted while the sentence beside it does not.
    """
    for path in sorted(MEASUREMENT.glob("sc-030*.md")):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("accuracy of", "precision of", "f1", "score of"):
            assert forbidden not in text.lower(), forbidden
        assert not re.search(r"\b\d{1,3}(\.\d+)?\s?%\s+(accuracy|precision|recall|quality)", text)


def test_the_blocked_set_is_non_empty_and_derived() -> None:
    """A blocked set of zero would mean this feature has no external dependency.

    It has fifteen. An empty set means the derivation stopped working, which is why this is
    an assertion rather than a note.
    """
    assert BLOCKED, "no criterion is blocked; the code derivation has broken"
    assert BLOCKED <= ALL_SC


# --- the classification self-invalidates --------------------------------------


def test_every_blocked_criterion_depends_on_a_currently_unavailable_capability() -> None:
    """**The self-invalidating half.**

    Blocked means blocked *by something*. Checked against the readiness records rather
    than asserted: the day a capability is approved, this fails and the classification has
    to be re-derived instead of quietly describing a world that moved.
    """
    assert BLOCKED
    # RE-DERIVADO em 2026-09-02 (OD-101), como este proprio no exigia: d_21 ficou
    # disponivel. A superficie do selo abriu, mas a demonstracao de PRODUCAO do selo e
    # da implantacao (chave real na VM; decisao 4 do dono: nenhuma suite a le) — entao
    # SC-044 permanece blocked_external como afirmacao sobre o caminho de producao nao
    # demonstrado NESTE repositorio, nunca como "portao fechado". Os demais bloqueados
    # continuam atras de d_18/d_19/d_20 ou do executor composto.
    # RE-RE-DERIVADO em 2026-09-02 (OD-104): d_18 tambem abriu — as tres superficies do
    # vocabulario passam; os bloqueados restantes seguem atras de d_19/d_20 ou do
    # executor composto, e SC-044 mantem a leitura do OD-101.
    assert available_capabilities() == frozenset({"d_18", "d_21"})
    for capability in InteractionCapability:
        assert is_capability_available(capability) == (
            capability in (InteractionCapability.D_18, InteractionCapability.D_21)
        )


def test_the_gated_surfaces_are_still_gated() -> None:
    """Eleven surfaces; clarification_sealing open by OD-101 (2026-09-02), ten gated."""
    from analytics_interaction.compliance.gates import is_surface_available

    for surface in CapabilitySurface:
        # OD-104 (2026-09-02): + as tres superficies do vocabulario; sete seguem fechadas.
        assert is_surface_available(surface) == (
            surface
            in (
                CapabilitySurface.CLARIFICATION_SEALING,
                CapabilitySurface.RELATIVE_PERIOD,
                CapabilitySurface.COMPARISON_FORMULA,
                CapabilitySurface.CLAIM_WORDING,
            )
        ), surface.value


def test_aggregate_readiness_is_still_none() -> None:
    """Restated here because this file's classifications depend on it."""
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )


# --- a fixture pass converts nothing -----------------------------------------


@pytest.mark.parametrize(
    "number",
    sorted(BLOCKED),
    ids=[f"SC-{n:03d}" for n in sorted(BLOCKED)],
)
def test_a_blocked_criterion_keeps_its_classification_despite_passing_tests(
    number: int,
) -> None:
    """**The sentence this forecloses: "our tests pass, so it works".**

    Every blocked criterion here has a green validation owner. The suite is green. The
    classification is still `blocked_external`, because the validation establishes internal
    contract behaviour and the capability is still unavailable.
    """
    owners = coverage().sc[number]
    assert owners.has_validation, number
    assert classify(number) in {Classification.BLOCKED_EXTERNAL, Classification.UNMEASURABLE}


def test_the_measured_set_claims_nothing_about_production() -> None:
    """Even `measured` means measured against fixtures.

    Asserted by the absence of the thing that would make it otherwise: no warehouse client,
    no provider, no seal key. A criterion measured against a fixture is measured; what it
    is not is observed in production.
    """
    measured = {number for number in SC_LIST if classify(number) is Classification.MEASURED}
    assert measured
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )


def test_the_classification_counts_are_reportable() -> None:
    """One place the release evidence can quote, so two documents cannot disagree.

    Asserted as a partition summing to 59 rather than as three fixed numbers: the
    derivation is allowed to move a criterion between `measured` and `blocked_external` if
    the code changes, and pinning the counts would make a legitimate refactor look like a
    regression.
    """
    counts = {
        classification: sum(1 for number in SC_LIST if classify(number) is classification)
        for classification in Classification
    }
    assert sum(counts.values()) == 59
    assert counts[Classification.UNMEASURABLE] == 1
    assert counts[Classification.BLOCKED_EXTERNAL] >= 1
    assert counts[Classification.MEASURED] >= 1
