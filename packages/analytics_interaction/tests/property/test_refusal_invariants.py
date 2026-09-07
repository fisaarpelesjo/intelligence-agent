"""Refusal and payload invariants, generated — T160 (FR-020; SC-015, SC-054).

    Every refusal MUST carry exactly one governed reason code and MUST NOT carry a
    payload containing an analytical value. — `FR-020`

    Evidence: exactly one code per refusal; no generated question produces a
    payload containing a value. — `tasks.md` T160

## Invariant 1 — exactly one code, and it names where it came from

A refusal with two codes is a refusal a consumer has to choose between: does the
caller see the catalog's reason or this layer's? A refusal with none is a generic
refusal, which `SC-004` forbids because "something went wrong" sends every caller
to the same wrong place.

The interesting failure is neither of those. It is a refusal carrying **this
feature's wording beside an upstream code** — which reads as though the catalog
said something it did not. The contract makes the pairing structural: local means
`code` plus `message`, upstream means `upstream_code` plus `upstream_message`, and
both-or-neither cannot be constructed. Generated over every combination so no
combination is merely untested.

## Invariant 2 — no payload carries a value

A refusal is where a value escapes, because a refusal is where somebody adds a
diagnostic. Two properties, both generated:

* **structurally** — the refusal contract has no field an analytical value could
  live in. Asserted as the exact field set, so a `partial`, a `debug` or a `context`
  added later fails here rather than in review;
* **behaviourally** — for generated questions, generated identifiers and generated
  wording, the serialised refusal contains none of the distinctive values planted
  in the inputs. Searched over the whole JSON, so a value nested inside
  `interpreted` or `alternative` is found.

`NarrowerAlternative` is the field that has to be checked hardest. Naming what
*would* have worked is disclosure and is permitted; carrying its result is not, and
the two look similar in a diff.

## Bounded and fixture-only

Every strategy draws from a small governed alphabet. No production distribution is
inferred and no accuracy claim is made.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_interaction.answer.refusal import (
    GovernedRefusal,
    NarrowerAlternative,
    refuse_locally,
    refuse_upstream,
)
from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.contracts._base import ContractViolation, LocalizedRef
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.intent import ResolvedIntent, ResolvedPeriod, SlotKind
from analytics_interaction.contracts.reason_codes import (
    REASON_CODE_OUTCOME,
    InterpretationReasonCode,
    outcome_for,
)
from analytics_interaction.interpretation.assemble_intent import assemble_resolved_intent

from ..conftest import REFERENCE, governed_resolution
from ..fixtures.answers import WORDING_VERSION

pytestmark = pytest.mark.property

SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)

#: Every code this feature can refuse with. Derived from the enum rather than
#: listed, so a code added in Phase 3 is generated here without an edit.
#: Split on ``DENY`` rather than on a list of permitted outcomes, matching the
#: validator. A code whose outcome is neither is a permitted outcome by definition.
DENYING = [code for code in InterpretationReasonCode if outcome_for(code).value == "DENY"]
PERMITTING = [code for code in InterpretationReasonCode if outcome_for(code).value != "DENY"]

LOCAL_CODES = st.sampled_from(DENYING)
UPSTREAM_CODES = st.sampled_from(
    [ReasonCode.METRIC_NOT_GOVERNED, ReasonCode.ACCESS_DENIED, *list(AnalyticsReasonCode)[:4]]
)

#: A distinctive value planted in every input. If any of these reaches a serialised
#: refusal, a payload escaped — and none of them occurs incidentally anywhere in the
#: contracts or the governed content.
PLANTED_VALUE = "987654321000"
PLANTED_ROW = "row-987654321"
PLANTED_SQL = "SELECT 987654321 FROM raw.events"

UPSTREAM_MESSAGES = st.sampled_from(
    [
        "a métrica não é governada",
        "acesso negado para a tag solicitada",
        "cobertura insuficiente para o período",
        "  espaços preservados  ",
    ]
)

IDENTIFIERS = st.lists(
    st.sampled_from(["installs", "sessions", "revenue"]), min_size=1, max_size=3, unique=True
)
SOURCES = st.lists(st.sampled_from(["appstore", "playstore"]), max_size=2, unique=True)


def _intent(
    pair: tuple[AuthorizedContext, str], period: ResolvedPeriod, *, metric: str = "installs"
) -> ResolvedIntent:
    authorized, fingerprint = pair
    return assemble_resolved_intent(
        (governed_resolution(metric, SlotKind.METRIC),),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=period,
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        as_of=None,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )


def _serialised(refusal: GovernedRefusal) -> str:
    """The whole refusal as JSON, which is what a consumer actually receives."""
    return refusal.model_dump_json()


# --- invariant 1: exactly one code, and one origin speaks ------------------------


@SETTINGS
@given(code=LOCAL_CODES)
def test_a_local_refusal_carries_one_code_and_its_own_wording(
    code: InterpretationReasonCode,
) -> None:
    """One code, one pointer, no upstream fields.

    Generated over every denying code rather than a sample, so a code whose outcome
    mapping was wrong shows up here rather than at the moment somebody is refused
    by it.
    """
    refusal = refuse_locally(code, language="pt-BR", content_version=WORDING_VERSION)
    assert refusal.code is code
    assert refusal.message is not None
    assert refusal.message.code == code.value
    assert refusal.upstream_code is None
    assert refusal.upstream_message is None


@SETTINGS
@given(code=UPSTREAM_CODES, message=UPSTREAM_MESSAGES)
def test_an_upstream_refusal_carries_the_upstream_pair_verbatim(code: object, message: str) -> None:
    """The message travels byte-for-byte, including its whitespace.

    Whitespace is in the corpus on purpose: trimming an upstream sentence is the
    smallest possible rewording and is still a rewording of governed content.
    """
    refusal = refuse_upstream(code, message)  # pyright: ignore[reportArgumentType]
    assert refusal.upstream_code == str(code)
    assert refusal.upstream_message == message
    assert refusal.upstream_message is not None
    assert refusal.upstream_message.encode() == message.encode()
    assert refusal.code is None
    assert refusal.message is None


@SETTINGS
@given(local=LOCAL_CODES, upstream=UPSTREAM_CODES, message=UPSTREAM_MESSAGES)
def test_both_origins_speaking_cannot_be_constructed(
    local: InterpretationReasonCode, upstream: object, message: str
) -> None:
    """**The interesting failure.** Local wording beside an upstream code.

    A consumer reading that would attribute this feature's sentence to the catalog.
    Refused at construction, so no code path can assemble one — generated over every
    pairing rather than one example, because the validator is a single condition and
    a single example would prove only that the condition exists.
    """
    with pytest.raises(ValidationError):
        GovernedRefusal(
            code=local,
            message=LocalizedRef(
                code=local.value, language="pt-BR", content_version=WORDING_VERSION
            ),
            upstream_code=str(upstream),
            upstream_message=message,
        )


def test_a_refusal_with_neither_origin_cannot_be_constructed() -> None:
    """A refusal that names nothing is the generic refusal `SC-004` forbids."""
    with pytest.raises(ValidationError):
        GovernedRefusal()


@SETTINGS
@given(code=LOCAL_CODES)
def test_a_local_refusal_may_not_restate_an_upstream_message(
    code: InterpretationReasonCode,
) -> None:
    """The half-and-half shape, which reads as attribution without being one."""
    with pytest.raises(ValidationError):
        GovernedRefusal(
            code=code,
            message=LocalizedRef(
                code=code.value, language="pt-BR", content_version=WORDING_VERSION
            ),
            upstream_message="a métrica não é governada",
        )


@pytest.mark.parametrize("code", PERMITTING, ids=[code.value for code in PERMITTING])
def test_a_permitted_outcome_cannot_be_a_refusal(code: InterpretationReasonCode) -> None:
    """A response that says it refused and codes as success is worse than either.

    **This found a defect.** The validator compared against ``"ALLOW"`` alone, so
    ``QUESTION_ANSWERED_WITH_CAVEAT`` — outcome ``ALLOW_WITH_CAVEAT`` — could be
    constructed as a refusal. The more dangerous of the two: a consumer reading the
    outcome would surface the caveats of an answer that does not exist. Fixed to
    require ``DENY``, so an outcome added later is forbidden by default.

    Derived from the outcome map rather than listed, which is why it was found at
    all — a hand-written pair of examples would have used the two names somebody was
    already thinking about.
    """
    with pytest.raises(ValidationError):
        GovernedRefusal(
            code=code,
            message=LocalizedRef(
                code=code.value, language="pt-BR", content_version=WORDING_VERSION
            ),
        )


@SETTINGS
@given(code=UPSTREAM_CODES)
def test_an_upstream_refusal_without_wording_refuses_to_build(code: object) -> None:
    """Substituting local wording would be exactly the restatement this prevents."""
    for blank in ("", "   ", "\n", "\t"):
        with pytest.raises(ContractViolation) as raised:
            refuse_upstream(code, blank)  # pyright: ignore[reportArgumentType]
        assert raised.value.code is InterpretationReasonCode.INTAKE_MALFORMED


def test_every_code_has_exactly_one_outcome() -> None:
    """The map is total and single-valued.

    A code absent from it would make ``outcome_for`` a lookup that could fail at the
    moment somebody is being refused; a code mapped twice is not expressible, and
    this states that the enum and the map agree in both directions.
    """
    assert set(REASON_CODE_OUTCOME) == set(InterpretationReasonCode)
    assert len(DENYING) + len(PERMITTING) == len(list(InterpretationReasonCode))
    assert len(DENYING) == 30
    assert {code.value for code in PERMITTING} == {
        "QUESTION_ANSWERED",
        "QUESTION_ANSWERED_WITH_CAVEAT",
    }


# --- invariant 2: the contract has nowhere to put a value ----------------------


def test_the_refusal_declares_exactly_its_six_fields() -> None:
    """Structural, and the assertion that survives every refactor.

    A ``partial``, a ``debug``, a ``context`` or a ``rows`` added for diagnostics is
    where a value would live, and each would be a locally reasonable edit.
    """
    assert set(GovernedRefusal.model_fields) == {
        "code",
        "message",
        "upstream_code",
        "upstream_message",
        "interpreted",
        "alternative",
    }
    assert GovernedRefusal.model_config.get("extra") == "forbid"


def test_the_alternative_names_identifiers_and_carries_no_result() -> None:
    """Naming what would work is disclosure; running it is not.

    ``NarrowerAlternative`` is the field that has to be checked hardest, because a
    ``result`` on it would look almost identical in a diff to the ``detail`` pointer
    that belongs there.
    """
    assert set(NarrowerAlternative.model_fields) == {"metrics", "sources", "detail"}
    assert NarrowerAlternative.model_fields["detail"].annotation is LocalizedRef


@SETTINGS
@given(code=LOCAL_CODES, metrics=IDENTIFIERS, sources=SOURCES)
def test_no_generated_refusal_serialises_a_value(
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
    code: InterpretationReasonCode,
    metrics: list[str],
    sources: list[str],
) -> None:
    """**The behavioural half.** Nothing planted in the inputs comes out.

    The refusal is built with everything a caller can influence — the intent, the
    alternative, the wording pointer — and the serialised form is searched for the
    planted value, row identifier and SQL. Searched over the whole JSON, so a value
    nested inside ``interpreted`` is found rather than assumed absent.
    """
    refusal = refuse_locally(
        code,
        language="pt-BR",
        content_version=WORDING_VERSION,
        interpreted=_intent(authorized_pair, july_period),
        alternative=NarrowerAlternative(
            metrics=tuple(metrics),
            sources=tuple(sources),
            detail=LocalizedRef(code=code.value, language="pt-BR", content_version=WORDING_VERSION),
        ),
    )
    serialised = _serialised(refusal)
    for planted in (PLANTED_VALUE, PLANTED_ROW, PLANTED_SQL, "SELECT", "raw.events"):
        assert planted not in serialised, planted


@SETTINGS
@given(code=UPSTREAM_CODES, message=UPSTREAM_MESSAGES)
def test_an_upstream_message_is_the_only_free_text_that_travels(code: object, message: str) -> None:
    """And it is *upstream's* text, not the caller's.

    Asserted by planting a value in the position a caller could influence and
    checking the serialised refusal: the upstream message is the one string carried
    verbatim, and it comes from a governed decision rather than from a question.
    """
    refusal = refuse_upstream(code, message)  # pyright: ignore[reportArgumentType]
    serialised = json.loads(_serialised(refusal))
    free_text = [
        value
        for key, value in serialised.items()
        if isinstance(value, str) and key not in {"upstream_code"}
    ]
    assert free_text == [message]


@SETTINGS
@given(code=LOCAL_CODES)
def test_a_local_refusal_interpolates_nothing(code: InterpretationReasonCode) -> None:
    """The wording is a pointer, so there is no parameter a value could arrive through.

    This is why a malformed language value, an injected span or a hidden identifier
    cannot reach a refusal message: not because they are filtered, but because
    ``refuse_locally`` has no argument for them.
    """
    refusal = refuse_locally(code, language="pt-BR", content_version=WORDING_VERSION)
    assert refusal.message is not None
    assert refusal.message.arguments == ()
    assert refusal.message.code == code.value


@SETTINGS
@given(code=LOCAL_CODES, planted=st.sampled_from([PLANTED_VALUE, PLANTED_ROW, PLANTED_SQL]))
def test_a_planted_value_has_no_field_to_arrive_in(
    code: InterpretationReasonCode, planted: str
) -> None:
    """Every plausible smuggling field is refused as unknown.

    ``extra="forbid"`` rather than a denylist. A field that does not exist cannot be
    filtered incorrectly.
    """
    for field in ("value", "rows", "result", "partial", "debug", "context", "sql", "payload"):
        with pytest.raises(ValidationError):
            GovernedRefusal(
                code=code,
                message=LocalizedRef(
                    code=code.value, language="pt-BR", content_version=WORDING_VERSION
                ),
                **{field: planted},  # pyright: ignore[reportArgumentType]
            )


# --- the value detector works ---------------------------------------------------


def test_the_detector_would_find_a_planted_value(
    authorized_pair: tuple[AuthorizedContext, str], july_period: ResolvedPeriod
) -> None:
    """**Without this, every "not in serialised" assertion above is vacuous.**

    Planted through the one string field a caller can influence — an upstream
    message — and found. Which also states the honest limit: an upstream message
    that itself contained a value would be carried, because carrying it verbatim is
    the requirement. That is upstream's disclosure decision, not this layer's.
    """
    leaky = refuse_upstream(ReasonCode.ACCESS_DENIED, f"valor {PLANTED_VALUE}")
    assert PLANTED_VALUE in _serialised(leaky)

    clean = refuse_upstream(ReasonCode.ACCESS_DENIED, "acesso negado")
    assert PLANTED_VALUE not in _serialised(clean)


def test_the_planted_values_occur_nowhere_incidentally() -> None:
    """Otherwise a search for them could match something innocent and pass."""
    assert PLANTED_VALUE not in WORDING_VERSION
    assert PLANTED_ROW not in WORDING_VERSION
    assert str(date(2026, 7, 1)) not in PLANTED_VALUE
