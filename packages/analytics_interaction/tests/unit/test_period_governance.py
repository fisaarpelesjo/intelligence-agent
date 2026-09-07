"""Period governance — T080 (FR-009, FR-010; SC-017, SC-018).

Three properties.

**An unlisted expression refuses.** ``PERIOD_EXPRESSION_NOT_GOVERNED``, with no
nearest-match path anywhere — "semana passada" does not quietly become "the last
seven days".

**An expression whose convention `D-18` does not declare refuses.**
``PERIOD_CONVENTION_UNDECLARED``, rather than resolving under an assumption.
Whether "semana passada" starts on a Sunday or a Monday changes every weekly
number in the product, and nothing in this repository declares it. A library
picking one would be a library deciding a reporting standard.

**A listed expression resolves to an explicit closed range and nothing else** —
against the caller's ``reference_date``, in the canonical zone, through `001`'s
machinery. This feature performs no date arithmetic of its own, so IANA
resolution and the pre-2019 daylight-saving transitions stay `001`'s (`R-8`).

Every vocabulary below is **synthetic and fixture-only**. `D-18` is undeclared in
the shipped repository, and none of these instances is written to
`interpretation_governance/` or counts as evidence for it — the last test asserts
exactly that.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path

import pytest

from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.governance.schemas import (
    ContentApproval,
    PeriodExpression,
    PeriodVocabulary,
)
from analytics_interaction.governance.vocabulary import load_period_vocabulary
from analytics_interaction.interpretation import period as period_module
from analytics_interaction.interpretation.period import (
    resolve_explicit_period,
    resolve_expression,
    resolve_governed_period,
)

pytestmark = pytest.mark.unit

ON = date(2026, 8, 13)
REFERENCE = date(2026, 8, 13)

#: TEST-ONLY. Never written to `interpretation_governance/`, never `D-18` evidence.
FIXTURE_APPROVAL = ContentApproval(
    approver_role="data-governance", evidence_ref="FIXTURE-ONLY", approved_on=date(2026, 1, 1)
)


def _vocabulary(*expressions: PeriodExpression) -> PeriodVocabulary:
    """TEST-ONLY synthetic `D-18` instance."""
    return PeriodVocabulary(
        version="fixture-1",
        effective_from=date(2026, 1, 1),
        approval=FIXTURE_APPROVAL,
        expressions=expressions,
    )


def _expression(
    identifier: str = "fixture_month",
    *,
    surfaces: tuple[str, ...] = ("mês de teste",),
    boundary_rule: str = "fixture_anchor",
    week_start: str | None = None,
    month_rule: str | None = None,
) -> PeriodExpression:
    """TEST-ONLY synthetic expression."""
    return PeriodExpression(
        id=identifier,
        surface_forms=surfaces,
        boundary_rule=boundary_rule,
        inclusivity="fixture_inclusive",
        week_start=week_start,
        month_rule=month_rule,
    )


# --- the shipped state ---------------------------------------------------------


def test_the_shipped_vocabulary_holds_no_expression() -> None:
    """Nome historico fincado; a verdade desde OD-104 (2026-09-02): UMA instancia com as
    ONZE expressoes decididas, as duas semanais com week_start=monday declarado e as
    duas mensais com month_rule=civil_month — a convencao tem dente de validador."""
    instancias = load_period_vocabulary()
    assert len(instancias) == 1
    expressoes = {e.id: e for e in instancias[0].expressions}
    assert len(expressoes) == 11
    for semana in ("this_week", "last_week"):
        assert expressoes[semana].week_start == "monday", semana
    for mes in ("this_month", "last_month"):
        assert expressoes[mes].month_rule == "civil_month", mes


def test_an_expression_refuses_against_an_empty_vocabulary() -> None:
    with pytest.raises(ContractViolation) as caught:
        resolve_expression("semana passada", _vocabulary())
    assert caught.value.code is Code.PERIOD_EXPRESSION_NOT_GOVERNED


# --- an unlisted expression refuses --------------------------------------------


@pytest.mark.parametrize(
    "surface",
    [
        "semana passada",
        "mês passado",
        "últimos 7 dias",
        "ontem",
        "este trimestre",
        "mes de teste",  # unaccented near-miss of the authored surface
        "Mês de teste",  # differing case
    ],
)
def test_an_unlisted_expression_refuses_without_a_nearest_match(surface: str) -> None:
    """No approximation, and no normalisation of the caller's phrasing either.

    The near-miss cases are the point: a resolver that case-folded or stripped
    accents would resolve a period the vocabulary never listed, and the answer
    would look correct.
    """
    vocabulary = _vocabulary(_expression(surfaces=("mês de teste",)))
    with pytest.raises(ContractViolation) as caught:
        resolve_expression(surface, vocabulary)
    assert caught.value.code is Code.PERIOD_EXPRESSION_NOT_GOVERNED


def test_the_refusal_names_no_alternative() -> None:
    """Suggesting the nearest listed expression would be the approximation."""
    vocabulary = _vocabulary(_expression(identifier="last_week", surfaces=("semana anterior",)))
    with pytest.raises(ContractViolation) as caught:
        resolve_expression("semana passada", vocabulary)
    rendered = caught.value.detail.lower()
    assert "last_week" not in rendered
    assert "semana anterior" not in rendered


def test_a_listed_expression_resolves_by_id_or_by_surface_form() -> None:
    expression = _expression(identifier="fixture_month", surfaces=("mês de teste", "mes fixo"))
    vocabulary = _vocabulary(expression)
    # Equality, not identity: the models are frozen and the base revalidates,
    # so the entry a vocabulary holds is an equal value rather than the same
    # object. Equality is the right notion anyway — what matters is that the
    # governed entry came back, not which copy of it.
    assert resolve_expression("fixture_month", vocabulary) == expression
    assert resolve_expression("mês de teste", vocabulary) == expression
    assert resolve_expression("mes fixo", vocabulary) == expression


# --- an undeclared convention refuses ------------------------------------------


def test_a_week_relative_expression_without_a_week_start_is_not_constructible() -> None:
    """The schema refuses it, so an incomplete convention never reaches resolution."""
    with pytest.raises(Exception, match="week-relative"):
        _expression(identifier="last_week", boundary_rule="previous_week")


def test_a_month_relative_expression_without_a_month_rule_is_not_constructible() -> None:
    with pytest.raises(Exception, match="month-relative"):
        _expression(identifier="last_month", boundary_rule="previous_month")


def test_resolution_re_asserts_the_convention_it_was_handed() -> None:
    """Belt and braces: an entry that arrived without passing the contract refuses.

    ``PeriodExpression`` already enforces this, so reaching the branch means
    something bypassed construction — which is precisely when an assumed
    convention would be most dangerous.
    """
    incomplete = PeriodExpression.model_construct(
        id="last_week",
        surface_forms=("semana passada",),
        boundary_rule="previous_week",
        inclusivity="inclusive",
        week_start=None,
        month_rule=None,
    )
    vocabulary = PeriodVocabulary.model_construct(
        version="fixture-1",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        approval=FIXTURE_APPROVAL,
        expressions=(incomplete,),
    )
    with pytest.raises(ContractViolation) as caught:
        resolve_governed_period(
            "semana passada",
            reference_date=REFERENCE,
            vocabulary=vocabulary,
            boundaries=(date(2026, 8, 3), date(2026, 8, 9)),
            on=ON,
        )
    assert caught.value.code is Code.PERIOD_CONVENTION_UNDECLARED


# --- a listed expression resolves to an explicit closed range ------------------


def test_a_governed_expression_resolves_to_the_range_the_rule_produced() -> None:
    expression = _expression(
        identifier="last_week",
        surfaces=("semana passada",),
        boundary_rule="previous_week",
        week_start="monday",
    )
    resolved = resolve_governed_period(
        "semana passada",
        reference_date=REFERENCE,
        vocabulary=_vocabulary(expression),
        boundaries=(date(2026, 8, 3), date(2026, 8, 9)),
        on=ON,
    )

    assert resolved.start == date(2026, 8, 3)
    assert resolved.end == date(2026, 8, 9)
    assert resolved.expression == "last_week"
    assert resolved.reference_date == REFERENCE
    assert resolved.resolved_by == "governed_expression"


def test_the_convention_travels_on_the_resolved_period() -> None:
    """So an answer can state what "semana passada" meant on that day."""
    expression = _expression(
        identifier="last_week",
        surfaces=("semana passada",),
        boundary_rule="previous_week",
        week_start="monday",
    )
    resolved = resolve_governed_period(
        "semana passada",
        reference_date=REFERENCE,
        vocabulary=_vocabulary(expression),
        boundaries=(date(2026, 8, 3), date(2026, 8, 9)),
        on=ON,
    )
    assert resolved.convention is not None
    assert resolved.convention.week_start == "monday"
    assert resolved.convention.boundary_rule == "previous_week"


def test_explicit_dates_resolve_without_any_vocabulary() -> None:
    """`D-18` being unavailable does not block a caller who supplied real dates.

    That separation is deliberate and is why the feature is not entirely inert
    today: explicit dates carry their own meaning.
    """
    resolved = resolve_explicit_period(
        date(2026, 7, 1), date(2026, 7, 31), reference_date=REFERENCE, on=ON
    )
    assert resolved.start == date(2026, 7, 1)
    assert resolved.end == date(2026, 7, 31)
    assert resolved.expression is None
    assert resolved.convention is None
    assert resolved.resolved_by == "explicit_dates"


def test_an_inverted_explicit_range_refuses_through_001s_machinery() -> None:
    """`001` decides what an invalid range is; this feature does not re-decide."""
    with pytest.raises(ValueError, match="ends"):
        resolve_explicit_period(
            date(2026, 7, 31), date(2026, 7, 1), reference_date=REFERENCE, on=ON
        )


def test_resolution_is_deterministic_and_round_trips() -> None:
    first = resolve_explicit_period(
        date(2026, 7, 1), date(2026, 7, 31), reference_date=REFERENCE, on=ON
    )
    second = resolve_explicit_period(
        date(2026, 7, 1), date(2026, 7, 31), reference_date=REFERENCE, on=ON
    )
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


# --- no date arithmetic of this feature's own ----------------------------------


def test_the_period_module_performs_no_date_arithmetic() -> None:
    """No ``timedelta``, no month-end rule, no calendar.

    A second implementation of "what does last week mean" would eventually
    disagree with `001`'s — on exactly the days that are hardest to notice.
    """
    source = Path(inspect.getfile(period_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for arithmetic in ("timedelta", "relativedelta", "monthrange", "weekday", "isocalendar"):
        assert arithmetic not in names, f"the period module computes dates: {arithmetic}"

    operations = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub)
    ]
    assert not operations, f"the period module performs arithmetic: {operations}"


def test_the_canonical_range_comes_from_001() -> None:
    """Two call sites, both `001`'s ``canonical_period``.

    One for the governed-expression path and one for explicit dates. Counted
    so a third range-producing path could not appear without being noticed.
    """
    source = Path(inspect.getfile(period_module)).read_text(encoding="utf-8")
    assert "from semantic_catalog.periods.canonical import" in source
    assert source.count("canonical_period(") == 2, "expected exactly two call sites"


# --- fixtures never become governed content ------------------------------------


def test_no_fixture_vocabulary_is_written_to_governed_content() -> None:
    """A fixture must never become `D-18` evidence — re-derivada em OD-104 (2026-09-02):
    o conteudo embarcado agora existe, e o que este no afirma e que ele NAO e fixture:
    a approval nomeia papel real e data, nunca os marcadores de demonstracao."""
    instancias = load_period_vocabulary()
    assert len(instancias) == 1
    assert "demo" not in instancias[0].version.lower()
    assert "demonstration" not in instancias[0].approval.approver_role.lower()
