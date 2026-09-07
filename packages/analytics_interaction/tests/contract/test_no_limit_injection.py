"""No governed value is injectable — T092 (FR-030; SC-002).

    The system MUST NOT set, override, weaken or suggest any governed limit,
    policy value, observation or data revision, and MUST NOT supply an as-of pin
    other than one the caller explicitly provided and the response discloses.
    — `FR-030`

    Evidence: the fields do not exist. — `tasks.md` T092

That evidence line is the design. This is not "a validator rejects a limit" —
`002`'s ``AnalyticsQuery`` declares six fields and none of them is a limit, a
threshold, an observation or a revision, so there is nothing to reject. The same
holds for the intent this feature builds it from.

**Four families, and each fails differently if it leaks:**

| Family | What would go wrong |
|---|---|
| limits and policy values | this feature would be setting a bound `D-14`/`D-19` owns |
| observations and revisions | the requester would become authoritative about
  the state of the data |
| an unrequested ``as_of`` | every question would pin to a definition nobody chose |
| `BD-1`'s excluded three | `002` rejects `comparison`, `order_by` and `limit` as unknown fields |

The ``as_of`` case is the subtle one and gets the most attention below: the value
must be the caller's, or absent, and **never** ``reference_date``. A derivation
there is invisible in a passing request and wrong in every relative-period
answer.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path

import pytest
from analytics_query.contracts.request import AnalyticsQuery

import analytics_interaction
from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.contracts.intent import ResolvedIntent
from analytics_interaction.contracts.request_build import REQUEST_FIELDS, build_analytics_query

from ..conftest import JULY, REFERENCE

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent

#: Governed values this feature may never set, suggest or carry.
GOVERNED_VALUE_FIELDS = (
    "max_bytes",
    "maximum_bytes_billed",
    "max_rows",
    "maximum_rows",
    "row_limit",
    "byte_limit",
    "timeout",
    "execution_timeout_seconds",
    "maximum_range_days",
    "minimum_aggregation_threshold",
    "threshold",
    "policy_value",
    "freshness",
    "coverage",
    "availability",
    "data_revision",
    "revision",
    "observation",
    "last_updated",
    "staleness",
)

#: `BD-1`. `002` excludes these deliberately, and a request naming one is
#: rejected as an unknown field.
BD1_EXCLUDED = ("comparison", "order_by", "limit")


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


# --- the fields do not exist ---------------------------------------------------


@pytest.mark.parametrize("field", GOVERNED_VALUE_FIELDS)
def test_the_request_contract_declares_no_governed_value_field(field: str) -> None:
    assert field not in AnalyticsQuery.model_fields


@pytest.mark.parametrize("field", GOVERNED_VALUE_FIELDS)
def test_the_intent_contract_declares_no_governed_value_field(field: str) -> None:
    """The intent is where one would arrive before reaching the request."""
    assert field not in ResolvedIntent.model_fields


@pytest.mark.parametrize("field", BD1_EXCLUDED)
def test_the_request_contract_excludes_the_bd1_fields(field: str) -> None:
    assert field not in AnalyticsQuery.model_fields


@pytest.mark.parametrize("field", (*GOVERNED_VALUE_FIELDS, *BD1_EXCLUDED))
def test_supplying_the_field_is_refused_as_unknown(field: str) -> None:
    """Refused because the field does not exist, not by a rule naming it."""
    with pytest.raises(Exception, match=r"extra_forbidden|Extra inputs"):
        AnalyticsQuery.model_validate(
            {
                "metrics": ("installs",),
                "date_range": {"start": JULY[0].isoformat(), "end": JULY[1].isoformat()},
                field: 1,
            }
        )


def test_the_builder_names_exactly_the_six_public_fields() -> None:
    """Enumerated, so an upstream field added or removed is a visible change."""
    assert tuple(AnalyticsQuery.model_fields) == REQUEST_FIELDS
    assert len(REQUEST_FIELDS) == 6


def test_no_module_names_a_governed_limit_at_all() -> None:
    """Not even as a local variable. A limit named here is a limit half-set."""
    forbidden = (
        "maximum_bytes_billed",
        "minimum_aggregation_threshold",
        "execution_timeout_seconds",
        "maximum_range_days",
    )
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.arg
                if isinstance(node, ast.arg)
                else ""
            )
            if name in forbidden:
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {name}")
    assert not offenders, f"a governed limit is named: {offenders}"


# --- the period is the date range, and only the date range ---------------------


def test_no_date_filter_is_constructed(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """`002` §4.3.1: the date dimension is not filterable.

    Expressing the period twice — once where `002` accepts it, once where it
    does not — would be rejected downstream after this layer had told the caller
    the question was fine.
    """
    authorized, fingerprint = authorized_pair
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    assert request.filters == ()
    assert request.date_range.start == JULY[0]
    assert request.date_range.end == JULY[1]


def test_the_builder_creates_no_filter_from_the_period() -> None:
    """Checked in the source too: no filter is built from period fields."""
    source = inspect.getsource(build_analytics_query)
    body = source.split('"""')[2]
    assert "GovernedFilter" not in body
    assert "filters=intent.filters" in body


# --- `as_of` is the caller's, or absent ----------------------------------------


def test_an_omitted_as_of_stays_omitted(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """`None` is the answer: current-definition resolution, `002`'s own behaviour."""
    authorized, fingerprint = authorized_pair
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    assert resolved_intent.as_of is None
    assert request.as_of is None
    assert '"as_of":null' in request.model_dump_json()


def test_the_reference_date_never_becomes_the_as_of(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """The failure this prevents is invisible in a passing request."""
    authorized, fingerprint = authorized_pair
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    assert resolved_intent.reference_date == REFERENCE
    assert request.as_of != REFERENCE
    assert request.as_of is None


def test_a_supplied_as_of_is_carried_verbatim(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: object,
) -> None:
    from analytics_interaction.contracts.intake import DeclaredLanguage
    from analytics_interaction.interpretation.assemble_intent import assemble_resolved_intent

    from ..conftest import governed_resolution

    authorized, fingerprint = authorized_pair
    pinned = assemble_resolved_intent(
        (governed_resolution("installs"),),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=july_period,  # type: ignore[arg-type]
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        as_of=date(2026, 1, 15),
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )
    request = build_analytics_query(pinned, authorized=authorized, auth_fingerprint=fingerprint)
    assert request.as_of == date(2026, 1, 15)


def test_the_builder_assigns_as_of_from_the_intent_and_nothing_else() -> None:
    """Source-level, because the derivation would be one token wide.

    ``as_of=intent.reference_date`` differs from ``as_of=intent.as_of`` by six
    characters and would pass every behavioural test that happened to supply
    equal dates.
    """
    tree = ast.parse(inspect.getsource(build_analytics_query))
    assignments = {
        keyword.arg: ast.unparse(keyword.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "AnalyticsQuery"
        for keyword in node.keywords
        if keyword.arg
    }
    # Read from the AST rather than the source text: the line carries an inline
    # comment saying "never `reference_date`", and a text scan would flag the
    # explanation instead of a derivation.
    assert assignments["as_of"] == "intent.as_of"
    assert "reference_date" not in assignments.values()
    assert set(assignments) == set(REQUEST_FIELDS)


def test_no_module_assigns_one_date_from_the_other() -> None:
    """The derivation shape, checked across the whole package."""
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "as_of":
                rendered = ast.unparse(node.value)
                if "reference_date" in rendered:
                    offenders.append(f"{path.relative_to(SRC).as_posix()}: as_of={rendered}")
            if isinstance(node, ast.keyword) and node.arg == "reference_date":
                rendered = ast.unparse(node.value)
                if "as_of" in rendered:
                    offenders.append(
                        f"{path.relative_to(SRC).as_posix()}: reference_date={rendered}"
                    )
    assert not offenders, f"one date is derived from the other: {offenders}"


# --- no defaults ----------------------------------------------------------------


def test_the_builder_invents_no_collection(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """An absent collection is passed absent, not filled with a guess."""
    authorized, fingerprint = authorized_pair
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    assert request.dimensions == ()
    assert request.sources == ()
    assert request.filters == ()
    assert request.metrics == ("installs",)


def test_the_builder_declares_no_default_of_its_own() -> None:
    """No literal collection, date or number is constructed in the builder."""
    tree = ast.parse(inspect.getsource(build_analytics_query))
    literals = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.List | ast.Dict | ast.Set)
        or (isinstance(node, ast.Constant) and isinstance(node.value, int | float))
    ]
    assert not literals, f"the builder invents a value: {literals}"
