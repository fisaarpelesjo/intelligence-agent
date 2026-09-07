"""T112 — `003`'s adversarial scenarios, re-run through the composed entry point (`SC-057`).

`003` already proves each of these against its components. The question this file answers is
narrower and it is the one ADR 0017's authorization created: does routing the same attack through
`ask` weaken it? A composition can lose a property without any component changing — by reordering,
by catching, by rewording, or by reading a value the component would have refused to read.

## Reachable families, and the ones that are not

`ask` refuses at step 7 for every analytical question today, and it bounds what can be attacked
through this surface.

**The reason changed with `F12`'s correction and the conclusion did not.** Step 7 used to pass the
*whole* question to `resolve_governed_period`, which matches by exact equality, so no input could
satisfy both halves of a question. It now searches the question for the expression it *contains*,
over the same spans step 6 uses. What still refuses every question is that production `D-18`
declares no expression at all: `interpretation_governance/period-vocabulary.yaml` carries
`instances: []`, so `locate_expression` finds nothing and raises
`PERIOD_EXPRESSION_NOT_GOVERNED`.

Measured rather than assumed: this file's assertions were unchanged by that correction and the whole
`003` suite stayed at its full count. The premise survived for a **different cause**, which is why
this paragraph names the cause instead of the mechanism — a paragraph that named the old mechanism
would now be false while every test still passed.

Covered here, because reachable: **injection** at step 5, **enumeration by probing** across steps 6
and 7, **tag escalation** at step 2, **fabricated identifiers** of each kind, and **fixture
substitution** by flag or environment.

Not covered, because unreachable through `ask`: seal tampering, replay and expiry (step 10),
asserted freshness (step 14), cross-question reconstruction (step 10), partial-comparison leakage
(steps 13 and 14). Those live in `003`'s own adversarial suites against its components, and
re-running them here would need the period gap closed first. `T112` is therefore **not** marked
complete on this file alone, and :func:`test_the_unreachable_families_are_still_unreachable` fails
when that changes.

## The property every scenario shares

**No refusal may carry any part of the question.** Injected content that reaches a refusal detail
reaches a log line, an audit event and a screen. So each scenario asserts the refusal's `detail`
contains no fragment of the input it was raised for, not merely that the code was right.
"""

from __future__ import annotations

import pytest

from analytics_interaction.authorization.refusal import AuthorizationRefused
from analytics_interaction.contracts.intake import PrincipalContext, PrincipalType
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.interact import InteractionCollaborators

from ..fixtures.counters import SURFACES, Surfaces
from ..integration.test_interact_equivalence import (
    build_collaborators,
    coded,
    fixture_policy,
    fixture_vocabulary,
    payload_for,
    refusal_from_ask,
)

pytestmark = pytest.mark.adversarial

#: A question naming a governed metric, so a scenario reaches step 6 rather than stopping earlier.
GOVERNED = "instalacoes"


def _usable(**overrides: object) -> InteractionCollaborators:
    """Collaborators whose governed content resolves, so an attack reaches the step it targets."""
    arguments: dict[str, object] = {
        "policy_instances": fixture_policy(),
        "vocabulary_instances": fixture_vocabulary(),
    }
    arguments.update(overrides)
    return build_collaborators(**arguments)  # pyright: ignore[reportArgumentType]


def _pattern() -> str:
    """The pattern `D-19`'s fixture redaction rule declares."""
    return fixture_policy()[0].redaction_rule.patterns[0]


def _assert_discloses_nothing(detail: str, question: str) -> None:
    """No fragment of ``question`` appears in ``detail``.

    Fragments rather than the whole string: a refusal that echoed half the question would pass a
    containment check on the whole. Every whitespace-separated token of length three or more is
    checked, which is short enough to catch an echoed identifier and long enough not to trip on
    articles.
    """
    leaked = sorted({token for token in question.split() if len(token) >= 3 and token in detail})
    assert not leaked, (
        f"the refusal detail echoes {leaked} back from the question. Injected content in a detail "
        "reaches a log line, an audit event and a screen"
    )


# --------------------------------------------------------------------------------------------------
# Injection
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param("{pattern}", id="bare"),
        pytest.param("quantas instalacoes {pattern}", id="appended"),
        pytest.param("{pattern} quantas instalacoes", id="prepended"),
        pytest.param("quantas {pattern} instalacoes", id="embedded"),
        pytest.param("QUANTAS {pattern} INSTALACOES", id="upper-cased-around"),
    ],
)
def test_injection_refuses_wherever_the_pattern_sits(shape: str) -> None:
    """A governed pattern refuses regardless of where in the question it appears.

    Five placements rather than one, because a screener that only examined a prefix would pass a
    single bare-pattern scenario and let every other placement through.
    """
    question = shape.format(pattern=_pattern())
    refusal = coded(refusal_from_ask(payload_for(question), _usable()), step="injection")

    assert refusal.code is Code.INSTRUCTION_INJECTION_REFUSED
    _assert_discloses_nothing(refusal.detail, question)


def test_injection_is_refused_before_the_catalog_is_touched() -> None:
    """Screening precedes slot resolution, so injected text never reaches a cost surface.

    An injection that got as far as the catalog would have spent budget on an attack, and would
    have put attacker-controlled text into a discovery call.
    """
    surfaces = Surfaces()
    refusal = coded(
        refusal_from_ask(payload_for(_pattern()), _usable(surfaces=surfaces)), step="injection"
    )

    assert refusal.code is Code.INSTRUCTION_INJECTION_REFUSED
    assert surfaces.counts() == dict.fromkeys(SURFACES, 0), (
        f"an injected question reached a cost surface: {surfaces.counts()}"
    )


# --------------------------------------------------------------------------------------------------
# Enumeration by probing
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "probe",
    [
        pytest.param("instalacoes", id="a-real-governed-metric"),
        pytest.param("metrica_que_nao_existe", id="a-fabricated-metric"),
        pytest.param("plataforma", id="a-real-governed-dimension"),
        pytest.param("dimensao_que_nao_existe", id="a-fabricated-dimension"),
        pytest.param("fonte_que_nao_existe", id="a-fabricated-source"),
        pytest.param("palavra-sem-qualquer-relacao", id="an-unrelated-word"),
    ],
)
def test_probing_cannot_distinguish_what_exists_from_what_does_not(probe: str) -> None:
    """Six probes, one answer. That is what makes enumeration useless.

    A caller who could tell "governed but not resolvable here" from "never governed" would
    enumerate the catalog by asking, without ever being authorised to read any of it. Every probe
    must reach the same refusal, and none may have its own term echoed back.
    """
    refusal = coded(refusal_from_ask(payload_for(probe), _usable()), step="probing")

    assert refusal.code is Code.PERIOD_EXPRESSION_NOT_GOVERNED, (
        f"{probe!r} refused with {refusal.code.value}, which differs from the other probes and so "
        "tells the caller something about whether it exists"
    )
    _assert_discloses_nothing(refusal.detail, probe)


def test_the_probe_answers_are_byte_identical_to_each_other() -> None:
    """The stronger form: identical **details**, not merely identical codes.

    Two probes sharing a code but differing in wording are still an oracle. Comparing the details
    directly is what closes that, and it is why this is a separate node from the parametrised one
    above — that one would pass if each detail named its own probe.
    """
    probes = ("instalacoes", "metrica_que_nao_existe", "plataforma", "palavra-sem-relacao")
    details = {
        probe: coded(refusal_from_ask(payload_for(probe), _usable()), step="probing").detail
        for probe in probes
    }

    assert len(set(details.values())) == 1, (
        f"probes produce distinguishable refusals: {details}. Any difference is an enumeration "
        "channel"
    )


# --------------------------------------------------------------------------------------------------
# Tag escalation
# --------------------------------------------------------------------------------------------------


def test_a_principal_cannot_grant_itself_tags_through_the_payload() -> None:
    """The payload declares tags; the resolver decides them. Only the resolver's answer may govern.

    `PrincipalContext` carries `granted_access_tags`, and the payload is attacker-controlled. If
    the composed path used the payload's claim rather than the resolver's answer, a caller would
    grant itself access by typing it.

    **The measured behaviour is stronger than what this test first asserted, and the correction is
    worth recording.** The first version required the two outcomes to be byte-identical — claiming
    tags must change nothing. Measuring it showed something better: a payload claiming tags the
    resolver did not grant refuses at **step 2** with `AUTHORIZATION_CONTEXT_UNRESOLVABLE`. The
    preflight does not ignore the mismatch, it refuses on it.

    So the property asserted is the one that actually protects: claiming tags can never **help**.
    It either changes nothing or it refuses earlier, and it must never carry the caller further
    than the modest payload did.
    """
    resolved = PrincipalContext(
        principal_ref="t112-principal",
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        granted_access_tags=frozenset({"standard"}),
        authorization_policy_pin="t112-pin",
    )

    modest = payload_for(GOVERNED, principal=resolved)
    greedy = dict(modest)
    greedy["principal"] = {
        **resolved.model_dump(),
        "granted_access_tags": ["standard", "restricted_financial", "inventado"],
    }

    surfaces = Surfaces()
    from_modest = coded(refusal_from_ask(modest, _usable(principal=resolved)), step="modest")
    from_greedy = refusal_from_ask(greedy, _usable(principal=resolved, surfaces=surfaces))

    assert from_modest.code is Code.PERIOD_EXPRESSION_NOT_GOVERNED, (
        f"the modest payload refused with {from_modest.code.value}, so this scenario is no longer "
        "comparing against a question that got as far as step 7"
    )
    assert isinstance(from_greedy, AuthorizationRefused), (
        f"claiming ungranted tags produced {type(from_greedy).__name__} rather than a step-2 "
        "refusal, so the preflight accepted a context the resolver did not grant"
    )
    assert surfaces.counts() == dict.fromkeys(SURFACES, 0), (
        f"a payload claiming extra tags reached a cost surface: {surfaces.counts()}"
    )


def test_an_unresolvable_principal_refuses_whatever_it_claims() -> None:
    """The same attack against a principal the resolver does not know at all."""
    greedy = PrincipalContext(
        principal_ref="t112-unknown",
        principal_type=PrincipalType.SERVICE_PRINCIPAL,
        authorization_scope="default",
        granted_access_tags=frozenset({"standard", "restricted_financial"}),
        authorization_policy_pin="t112-pin",
    )
    surfaces = Surfaces()

    refusal = refusal_from_ask(
        payload_for(GOVERNED, principal=greedy), _usable(principal=None, surfaces=surfaces)
    )

    assert isinstance(refusal, AuthorizationRefused)
    assert surfaces.counts() == dict.fromkeys(SURFACES, 0), (
        f"an unknown principal claiming tags reached a cost surface: {surfaces.counts()}"
    )


# --------------------------------------------------------------------------------------------------
# Fabricated identifiers, and fixture substitution
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fabricated",
    [
        pytest.param({"text": GOVERNED, "sql": "SELECT 1"}, id="sql-field"),
        pytest.param({"text": GOVERNED, "access_tags": ["standard"]}, id="access-tags-field"),
        pytest.param({"text": GOVERNED, "max_rows": 10}, id="max-rows-field"),
        pytest.param({"text": GOVERNED, "fixture": True}, id="fixture-flag-field"),
        pytest.param({"text": GOVERNED, "channel": "slack"}, id="channel-field"),
    ],
)
def test_an_unknown_intake_field_is_refused_rather_than_ignored(
    fabricated: dict[str, object],
) -> None:
    """A field the contract does not declare refuses, including the one that would select a fixture.

    ``fixture: True`` is the important row. If an unknown field were ignored rather than refused, a
    caller could ship a flag and hope some layer honoured it. The contract's ``extra="forbid"`` is
    what refuses these, and this asserts the composed path does not soften it.
    """
    payload = {**payload_for(GOVERNED), **fabricated}
    refusal = coded(refusal_from_ask(payload, _usable()), step="fabricated field")

    assert refusal.code is Code.INTAKE_MALFORMED, (
        f"an unknown intake field refused with {refusal.code.value} rather than as malformed"
    )


def test_no_environment_variable_changes_the_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixture substitution by environment, refused by there being nothing to substitute.

    Six plausible switch names are set at once. The outcome must be byte-identical to the outcome
    with none of them set — if any layer read one, this is where it would show.
    """
    baseline = coded(refusal_from_ask(payload_for(GOVERNED), _usable()), step="baseline")

    for name in (
        "ANALYTICS_INTERACTION_FIXTURE",
        "ANALYTICS_INTERACTION_MODE",
        "INTERACTION_USE_FIXTURES",
        "USE_FIXTURES",
        "FIXTURE",
        "ENV",
    ):
        monkeypatch.setenv(name, "1")

    switched = coded(refusal_from_ask(payload_for(GOVERNED), _usable()), step="switched")

    assert baseline.code is switched.code, "an environment variable changed the reason code"
    assert baseline.detail == switched.detail, "an environment variable changed the refusal wording"


# --------------------------------------------------------------------------------------------------
# The boundary of this file, asserted rather than described
# --------------------------------------------------------------------------------------------------


def test_the_unreachable_families_are_still_unreachable() -> None:
    """Seal tampering, replay, expiry, freshness and comparison leakage need step 10 or later.

    They are unreachable while every analytical question refuses at step 7. This asserts that wall
    is still there, so the day it falls this fails and the remaining families get written — rather
    than the prose above quietly becoming false.

    ## Why this node survived `T112` being marked complete

    On 2026-08-19 the owner narrowed `T112`'s criterion to the five reachable families and the task
    was marked. This node was **not** deleted along with the seven removed ones. A task closing is a
    scope decision; it does not make an unwritten attack surface safe.

    What it signals changed, and only that: it used to mean "`T112` cannot be marked yet", and now
    means "the seven deferred families can come back". The ledger row names them individually, and
    this failing node is what tells someone the deferral has expired. Deleting it would have turned
    a deferral into a silent permanent gap — in an **adversarial** suite, which is the worst place
    for one.
    """
    refusal = coded(refusal_from_ask(payload_for(GOVERNED), _usable()), step="the wall")
    assert refusal.code is Code.PERIOD_EXPRESSION_NOT_GOVERNED, (
        f"an analytical question now refuses with {refusal.code.value} rather than at step 7. If "
        "period gap closed, the seal, replay, expiry, freshness and comparison families became "
        "reachable and must be written rather than this assertion adjusted"
    )
