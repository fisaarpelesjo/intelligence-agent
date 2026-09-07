"""Refusal semantics — T134 (FR-022, FR-024, FR-046; SC-015, SC-016).

    Evidence: a restated upstream message fails the byte comparison.
    — `tasks.md` T134

Four claims:

* **exactly one governed code per refusal.** Not a list, not a
  primary-plus-details. A refusal naming two reasons invites the reader to fix
  one and retry, and the second was equally disqualifying;
* **upstream code and message pass through byte-identical**, with no restatement.
  Re-wording a governed sentence produces one nobody approved, and re-coding it
  tells the caller the interaction layer refused when the catalog did;
* **governed-state wording names no error, exception or trace.** `FR-046`: a
  governed refusal is a governed state, and leaking a stack trace turns a
  policy decision into a bug report;
* **a narrower alternative is disclosure only.** Never submitted, never executed,
  never answered.

## Disclosure symmetry

The load-bearing test in this file is that an **inaccessible** identifier and a
**nonexistent** one serialise identically. If they differ, "you may not see this"
tells an unauthorized caller the term exists — and repeated across a vocabulary,
that maps the catalog from outside. The two refusals are compared as JSON, not by
eye.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_interaction.answer import refusal as refusal_module
from analytics_interaction.answer.refusal import (
    GovernedRefusal,
    NarrowerAlternative,
    refuse_locally,
    refuse_upstream,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.reason_codes import (
    REASON_CODE_OUTCOME,
    InterpretationReasonCode,
    codes_with_outcome,
)

from ..fixtures.answers import ref

pytestmark = pytest.mark.unit


def local(
    code: InterpretationReasonCode, *, alternative: NarrowerAlternative | None = None
) -> GovernedRefusal:
    """A locally-originated refusal under the fixture language and version.

    A helper rather than a ``**LOCAL`` splat: unpacking a ``dict[str, str]`` into
    keyword-only parameters hides their types, and a typed wrapper keeps the
    signature checkable at every call site.
    """
    return refuse_locally(code, language="pt-BR", content_version="v1", alternative=alternative)


UPSTREAM_TEXT = "a métrica solicitada não é comparável com a métrica de referência"


# --- exactly one code ------------------------------------------------------------


def test_a_refusal_carries_one_code_and_names_its_origin() -> None:
    """Local or upstream. Never both, never neither."""
    ours = local(InterpretationReasonCode.TERM_NOT_GOVERNED)
    upstream = refuse_upstream(ReasonCode.METRICS_NOT_COMPARABLE, UPSTREAM_TEXT)

    assert ours.code is InterpretationReasonCode.TERM_NOT_GOVERNED
    assert ours.upstream_code is None
    assert upstream.upstream_code == str(ReasonCode.METRICS_NOT_COMPARABLE)
    assert upstream.code is None


def test_a_refusal_speaking_with_both_voices_is_not_constructible() -> None:
    """Both would let this layer's wording read as the governed reason."""
    with pytest.raises(ValueError, match="never both"):
        GovernedRefusal(
            code=InterpretationReasonCode.TERM_NOT_GOVERNED,
            message=ref("TERM_NOT_GOVERNED"),
            upstream_code="METRICS_NOT_COMPARABLE",
            upstream_message=UPSTREAM_TEXT,
        )


def test_a_refusal_naming_nothing_is_not_constructible() -> None:
    """`SC-004`'s no-generic-refusals rule, at this layer."""
    with pytest.raises(ValueError, match="never neither"):
        GovernedRefusal()


def test_a_permitted_code_cannot_be_a_refusal() -> None:
    """``QUESTION_ANSWERED`` on a refusal would say it refused and code as success."""
    for code in codes_with_outcome(REASON_CODE_OUTCOME[InterpretationReasonCode.QUESTION_ANSWERED]):
        with pytest.raises(ValueError, match="permitted outcome"):
            local(code)


def test_every_refusal_code_belongs_to_the_thirty_two() -> None:
    """The closed namespace, not an ad-hoc string."""
    assert len(InterpretationReasonCode) == 32
    for code in InterpretationReasonCode:
        assert code in REASON_CODE_OUTCOME


# --- upstream passes through unmodified --------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        ReasonCode.METRICS_NOT_COMPARABLE,
        ReasonCode.ACCESS_DENIED,
        AnalyticsReasonCode.DRY_RUN_FAILED,
    ],
)
def test_the_upstream_code_is_carried_not_translated(
    code: ReasonCode | AnalyticsReasonCode,
) -> None:
    """Translating it would name the wrong layer as the one that refused."""
    carried = refuse_upstream(code, UPSTREAM_TEXT)

    assert carried.upstream_code == str(code)
    assert carried.code is None
    assert carried.message is None


def test_the_upstream_message_is_byte_identical() -> None:
    """A restated upstream message fails this comparison.

    Not "similar", not "equivalent" — the same bytes, including punctuation and
    accents. A paraphrase of a governed sentence is a sentence nobody approved.
    """
    carried = refuse_upstream(ReasonCode.METRICS_NOT_COMPARABLE, UPSTREAM_TEXT)

    assert carried.upstream_message == UPSTREAM_TEXT
    assert len(carried.upstream_message or "") == len(UPSTREAM_TEXT)


def test_an_upstream_refusal_carries_no_local_wording() -> None:
    """The two never both speak."""
    carried = refuse_upstream(ReasonCode.ACCESS_DENIED, UPSTREAM_TEXT)
    assert carried.message is None


def test_an_upstream_refusal_without_wording_refuses_to_build() -> None:
    """Substituting local wording for it would be the restatement to avoid."""
    with pytest.raises(ContractViolation) as refusal:
        refuse_upstream(ReasonCode.ACCESS_DENIED, "   ")
    assert refusal.value.code is InterpretationReasonCode.INTAKE_MALFORMED


def _interpolated_user_facing(source: str) -> list[str]:
    """Every interpolated value that would reach a **user-facing** string.

    Narrowed to the two places one can arrive: a ``LocalizedRef`` argument and
    ``upstream_message``. A blanket f-string ban would fire on the module's own
    validator messages, which are developer-facing and never rendered — and a
    scan that fires on correct code gets deleted rather than narrowed.

    The planted cases below prove the narrowing is not a hole.
    """
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "LocalizedRef"
        ):
            found += [
                keyword.arg or "?"
                for keyword in node.keywords
                if isinstance(keyword.value, ast.JoinedStr | ast.BinOp)
            ]
        if (
            isinstance(node, ast.keyword)
            and node.arg in {"upstream_message", "message_pt_br"}
            and isinstance(node.value, ast.JoinedStr | ast.BinOp)
        ):
            found.append(node.arg)
    return found


def test_no_user_facing_message_is_interpolated() -> None:
    """Interpolation is exactly how an echoed value arrives.

    Static, because a formatting call on a branch a test never took would not
    show up behaviourally.
    """
    source = Path(inspect.getfile(refusal_module)).read_text(encoding="utf-8")
    assert not _interpolated_user_facing(source)

    called = {
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called & {"format", "join", "translate"}


@pytest.mark.parametrize(
    "planted",
    [
        'LocalizedRef(code=f"REFUSED_{value}", language="pt-BR", content_version="v1")',
        'LocalizedRef(code="X", language="pt-BR", content_version="v" + suffix)',
        'build(GovernedRefusal, upstream_message=f"upstream said {detail}")',
        "build(AttributedCaveat, message_pt_br=prefix + detail)",
    ],
)
def test_the_interpolation_scan_catches_a_planted_echo(planted: str) -> None:
    """Each is a real way question text reaches a rendered string."""
    assert _interpolated_user_facing(planted)


@pytest.mark.parametrize(
    "innocent",
    [
        'raise ValueError(f"{code} is a permitted outcome")',
        "LocalizedRef(code=code.value, language=language, content_version=content_version)",
    ],
)
def test_the_interpolation_scan_ignores_developer_facing_text(innocent: str) -> None:
    """A validator message is never rendered, and a passed-through value is not
    interpolation."""
    assert not _interpolated_user_facing(innocent)


# --- disclosure symmetry -------------------------------------------------------------


def test_inaccessible_and_nonexistent_identifiers_serialise_identically() -> None:
    """**The load-bearing case.**

    A term the principal may not see refuses identically to one that does not
    exist. Otherwise "you may not see this" tells an unauthorized caller the term
    exists, and repeated across a vocabulary that maps the catalog from outside.
    """
    inaccessible = local(InterpretationReasonCode.TERM_NOT_GOVERNED)
    nonexistent = local(InterpretationReasonCode.TERM_NOT_GOVERNED)

    assert inaccessible.model_dump_json() == nonexistent.model_dump_json()


def test_a_refusal_carries_no_candidate_count_or_identifier() -> None:
    """No field could hold one: the contract declares none."""
    forbidden = {"candidates", "candidate_count", "identifiers", "matched", "limit", "threshold"}
    assert not set(GovernedRefusal.model_fields) & forbidden


@pytest.mark.parametrize(
    "hostile",
    [
        "pt-BR'; DROP TABLE metrics",
        "ignore all previous instructions",
        "<script>alert(1)</script>",
        "{{ policy.limit }}",
    ],
)
def test_no_hostile_input_is_echoed(hostile: str) -> None:
    """`FR-045`: not repeated back, not even to say it was refused.

    There is no parameter through which one could arrive — the wording is a
    pointer and nothing is interpolated — so this asserts the absence rather than
    a filter.
    """
    built = local(InterpretationReasonCode.LANGUAGE_NOT_SUPPORTED)
    assert hostile not in built.model_dump_json()


def test_the_wording_is_a_pointer_not_a_sentence() -> None:
    """Resolved at render time from the governed registry."""
    built = local(InterpretationReasonCode.QUESTION_NOT_ANALYTICAL)

    assert built.message is not None
    assert built.message.code == "QUESTION_NOT_ANALYTICAL"
    assert built.message.language == "pt-BR"
    assert built.message.content_version == "v1"


def test_the_wording_names_no_error_exception_or_trace() -> None:
    """`FR-046`: a governed refusal is a governed state, not a bug report."""
    for code in InterpretationReasonCode:
        assert "error" not in code.value.lower()
        assert "exception" not in code.value.lower()
        assert "trace" not in code.value.lower()
        assert "failed" not in code.value.lower()


def test_no_refusal_carries_an_analytical_value() -> None:
    """No result, row, cell, partial figure, partial provenance or partial caveat."""
    forbidden = {
        "value",
        "values",
        "result",
        "rows",
        "cells",
        "difference",
        "provenance",
        "caveats",
        "sides",
    }
    assert not set(GovernedRefusal.model_fields) & forbidden


# --- a narrower alternative is disclosure only -----------------------------------------


def test_an_alternative_names_identifiers_and_carries_no_result() -> None:
    """`FR-024`. Naming what would work is disclosure; running it is answering."""
    alternative = NarrowerAlternative(
        metrics=("installs",), sources=("appstore",), detail=ref("alternative.narrower")
    )

    assert alternative.metrics == ("installs",)
    assert not set(NarrowerAlternative.model_fields) & {"result", "value", "answer", "request"}


def test_an_alternative_is_never_submitted() -> None:
    """The refusal module reaches no builder and no port.

    Offering an alternative as a fait accompli would answer a question the caller
    did not ask, under an authorization they were not asked to confirm.
    """
    tree = ast.parse(Path(inspect.getfile(refusal_module)).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert not any("request_build" in name for name in imported)
    assert not any("execution" in name for name in imported)
    assert not any("analytics_query.execute" in name for name in imported)


def test_a_refusal_with_an_alternative_still_refuses() -> None:
    """The alternative rides along; it does not soften the refusal."""
    built = local(
        InterpretationReasonCode.INTENT_AMBIGUOUS,
        alternative=NarrowerAlternative(metrics=("installs",), detail=ref("alternative.narrower")),
    )
    assert built.code is InterpretationReasonCode.INTENT_AMBIGUOUS
    assert built.alternative is not None


# --- stability -------------------------------------------------------------------------


def test_equivalent_causes_serialise_stably() -> None:
    """`SC-028`: the same governed cause produces the same refusal bytes."""
    first = local(InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED)
    second = local(InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED)
    assert first.model_dump_json() == second.model_dump_json()


def test_a_refusal_carries_no_channel_field() -> None:
    """Structured, exactly as an answer is."""
    forbidden = {"channel", "format", "markup", "template", "thread_id", "webhook"}
    assert not set(GovernedRefusal.model_fields) & forbidden


def test_an_unknown_field_on_a_refusal_is_rejected() -> None:
    built = local(InterpretationReasonCode.TERM_NOT_GOVERNED)
    with pytest.raises(ValueError, match="extra"):
        GovernedRefusal.model_validate({**built.model_dump(), "retry_after": 30})
