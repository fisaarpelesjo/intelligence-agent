"""Upstream conditions surface verbatim — T161 (FR-020, FR-021, FR-059; SC-015).

    An upstream refusal MUST be surfaced with its own code and wording. This
    feature MUST NOT translate it, re-word it, or substitute a code of its own.
    Retention questions remain unanswerable while `D-8` and `D-9` are absent.
    — `FR-020`, `FR-021`, `FR-059`

    Evidence: each upstream condition surfaces its own code verbatim; retention
    stays unanswerable. — `tasks.md` T161

## Why translation is the failure and not a convenience

There are thirty-two reason codes in this feature and none of them means "the source
is stale". That is deliberate, and it is the whole design: staleness is `001`'s
judgement about governed freshness evidence, suppression is `002`'s judgement about a
minimum-aggregation threshold, and retention maturity is `001`'s judgement about a
cohort definition nobody has approved yet.

Inventing a local code for any of them would mean this layer *asserting* an upstream
fact. The next reader would look for the freshness rule in this package and not find
one, and the caller would be told the interaction layer refused when the catalog did
— sending them to the wrong owner with the wrong question.

So the assertion is not "a refusal happens" but **"the upstream code and the upstream
sentence arrive unaltered"**, and separately that **no local code exists** that could
be substituted for them.

## The four conditions

| Condition | Owner | Governed by |
|---|---|---|
| stale or lagging source | `001` freshness gate | `D-1` |
| suppressed cell | `002` minimum aggregation | `D-16` |
| retention not matured | `001` retention contract | `D-8`, `D-9` |
| withdrawn release | `001` release gate | catalog release state |

Each is a different owner and a different open record, which is exactly why they
must stay distinguishable.
"""

from __future__ import annotations

import unicodedata

import pytest
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_interaction.answer.refusal import GovernedRefusal, refuse_upstream
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code

pytestmark = pytest.mark.adversarial

#: The upstream conditions this feature surfaces rather than judges.
#:
#: The wording is the **upstream sentence**, in pt-BR, with the awkward parts left
#: in: a trailing space, a doubled space, an accent in decomposed form. Each is
#: something a well-meaning normaliser would tidy, and tidying it is the violation.
UPSTREAM: tuple[tuple[str, object, str], ...] = (
    (
        "stale-source",
        ReasonCode.SOURCE_BEYOND_TOLERANCE,
        "a fonte appstore está além da tolerância de atraso aprovada",
    ),
    (
        "lagging-within-tolerance",
        ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE,
        "a fonte playstore está atrasada, dentro da tolerância ",
    ),
    (
        "source-state-unknown",
        ReasonCode.SOURCE_STATE_UNKNOWN,
        "o estado  de publicação da fonte é desconhecido",
    ),
    (
        "coverage-ends-early",
        ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD,
        unicodedata.normalize("NFD", "a cobertura observada termina antes do período pedido"),
    ),
    (
        "retention-not-matured",
        ReasonCode.COHORT_NOT_MATURED,
        "a coorte não atingiu a maturação necessária",
    ),
    (
        "retention-source-unavailable",
        ReasonCode.RETENTION_SOURCE_UNAVAILABLE,
        "a fonte de retenção não está disponível",
    ),
    (
        "retention-not-summable",
        ReasonCode.RETENTION_NOT_SUMMABLE,
        "retenção não é somável entre coortes",
    ),
    (
        "release-withdrawn",
        ReasonCode.RELEASE_WITHDRAWN,
        "a versão do catálogo foi retirada",
    ),
    (
        "access-denied",
        ReasonCode.ACCESS_DENIED,
        "acesso negado pela tag governada",
    ),
    (
        "definition-change",
        ReasonCode.SPANS_DEFINITION_CHANGE,
        "o período atravessa uma mudança de definição",
    ),
)

#: `002`'s codes, which arrive through the execution boundary rather than the
#: catalog. Kept separate because they have a different owner and a different open
#: record, and a test that merged them would stop noticing if one namespace started
#: answering for the other.
EXECUTION_UPSTREAM: tuple[tuple[str, object, str], ...] = tuple(
    (code.value.lower().replace("_", "-"), code, f"condição de execução: {code.value}")
    for code in list(AnalyticsReasonCode)[:6]
)

CATALOG_IDS = [name for name, _, _ in UPSTREAM]
EXECUTION_IDS = [name for name, _, _ in EXECUTION_UPSTREAM]

#: Retention conditions, named separately because `FR-059` makes a stronger claim
#: about them than about the rest: they are not merely refused today, they are
#: **unanswerable** while `D-8` and `D-9` are absent.
RETENTION = tuple(
    entry for entry in UPSTREAM if "retention" in entry[0] or entry[0] == "retention-not-matured"
)


# --- the corpus covers each owner ------------------------------------------------


def test_the_corpus_covers_both_upstream_namespaces() -> None:
    """Ten catalog conditions and six execution ones, from two enums.

    Drawn from the real upstream enums rather than from strings, so a code renamed
    upstream breaks this import rather than silently testing a string nobody raises.
    """
    assert len(UPSTREAM) == 10
    assert len(EXECUTION_UPSTREAM) == 6
    assert all(isinstance(code, ReasonCode) for _, code, _ in UPSTREAM)
    assert all(isinstance(code, AnalyticsReasonCode) for _, code, _ in EXECUTION_UPSTREAM)
    assert len(RETENTION) == 3


def test_no_local_code_means_any_upstream_condition() -> None:
    """**The load-bearing absence.**

    Thirty-two codes and none of them says "stale", "suppressed", "retention" or
    "withdrawn". Asserted as a scan over the enum, so a code added later that
    *would* let this layer assert an upstream fact fails here.
    """
    local = {code.value for code in Code}
    for forbidden in (
        "STALE",
        "SUPPRESS",
        "RETENTION",
        "COHORT",
        "WITHDRAWN",
        "FRESHNESS",
        "TOLERANCE",
        "COVERAGE",
        "AGGREGATION",
    ):
        offenders = sorted(name for name in local if forbidden in name)
        assert not offenders, f"a local code asserts an upstream fact: {offenders}"


def test_the_two_upstream_namespaces_stay_disjoint_from_the_local_one() -> None:
    """Three namespaces, no shared values.

    A shared value would make ``upstream_code`` ambiguous: a consumer could not tell
    whether the string came from `001`, `002` or here, which is the attribution this
    whole file is about.
    """
    local = {code.value for code in Code}
    catalog = {code.value for code in ReasonCode}
    execution = {code.value for code in AnalyticsReasonCode}
    assert not local & catalog
    assert not local & execution
    assert not catalog & execution


# --- the code and the sentence arrive unaltered ---------------------------------


@pytest.mark.parametrize("entry", UPSTREAM, ids=CATALOG_IDS)
def test_a_catalog_condition_surfaces_its_own_code(entry: tuple[str, object, str]) -> None:
    """**The load-bearing assertion.** Stringified, never mapped.

    ``upstream_code`` holds the upstream enum's own value. A translation table here
    would tell the caller the interaction layer refused when the catalog did.
    """
    _, code, message = entry
    refusal = refuse_upstream(code, message)  # pyright: ignore[reportArgumentType]
    assert refusal.upstream_code == str(code)
    assert refusal.code is None, "no local code is substituted"
    assert refusal.message is None, "no local wording speaks alongside it"


@pytest.mark.parametrize("entry", UPSTREAM, ids=CATALOG_IDS)
def test_the_upstream_sentence_survives_byte_for_byte(entry: tuple[str, object, str]) -> None:
    """No trim, no whitespace collapse, no recomposition, no translation.

    Compared as bytes, so an NFC/NFD change — invisible in a diff — is caught. The
    corpus deliberately includes a trailing space, a doubled space and a decomposed
    accent for exactly this.
    """
    _, code, message = entry
    refusal = refuse_upstream(code, message)  # pyright: ignore[reportArgumentType]
    assert refusal.upstream_message == message
    assert refusal.upstream_message is not None
    assert refusal.upstream_message.encode() == message.encode()


@pytest.mark.parametrize("entry", EXECUTION_UPSTREAM, ids=EXECUTION_IDS)
def test_an_execution_condition_surfaces_its_own_code(entry: tuple[str, object, str]) -> None:
    """`002`'s namespace, carried the same way and kept distinguishable from `001`'s."""
    _, code, message = entry
    refusal = refuse_upstream(code, message)  # pyright: ignore[reportArgumentType]
    assert refusal.upstream_code == str(code)
    assert refusal.upstream_message == message
    assert refusal.code is None


@pytest.mark.parametrize("entry", UPSTREAM + EXECUTION_UPSTREAM, ids=CATALOG_IDS + EXECUTION_IDS)
def test_the_refusal_carries_no_local_wording_beside_it(
    entry: tuple[str, object, str],
) -> None:
    """One origin speaks. Both speaking is unconstructible, and this is the path proof.

    The contract forbids the shape; this asserts that the *function* a caller
    actually uses produces the permitted half of it, so no code path assembles the
    forbidden one by accident.
    """
    _, code, message = entry
    refusal = refuse_upstream(code, message)  # pyright: ignore[reportArgumentType]
    assert (refusal.code is None) and (refusal.message is None)
    assert refusal.upstream_code is not None and refusal.upstream_message is not None


@pytest.mark.parametrize("entry", UPSTREAM, ids=CATALOG_IDS)
def test_repeating_the_passthrough_is_deterministic(entry: tuple[str, object, str]) -> None:
    """Same condition in, same serialised refusal out. Five times."""
    _, code, message = entry
    serialised = {
        refuse_upstream(code, message).model_dump_json()  # pyright: ignore[reportArgumentType]
        for _ in range(5)
    }
    assert len(serialised) == 1


# --- an upstream refusal with no wording is refused, never papered over --------


@pytest.mark.parametrize("entry", UPSTREAM, ids=CATALOG_IDS)
def test_a_wordless_upstream_refusal_is_refused(entry: tuple[str, object, str]) -> None:
    """Substituting local wording would be the restatement this exists to prevent.

    A caller receiving a code with no sentence cannot read the refusal; a caller
    receiving a code with *this layer's* sentence has been told something the
    catalog did not say. The first is a bug to fix upstream, the second is a
    misattribution that would look correct forever.
    """
    _, code, _ = entry
    for blank in ("", " ", "\t", "\n", "   \n  "):
        with pytest.raises(ContractViolation) as raised:
            refuse_upstream(code, blank)  # pyright: ignore[reportArgumentType]
        assert raised.value.code is Code.INTAKE_MALFORMED


# --- retention is unanswerable, not merely refused -----------------------------


@pytest.mark.parametrize("entry", RETENTION, ids=[name for name, _, _ in RETENTION])
def test_a_retention_condition_surfaces_upstream_and_nothing_local(
    entry: tuple[str, object, str],
) -> None:
    """`FR-059`'s stronger claim.

    `D-8` and `D-9` are undeclared, so no retention question has an approved
    definition to be answered against. This feature does not implement a fallback,
    an approximation or a partial answer — it carries the upstream verdict and adds
    nothing.
    """
    _, code, message = entry
    refusal = refuse_upstream(code, message)  # pyright: ignore[reportArgumentType]
    assert refusal.upstream_code == str(code)
    assert refusal.upstream_message == message
    assert refusal.code is None
    assert refusal.alternative is None, (
        "a narrower alternative would suggest a retention question that could be "
        "answered; none can be, while D-8 and D-9 are absent"
    )


def test_no_module_implements_a_retention_definition() -> None:
    """The absence, asserted where somebody would add it.

    A cohort identity rule, an eligible-event rule or a maturation window authored
    here would be this feature inventing `D-8` and `D-9` content — and a green
    retention test would then read as approval.
    """
    import ast
    import inspect
    from pathlib import Path

    import analytics_interaction

    src = Path(inspect.getfile(analytics_interaction)).resolve().parent
    forbidden = (
        "cohort_identity",
        "eligible_event",
        "maturation_window",
        "retention_window",
        "cohort_timezone",
        "retention_day",
    )
    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.name
                if isinstance(node, ast.FunctionDef | ast.ClassDef)
                else ""
            )
            if name and any(banned in name.lower() for banned in forbidden):
                offenders.append(f"{path.relative_to(src).as_posix()}: {name}")
    assert not offenders, f"a retention definition is authored here: {offenders}"


# --- the passthrough is not a wildcard ----------------------------------------


def test_an_unknown_upstream_code_still_carries_verbatim() -> None:
    """A code this build does not know is still surfaced, not swallowed.

    The tempting alternative — refuse with a local "unknown upstream code" — would
    replace a governed sentence the caller can act on with one that says the
    interaction layer was confused. Upstream namespaces evolve; this layer carries
    what it is given.
    """
    refusal = refuse_upstream(
        "A_CODE_FROM_A_LATER_RELEASE",  # pyright: ignore[reportArgumentType]
        "uma condição que este build não conhece",
    )
    assert refusal.upstream_code == "A_CODE_FROM_A_LATER_RELEASE"
    assert refusal.upstream_message == "uma condição que este build não conhece"
    assert refusal.code is None


def test_the_passthrough_returns_the_governed_contract() -> None:
    """A ``GovernedRefusal``, so every validator on it ran.

    Not a dict, not a tuple, not a string — which matters because the "exactly one
    origin speaks" rule lives on the contract, and a passthrough returning something
    looser would bypass it.
    """
    refusal = refuse_upstream(ReasonCode.ACCESS_DENIED, "acesso negado")
    assert isinstance(refusal, GovernedRefusal)
