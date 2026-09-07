"""A clarification costs nothing downstream — T115 (FR-016; SC-014).

    Evidence: counted zero governed requests and zero execution-port calls.
    — `tasks.md` T115

This is what makes asking better than guessing. A clarification constructs no
``AnalyticsQuery`` and reaches no warehouse, so surfacing an ambiguity costs
interpretation only — while guessing costs a confident wrong answer the reader
cannot detect.

**Counted, not inspected.** A source scan shows the clarification modules do not
import the request builder or the execution port; it cannot show that some other
path reached one at runtime. `FR-089` is explicit that the zero-call property is
measured by call count against each surface.

The suite also covers the `D-21` gate, which is the state the repository actually
ships in: with sealing unavailable, **no contract is issued at all**, and the
seal port is never touched either. Both refusals are asserted against a counting
port so "refused before the provider" is a count rather than a claim.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from analytics_interaction.clarification.issue import issue_clarification
from analytics_interaction.clarification.seal import issue_seal, verify_seal
from analytics_interaction.compliance.gates import InteractionCapability
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intent import SlotKind
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code

from ..fixtures.clarifications import (
    FIXTURE_ALGORITHM,
    FIXTURE_KEY,
    FIXTURE_KEY_ID,
    CountingSealPort,
    FixtureSealPort,
    candidate,
    issued_contract,
    ready_records,
    unready_records,
)
from ..fixtures.counters import Surfaces

pytestmark = pytest.mark.integration

ISSUED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
CANDIDATES = (candidate("installs"), candidate("sessions"))


def _issue(*, port: object, records: object) -> object:
    return issue_clarification(
        correlation_id="corr-1",
        interpretation_id="interp-1",
        auth_fingerprint="fp-1",
        unresolved=SlotKind.METRIC,
        candidates=CANDIDATES,
        rounds_consumed=0,
        round_bound=2,
        issued_at=ISSUED_AT,
        expiry=timedelta(minutes=15),
        nonce="nonce-1",
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
        port=port,  # pyright: ignore[reportArgumentType]
        key_id=FIXTURE_KEY_ID,
        algorithm=FIXTURE_ALGORITHM,
        records=records,  # pyright: ignore[reportArgumentType]
    )


# --- the shipped state: D-21 undeclared -------------------------------------------


def test_the_shipped_readiness_refuses_issuance_with_zero_seal_calls() -> None:
    """**The state the repository ships in.** No contract, no provider call.

    ``records=None`` reads the real files, so this is the production answer
    rather than a fixture's.
    """
    port = CountingSealPort()

    # OD-101 (2026-09-02): o estado embarcado passou a ALCANCAR o porto injetado — o
    # AssertionError do porto-contador e a prova do alcance, e a contagem e UM. A recusa
    # sem porto nenhum segue dirigida em test_a_missing_provider_refuses_....
    with pytest.raises(AssertionError):
        _issue(port=port, records=None)

    assert port.calls == 1


def test_declared_without_evidence_also_produces_zero_calls() -> None:
    """A flag with nothing behind it unlocks exactly as much as no flag: nothing."""
    port = CountingSealPort()

    with pytest.raises(ContractViolation) as refusal:
        _issue(port=port, records=unready_records(InteractionCapability.D_21, declared=True))

    assert refusal.value.code is Code.CLARIFICATION_UNAVAILABLE
    assert port.calls == 0


def test_verification_is_gated_too_with_zero_calls() -> None:
    """A build where sealing is unavailable cannot verify a contract either.

    Correct rather than inconvenient: it cannot establish that the key is still
    the governed one.
    """
    contract = issued_contract(fingerprint="fp-1")
    port = CountingSealPort()

    # OD-101 (2026-09-02): a verificacao tambem alcanca o porto no estado embarcado (um
    # call); numa copia SEM prontidao ela continua recusando com ZERO calls.
    with pytest.raises(AssertionError):
        verify_seal(contract, port=port, records=None)
    assert port.calls == 1

    gated = CountingSealPort()
    with pytest.raises(ContractViolation) as refusal:
        verify_seal(contract, port=gated, records=unready_records(InteractionCapability.D_21))
    assert refusal.value.code is Code.CLARIFICATION_UNAVAILABLE
    assert gated.calls == 0


def test_a_missing_provider_refuses_rather_than_sealing_with_nothing() -> None:
    """Absence is a refusal, never a bypass."""
    contract = issued_contract(fingerprint="fp-1")

    with pytest.raises(ContractViolation) as refusal:
        issue_seal(
            contract,
            port=None,
            key_id=FIXTURE_KEY_ID,
            algorithm=FIXTURE_ALGORITHM,
            records=ready_records(InteractionCapability.D_21),
        )

    assert refusal.value.code is Code.CLARIFICATION_UNAVAILABLE


# --- and with sealing available, still nothing downstream --------------------------


def test_a_successful_issuance_touches_no_governed_request_or_warehouse() -> None:
    """`FR-016`, counted across all six cost surfaces.

    A clarification is interpretation work. It builds no request and submits
    nothing — which is exactly why asking is cheaper than guessing.
    """
    surfaces = Surfaces()

    contract = _issue(
        port=FixtureSealPort(key=FIXTURE_KEY),
        records=ready_records(InteractionCapability.D_21),
    )

    assert contract is not None
    assert surfaces.counts()["execution"] == 0
    assert surfaces.counts()["catalog"] == 0
    assert surfaces.counts()["model"] == 0
    assert surfaces.all_zero()


def test_issuance_reaches_the_provider_exactly_once() -> None:
    """One seal per contract. A second call would be a second sealing.

    Counted because the draft is sealed and then rebuilt with the real seal — an
    implementation that sealed the rebuilt contract too would double the calls
    and produce a value covering a different object.
    """
    calls: list[str] = []

    class Recording(FixtureSealPort):
        def seal(self, preimage: str, *, key_id: str):
            calls.append(preimage)
            return super().seal(preimage, key_id=key_id)

    _issue(port=Recording(key=FIXTURE_KEY), records=ready_records(InteractionCapability.D_21))

    assert len(calls) == 1


def test_the_clarification_modules_import_no_request_builder_or_port() -> None:
    """The static half. Neither claim is sufficient alone.

    The count proves nothing was reached this time; the import ban proves there
    is no path to reach.
    """
    import ast
    import inspect
    from pathlib import Path

    from analytics_interaction import clarification

    root = Path(inspect.getfile(clarification)).resolve().parent
    forbidden = {
        "analytics_interaction.contracts.request_build",
        "analytics_interaction.execution.port",
        "analytics_query.execute",
    }
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in forbidden:
                offenders.append(f"{path.name}:{node.lineno} {node.module}")
            elif isinstance(node, ast.Import):
                offenders += [
                    f"{path.name}:{node.lineno} {alias.name}"
                    for alias in node.names
                    if alias.name in forbidden
                ]
    assert not offenders, f"a clarification module reaches execution: {offenders}"


def test_a_clarification_constructs_no_analytics_query() -> None:
    """Nowhere in the clarification package is a governed request built."""
    import ast
    import inspect
    from pathlib import Path

    from analytics_interaction import clarification

    root = Path(inspect.getfile(clarification)).resolve().parent
    constructed = {
        node.func.id
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "AnalyticsQuery" not in constructed
    assert "build_analytics_query" not in constructed
