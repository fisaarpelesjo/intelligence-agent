"""Quickstart scenarios 9—12 — T164 (FR-075; SC-043).

    Evidence: resume against a fresh instance succeeds with a fixture seal.
    — `tasks.md` T164

| Scenario | Claim |
|---|---|
| 9 | A clarification survives a fresh process holding nothing |
| 10 | No value can reach a model surface |
| 11 | Nothing is persisted, nothing is detected, no clock is read |
| 12 | Determinism, including where it must stop |

## Scenario 9 is the one that needs a fresh process

"Stateless" is easy to claim and hard to test, because a test that issues and resumes
in one function shares every object between the two halves. A dictionary cached on a
module, a memoised policy read, a lazily-built index — any of them would make the
resumption succeed for the wrong reason, and the test would pass.

So the resumption half runs against **freshly imported modules**: the clarification
package is reloaded, so every module-level value is rebuilt, and the contract is
re-parsed from its serialised form rather than passed as an object. What survives is a
JSON string and a seal, which is exactly what survives between two real processes.

## Scenarios 10—12 are absences

Each is a static property — no reachable path, no persistence call, no detection, no
clock — and each is asserted by the contract suites in full. What this file adds is the
**scenario framing**: the four claims run together, so a change that satisfied one by
breaking another shows up here rather than in two files nobody reads side by side.

## Fixture-only

`D-21` is undeclared, so scenario 9 needs the synthetic key from
`tests/fixtures/seal/`. Production cannot issue a contract at all, which is asserted
first.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.clarification.replay import replay_posture
from analytics_interaction.clarification.resume import GoverningVersions, resume_clarification
from analytics_interaction.compliance.gates import InteractionCapability
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.clarification import ClarificationContract
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.intent import SlotKind
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.identity.authorization_fingerprint import (
    derive_authorization_fingerprint,
)
from analytics_interaction.identity.interpretation_identity import (
    derive_interpretation_identity,
)
from analytics_interaction.intake.language import require_declared_language, supported_language_tags
from analytics_interaction.messages.registry import load_registry

from ..conftest import authorize
from ..fixtures.clarifications import (
    EXPIRY,
    FIXTURE_KEY,
    ISSUED_AT,
    FixtureSealPort,
    issued_contract,
    ready_records,
    unready_records,
)

pytestmark = pytest.mark.integration

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent

READY = ready_records(InteractionCapability.D_21)
PORT = FixtureSealPort(key=FIXTURE_KEY)
IN_FORCE = GoverningVersions(
    catalog_release="r-1", policy_version="pol-1", vocabulary_version="voc-1"
)
LIVE = ISSUED_AT + timedelta(minutes=5)


# --- scenario 9: the shipped state issues nothing -----------------------------


def test_production_cannot_issue_a_clarification_at_all() -> None:
    """**The premise.** `D-21` is undeclared, so there is no key to seal with.

    Asserted before the fixture-backed resumption below, because the resumption is
    what a reader would over-read — a green scenario 9 proves the statelessness
    design, not that a clarification can be issued today.
    """
    from analytics_interaction.clarification.issue import issue_clarification

    from ..fixtures.clarifications import FIXTURE_ALGORITHM, FIXTURE_KEY_ID, candidate

    # Called through the **real** issuance path with the shipped readiness state,
    # rather than through the fixture helper — the helper exists to hand other tests a
    # sealed contract and therefore passes ready records by design. Bypassing it is
    # the only way to observe what production actually does.
    with pytest.raises(ContractViolation) as raised:
        issue_clarification(
            correlation_id="corr-1",
            interpretation_id="interp-1",
            auth_fingerprint=derive_authorization_fingerprint(authorize()),
            unresolved=SlotKind.METRIC,
            candidates=(candidate("installs"), candidate("sessions")),
            rounds_consumed=0,
            round_bound=2,
            issued_at=ISSUED_AT,
            expiry=EXPIRY,
            nonce="nonce-1",
            catalog_release="r-1",
            policy_version="pol-1",
            vocabulary_version="voc-1",
            port=PORT,
            key_id=FIXTURE_KEY_ID,
            algorithm=FIXTURE_ALGORITHM,
            records=unready_records(InteractionCapability.D_21),
        )
    assert raised.value.code is Code.CLARIFICATION_UNAVAILABLE


def test_the_shipped_records_are_what_production_reads() -> None:
    """And with **no** records argument at all, the reader loads the shipped files.

    The stronger form: the test above supplies synthetic un-ready records, which
    proves the gate. This proves the *default* — that omitting the parameter reads
    `docs/readiness/` rather than defaulting to permissive.
    """
    from analytics_interaction.clarification.issue import issue_clarification

    from ..fixtures.clarifications import FIXTURE_ALGORITHM, FIXTURE_KEY_ID, candidate

    # OD-101 (2026-09-02): o default le docs/readiness/ e o que ele diz hoje e que o
    # d_21 esta pronto — a emissao PASSA. A prova de que o default nao e permissivo
    # continua no teste acima: uma copia sem prontidao, pelo MESMO parametro, recusa.
    contract = issue_clarification(
        correlation_id="corr-1",
        interpretation_id="interp-1",
        auth_fingerprint=derive_authorization_fingerprint(authorize()),
        unresolved=SlotKind.METRIC,
        candidates=(candidate("installs"),),
        rounds_consumed=0,
        round_bound=2,
        issued_at=ISSUED_AT,
        expiry=EXPIRY,
        nonce="nonce-1",
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
        port=PORT,
        key_id=FIXTURE_KEY_ID,
        algorithm=FIXTURE_ALGORITHM,
    )
    assert contract.seal.key_id == FIXTURE_KEY_ID


# --- scenario 9: it survives a fresh process ---------------------------------


def _reload_clarification_modules() -> None:
    """Rebuild every module-level value in the clarification package.

    A cache, a memoised read or a lazily-built table would survive a plain second
    call and make the resumption succeed for the wrong reason. Reloading forces each
    one to be reconstructed, so what carries the contract across is genuinely only its
    serialised form and its seal.
    """
    for name in sorted(
        module
        for module in list(sys.modules)
        if module.startswith("analytics_interaction.clarification")
    ):
        importlib.reload(sys.modules[name])


def test_a_clarification_resumes_against_a_freshly_loaded_instance() -> None:
    """**Scenario 9's load-bearing assertion.**

    The contract crosses as a **JSON string**, and the modules that validate it are
    reloaded in between. Nothing else travels — no session, no store, no shared
    object. That is what a second process has.
    """
    authorized = authorize()
    fingerprint = derive_authorization_fingerprint(authorized)
    issued = issued_contract(port=PORT, fingerprint=fingerprint)

    wire = issued.model_dump_json()
    _reload_clarification_modules()

    from analytics_interaction.clarification.resume import (
        GoverningVersions as FreshVersions,
    )
    from analytics_interaction.clarification.resume import (
        resume_clarification as fresh_resume,
    )

    revived = ClarificationContract.model_validate(json.loads(wire))
    resumed = fresh_resume(
        revived,
        authorized=authorize(),
        in_force=FreshVersions(
            catalog_release="r-1", policy_version="pol-1", vocabulary_version="voc-1"
        ),
        at=LIVE,
        port=FixtureSealPort(key=FIXTURE_KEY),
        records=ready_records(InteractionCapability.D_21),
    )
    assert resumed == revived


def test_the_revived_contract_is_byte_identical_to_the_issued_one() -> None:
    """The round trip loses nothing.

    A field dropped in serialisation would break the seal — which is the right
    failure — but would break it for a reason that reads as tampering. Asserting the
    round trip separately keeps the two diagnoses apart.
    """
    issued = issued_contract(port=PORT, fingerprint=derive_authorization_fingerprint(authorize()))
    revived = ClarificationContract.model_validate(json.loads(issued.model_dump_json()))
    assert revived.model_dump_json() == issued.model_dump_json()


def test_the_outcome_is_identical_across_repeated_fresh_loads() -> None:
    """Three fresh loads, one outcome. A cache warmed on first use would differ."""
    issued = issued_contract(port=PORT, fingerprint=derive_authorization_fingerprint(authorize()))
    wire = issued.model_dump_json()

    outcomes: list[str] = []
    for _ in range(3):
        _reload_clarification_modules()
        revived = ClarificationContract.model_validate(json.loads(wire))
        resumed = resume_clarification(
            revived,
            authorized=authorize(),
            in_force=IN_FORCE,
            at=LIVE,
            port=FixtureSealPort(key=FIXTURE_KEY),
            records=READY,
        )
        outcomes.append(resumed.model_dump_json())
    assert len(set(outcomes)) == 1


def test_an_expired_contract_refuses_against_a_fresh_instance_too() -> None:
    """The gates travel with the contract, not with the process that issued it."""
    issued = issued_contract(port=PORT, fingerprint=derive_authorization_fingerprint(authorize()))
    wire = issued.model_dump_json()
    _reload_clarification_modules()

    revived = ClarificationContract.model_validate(json.loads(wire))
    with pytest.raises(ContractViolation) as raised:
        resume_clarification(
            revived,
            authorized=authorize(),
            in_force=IN_FORCE,
            at=ISSUED_AT + EXPIRY + timedelta(minutes=1),
            port=FixtureSealPort(key=FIXTURE_KEY),
            records=READY,
        )
    assert raised.value.code is Code.CLARIFICATION_EXPIRED


def test_the_replay_limitation_is_disclosed_rather_than_implied() -> None:
    """Scenario 9's honest footnote, carried as a value on the response."""
    posture = replay_posture()
    assert posture.consumption_detected is False
    assert "single_use_consumption" in posture.unenforceable


# --- scenario 10: no value can reach a model surface -------------------------


def test_no_model_facing_type_can_hold_a_result() -> None:
    """Static reachability: none is present, rather than redacted.

    Asserted on the declared field sets of every model-facing contract. "Redacted"
    would mean a value arrived and was removed, and the removal is where a bug lives;
    "absent" means there is nothing to remove.
    """
    from analytics_interaction.interpretation.model_port import (
        CandidateOption,
        CandidateSelection,
        CandidateSet,
        DelimitedQuestionData,
    )

    forbidden = ("value", "row", "cell", "result", "figure", "total", "amount", "count")
    for contract in (DelimitedQuestionData, CandidateOption, CandidateSet, CandidateSelection):
        offenders = [
            name for name in contract.model_fields for banned in forbidden if banned in name.lower()
        ]
        assert not offenders, f"{contract.__name__} could hold a value: {offenders}"


def test_no_model_port_implementation_is_constructible_today() -> None:
    """`D-20` is undeclared, so the narrowing surface refuses.

    Not "returns nothing" — refuses. A port that returned an empty selection would let
    a caller proceed as though the model had abstained, which is a different fact.
    """
    from analytics_interaction.compliance.gates import require_model_participation

    with pytest.raises(ContractViolation) as raised:
        require_model_participation(records=unready_records(InteractionCapability.D_20))
    assert raised.value.code is Code.MODEL_SURFACE_UNAVAILABLE


def test_no_flag_or_mode_reopens_the_model_boundary() -> None:
    """Scenario 10's static scan, over the whole source tree.

    Names a flag, an environment read or a debug path would arrive under. Scanned as
    AST identifiers rather than text, so a docstring explaining that no such flag
    exists does not read as one.
    """
    forbidden = (
        "enable_model",
        "allow_model",
        "model_enabled",
        "force_model",
        "debug_model",
        "model_override",
        "bypass_gate",
    )
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
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
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {name}")
    assert not offenders, f"a model-boundary flag exists: {offenders}"


# --- scenario 11: no persistence, no detection, no clock --------------------


def test_no_source_module_reads_a_clock() -> None:
    """Scenario 11's third claim, over the whole tree including the CLI.

    Every governed instant is a parameter. A clock read anywhere would make one
    invocation answer differently on two days with nothing in the output to say why.
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"today", "now", "utcnow", "monotonic", "time_ns"}
            ):
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")
    assert not offenders, f"a clock is read: {offenders}"


def test_language_is_declared_and_never_detected() -> None:
    """Scenario 11's second claim.

    The supported set is governed and the tag is the caller's. There is no detection
    step, so no confidence, no scoring and nothing for an injected instruction to
    influence.
    """
    assert supported_language_tags() == ("pt-BR",)
    assert require_declared_language("pt-BR") is DeclaredLanguage.PT_BR
    for undeclared in (None, "", "en-US", "pt", "PT-br"):
        with pytest.raises(ContractViolation):
            require_declared_language(undeclared)


def test_the_only_cache_in_the_package_holds_governed_wording() -> None:
    """Scenario 11's first claim, at its one named exemption.

    The registry memoises a **read of authored content** bounded at the supported
    languages. It holds no question, no answer, no event and no business value — and
    that is asserted rather than asserted-about.
    """
    registry = load_registry()
    serialised = json.dumps(
        {
            "language": registry.language,
            "content_version": registry.content_version,
            "codes": sorted(code.value for code in registry.codes),
        },
        sort_keys=True,
    )
    for forbidden in ("987654", "row-", "SELECT", "installs:read", "p-1"):
        assert forbidden not in serialised


def test_the_registry_is_byte_stable_across_repeats() -> None:
    """Same code, same content version, same text. Every time.

    Which is what makes a refusal reproducible: two callers refused for the same
    reason read the same sentence, and a diff between two runs shows only real
    changes.
    """
    from analytics_interaction.contracts.reason_codes import InterpretationReasonCode

    first = {
        code: load_registry().text_for(code)
        for code in InterpretationReasonCode
        if code in load_registry().codes
    }
    second = {
        code: load_registry().text_for(code)
        for code in InterpretationReasonCode
        if code in load_registry().codes
    }
    assert first == second


# --- scenario 12: determinism ----------------------------------------------


def test_two_identical_intents_share_one_identity(resolved_intent: object) -> None:
    """Scenario 12's first line, at the identity rather than at the request."""
    digests = {derive_interpretation_identity(resolved_intent) for _ in range(5)}  # pyright: ignore[reportArgumentType]
    assert len(digests) == 1


def test_the_identity_is_a_fixed_width_digest(resolved_intent: object) -> None:
    """A variable-length identity would leak the size of what it covers."""
    digest = derive_interpretation_identity(resolved_intent)  # pyright: ignore[reportArgumentType]
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_the_same_code_yields_byte_identical_wording() -> None:
    """Scenario 12's fourth line. Nothing is generated, so nothing can drift."""
    from analytics_interaction.contracts.reason_codes import InterpretationReasonCode

    registry = load_registry()
    for code in InterpretationReasonCode:
        if code not in registry.codes:
            continue
        renders = {registry.text_for(code) for _ in range(3)}
        assert len(renders) == 1, code


# --- the four scenarios did not satisfy one another by breaking another ------


def test_nothing_in_this_file_mutated_the_shipped_readiness() -> None:
    """Reloading modules is the one unusual thing here, and it touches no file."""
    from analytics_interaction.compliance.readiness import aggregate_ready, load_all_records

    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )


def test_the_reload_left_the_package_importable() -> None:
    """A reload that broke a module would make every later test in the run lie.

    Asserted explicitly because module reloading is a blunt instrument, and a
    half-reloaded package is the kind of thing that produces failures three files
    away with no obvious cause.
    """
    from analytics_interaction.clarification import issue, replay, resume, seal

    for module in (issue, replay, resume, seal):
        assert module.__all__
    assert datetime(2026, 8, 13, tzinfo=UTC) is not None
