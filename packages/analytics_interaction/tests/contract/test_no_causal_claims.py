"""No causal claims — T131 (FR-036; SC-010).

    Evidence: correlation, association and hypothesis wording carries the
    causality warning. — `tasks.md` T131

This feature answers "what happened", not "why". The distinction matters because
a causal sentence beside a correct number is more dangerous than a wrong number:
the figure lends the explanation authority it did not earn, and nobody rereads a
number they already believe.

## Two halves, and both are needed

**Structural** — no claim class can express causation. The four are
`FACTUAL_RESULT`, `CALCULATED_COMPARISON`, `INTERPRETATION` and `LIMITATION`, and
none of them means "because". A fifth would be a contract change, not a content
change, so a governed-content edit cannot introduce one.

**Content** — the governed wording itself is scanned. `D-18`'s claim-class
wording and the pt-BR message registry are authored files, and an authored
sentence saying *"as instalações caíram por causa da campanha"* would slip past
every type in the system. So the denylist runs over the content, not over the
code.

## The three the requirement names

`FR-036` names correlation, association and hypothesis specifically — the three
that look descriptive and read as causal. "X está correlacionado com Y" is a
statistical statement in the writer's head and a causal one in the reader's, and
the requirement is that such wording carries the causality warning rather than
being banned outright: the catalog may legitimately publish a correlation
limitation.

So the rule is conditional. Wording that uses one of the three **must** also
carry the warning marker; wording that asserts causation outright is refused
whatever it carries.

## The shipped state

Both governed files ship empty, so the scan passes vacuously today. The
planted-content cases below are what make it non-vacuous: each is run through the
same detector, and each fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from analytics_interaction.contracts.answer import ClaimClass
from analytics_interaction.governance.schemas import governed_content_root

pytestmark = pytest.mark.contract

#: Wording that asserts causation outright. Refused whatever else it carries —
#: there is no marker that makes "porque" acceptable in a governed claim.
CAUSAL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("por causa de", r"\bpor causa d[eoa]s?\b"),
    ("porque", r"\bporque\b"),
    # ``à``/``às`` as well as ``a``: the crased contraction is the commoner
    # spelling, and a pattern that missed it would pass the sentence it was
    # written to catch.
    ("devido a", r"\bdevid[oa]s? (?:a|à|ao|aos|às)\b"),
    ("causou", r"\bcaus(?:ou|aram|a|am)\b"),
    ("resultou em", r"\bresultou em\b"),
    ("levou a", r"\blevou a\b"),
    ("provocou", r"\bprovoc(?:ou|aram)\b"),
    ("explica", r"\bexplica(?:m|do|da)?\b"),
    ("impacto de", r"\bimpacto d[eoa]s?\b"),
)

#: The three `FR-036` names. Permitted **only** alongside the warning marker.
CONDITIONAL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("correlação", r"\bcorrelaç(?:ão|ões)\b|\bcorrelacionad[oa]s?\b"),
    ("associação", r"\bassociaç(?:ão|ões)\b|\bassociad[oa]s?\b"),
    ("hipótese", r"\bhipótese(?:s)?\b"),
)

#: The marker governed wording must carry beside conditional language. A code
#: rather than a sentence: the warning's own text is `D-18` content, and naming a
#: sentence here would be authoring it.
CAUSALITY_WARNING = "NAO_IMPLICA_CAUSALIDADE"


def _causal_violations(text: str) -> list[str]:
    """Outright causal assertions, and unwarned conditional wording."""
    lowered = text.lower()
    found = [name for name, pattern in CAUSAL_PATTERNS if re.search(pattern, lowered)]

    warned = CAUSALITY_WARNING.lower() in lowered
    if not warned:
        found += [
            f"{name} (unwarned)"
            for name, pattern in CONDITIONAL_PATTERNS
            if re.search(pattern, lowered)
        ]
    return found


def _governed_files() -> list[Path]:
    root = governed_content_root()
    return sorted(path for path in root.rglob("*.yaml") if path.is_file())


# --- structural: no class can express causation -------------------------------------


def test_no_claim_class_means_because() -> None:
    """Four classes, and none of them is causal.

    A fifth would be a contract change, not a content change — so a
    governed-content edit cannot introduce one.
    """
    assert {c.value for c in ClaimClass} == {
        "FACTUAL_RESULT",
        "CALCULATED_COMPARISON",
        "INTERPRETATION",
        "LIMITATION",
    }
    for claim_class in ClaimClass:
        assert "CAUS" not in claim_class.value
        assert "REASON" not in claim_class.value
        assert "EXPLAIN" not in claim_class.value


def test_an_interpretation_carries_no_number_so_it_cannot_read_as_a_finding() -> None:
    """The class most likely to acquire an explanation carries no figure."""
    from analytics_interaction.contracts.answer import NUMERIC_CLAIM_CLASSES

    assert ClaimClass.INTERPRETATION not in NUMERIC_CLAIM_CLASSES
    assert ClaimClass.LIMITATION not in NUMERIC_CLAIM_CLASSES


# --- content: the governed wording is scanned ----------------------------------------


def test_the_governed_content_files_are_present() -> None:
    """Otherwise the scan below passes because it read nothing."""
    files = _governed_files()
    assert files, "no governed content files were found to scan"
    names = {path.name for path in files}
    assert "claim-classes.yaml" in names
    assert "comparison-formulas.yaml" in names


@pytest.mark.parametrize("path", _governed_files(), ids=lambda p: p.name)
def test_no_governed_wording_asserts_causation(path: Path) -> None:
    """The denylist over authored content, file by file.

    Empty today, which is why the planted cases below matter: an assertion that
    only ever runs over nothing is an assertion nobody has tested.
    """
    offenders = _causal_violations(path.read_text(encoding="utf-8"))
    assert not offenders, f"{path.name} carries causal wording: {offenders}"


def test_the_message_registry_asserts_no_causation() -> None:
    """The pt-BR refusal wording, which a user reads directly."""
    registry = governed_content_root() / "messages"
    if not registry.is_dir():
        pytest.skip("no message registry is authored yet")
    for path in sorted(registry.rglob("*.yaml")):
        offenders = _causal_violations(path.read_text(encoding="utf-8"))
        assert not offenders, f"{path.name} carries causal wording: {offenders}"


# --- the detector fires ----------------------------------------------------------------


@pytest.mark.parametrize(
    "planted",
    [
        pytest.param("as instalações caíram por causa da campanha", id="por-causa-de"),
        pytest.param("o número subiu porque a campanha começou", id="porque"),
        pytest.param("a queda ocorreu devido à falha da fonte", id="devido-a"),
        pytest.param("a campanha causou um aumento de instalações", id="causou"),
        pytest.param("a mudança resultou em mais sessões", id="resultou-em"),
        pytest.param("o lançamento levou a mais downloads", id="levou-a"),
        pytest.param("isto explica a variação observada", id="explica"),
        pytest.param("o impacto da campanha foi positivo", id="impacto-de"),
    ],
)
def test_the_detector_catches_planted_causal_wording(planted: str) -> None:
    """Each reads as an explanation of a number rather than a statement of one."""
    assert _causal_violations(planted), "causal wording was not detected"


@pytest.mark.parametrize(
    "conditional",
    [
        "as duas séries estão correlacionadas",
        "há uma associação entre as métricas",
        "esta é uma hipótese sobre a variação",
    ],
)
def test_conditional_wording_without_the_warning_is_caught(conditional: str) -> None:
    """`FR-036`'s three. Statistical to the writer, causal to the reader."""
    assert _causal_violations(conditional)


@pytest.mark.parametrize(
    "conditional",
    [
        "as duas séries estão correlacionadas (NAO_IMPLICA_CAUSALIDADE)",
        "há uma associação entre as métricas — NAO_IMPLICA_CAUSALIDADE",
        "esta é uma hipótese sobre a variação. NAO_IMPLICA_CAUSALIDADE",
    ],
)
def test_conditional_wording_with_the_warning_is_permitted(conditional: str) -> None:
    """The rule is conditional, not a ban.

    The catalog may legitimately publish a correlation limitation; what it may
    not do is publish one that reads as a cause.
    """
    assert not _causal_violations(conditional)


def test_the_warning_marker_does_not_excuse_outright_causation() -> None:
    """No marker makes "porque" acceptable in a governed claim."""
    assert _causal_violations("subiu porque a campanha começou (NAO_IMPLICA_CAUSALIDADE)")


@pytest.mark.parametrize(
    "innocent",
    [
        "o total de instalações no período",
        "a janela comparável foi reduzida para acompanhar as fontes",
        "a fonte está atrasada dentro da tolerância governada",
        "diferença absoluta entre os dois períodos",
    ],
)
def test_the_detector_does_not_fire_on_descriptive_wording(innocent: str) -> None:
    """Descriptions of what happened, which is the whole permitted vocabulary."""
    assert not _causal_violations(innocent)
