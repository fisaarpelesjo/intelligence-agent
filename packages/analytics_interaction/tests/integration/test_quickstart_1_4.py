"""Quickstart scenarios 1—4 — T162 (FR-057, FR-058; SC-031).

    Evidence: each lock removed in turn while the other four hold.
    — `tasks.md` T162

Four scenarios from `quickstart.md`, run as one file because they share one premise:
**nothing works today, and each reason is independent of the others.**

| Scenario | Claim |
|---|---|
| 1 | Five locks, and removing any one leaves four |
| 2 | An unauthorized principal costs zero calls, measured |
| 3 | A question is data, and a refused question costs nothing |
| 4 | Inaccessible and nonexistent are byte-identical |

## Why "each lock removed in turn" is the whole scenario

If two locks fall together, they were one lock wearing two names — and one upstream
approval would open both without anyone noticing. That is not a hypothetical: `D-18`
and `D-19` are both "interpretation content", and a single gate keyed on "governed
content present" would have satisfied every fail-closed test written so far while
collapsing two independent approvals into one.

So each of the four capabilities is unlocked **alone**, against synthetic readiness,
and the remaining three are asserted still closed. The unlocking is fixture-only and
says nothing about the real records, which remain open.

## The cross-artifact CLI documentation check

Also here, because scenario 1's own instructions are shell commands and a scenario
runner that cannot run its own documented commands is not a runner. Every command
`quickstart.md` documents is parsed and checked against the **real** parser: the
subcommand must exist, the options must exist, the required arguments must be
present, and no command may rely on a clock default. Nothing is executed against a
warehouse or a network to establish this — the parser answers structurally.
"""

from __future__ import annotations

import argparse
import inspect
import re
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.cli.main import EXIT_INVOCATION, EXIT_OK, EXIT_VIOLATION, build_parser
from analytics_interaction.compliance.gates import (
    CAPABILITY_FAIL_CLOSED,
    SURFACE_CAPABILITY,
    CapabilitySurface,
    InteractionCapability,
    available_capabilities,
    is_capability_available,
    is_surface_available,
    require_surface,
)
from analytics_interaction.compliance.readiness import (
    Capability,
    ReadinessRecord,
    aggregate_ready,
    load_all_records,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.intent import SlotKind, TermRef
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.intake.parse import parse_intake
from analytics_interaction.intake.screening import screen_question
from analytics_interaction.interpretation.resolve_terms import TermRequest, resolve_term

from ..adversarial.test_disclosure_symmetry import CATALOG, INACCESSIBLE, NONEXISTENT
from ..adversarial.test_injection import PAYLOADS
from ..conftest import ON, REFERENCE, SUPPLIED_PRINCIPAL, authorize
from ..fixtures.clarifications import unready_records
from ..fixtures.counters import SURFACES, Surfaces

pytestmark = pytest.mark.integration

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
REPO = SRC.parents[3]
QUICKSTART = REPO / "specs" / "003-nl-analytics-interaction" / "quickstart.md"

CAPABILITIES: tuple[InteractionCapability, ...] = tuple(InteractionCapability)


def _record_with_only(ready: InteractionCapability) -> tuple[ReadinessRecord, ...]:
    """One **complete** record: every capability present, exactly one ready.

    Completeness matters and is not incidental. A record naming only the capability
    under test makes ``is_capability_available`` raise ``UnknownCapability`` for the
    other three — correctly, because a record that omits a capability is malformed
    rather than a record saying "unavailable". A fixture built that way would report
    the other locks as *errors* instead of as closed, and the scenario would be
    asserting the wrong thing.
    """
    return (
        ReadinessRecord(
            feature="003-nl-analytics-interaction",
            source="fixture-only-not-provisioned",
            capabilities={
                capability.value: Capability(
                    identifier=capability.value,
                    declared=capability is ready,
                    evidence_ref=(
                        "fixture-only-not-provisioned-evidence" if capability is ready else None
                    ),
                    owner_role="fixture",
                )
                for capability in CAPABILITIES
            },
        ),
    )


def _record_declared_without_evidence() -> tuple[ReadinessRecord, ...]:
    """Every capability flagged, none evidenced. A flag with nothing behind it."""
    return (
        ReadinessRecord(
            feature="003-nl-analytics-interaction",
            source="fixture-only-not-provisioned",
            capabilities={
                capability.value: Capability(
                    identifier=capability.value,
                    declared=True,
                    evidence_ref=None,
                    owner_role="fixture",
                )
                for capability in CAPABILITIES
            },
        ),
    )


# --- scenario 1: five locks -----------------------------------------------------


def test_the_shipped_state_has_every_lock_closed() -> None:
    """**The premise.** Nothing is ready, so nothing is available.

    Read through the package's own reader against the shipped records, not against
    a fixture. This is the one assertion in the file that describes production.
    """
    records = load_all_records()
    assert aggregate_ready(records) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )  # +OD-106
    # OD-101/OD-104 (2026-09-02): d_21 e d_18 abertos pelo dono; d_19/d_20 fechados.
    assert available_capabilities(records=records) == frozenset({"d_18", "d_21"})
    for capability in CAPABILITIES:
        assert is_capability_available(capability, records=records) == (
            capability in (InteractionCapability.D_18, InteractionCapability.D_21)
        )


@pytest.mark.parametrize("unlocked", CAPABILITIES, ids=[c.value for c in CAPABILITIES])
def test_removing_one_lock_leaves_the_others_closed(unlocked: InteractionCapability) -> None:
    """**The load-bearing scenario.** Four unlockings, each alone.

    If two capabilities became available from one synthetic record, they were one
    gate wearing two names — and one real approval would open both. `D-18` and
    `D-19` are the pair most at risk, because both are "interpretation content".
    """
    records = _record_with_only(unlocked)
    assert available_capabilities(records=records) == frozenset({unlocked.value})
    for other in CAPABILITIES:
        if other is unlocked:
            assert is_capability_available(other, records=records)
        else:
            assert not is_capability_available(other, records=records), (
                f"unlocking {unlocked.value} also unlocked {other.value}"
            )


@pytest.mark.parametrize("unlocked", CAPABILITIES, ids=[c.value for c in CAPABILITIES])
def test_only_that_capabilitys_surfaces_open(unlocked: InteractionCapability) -> None:
    """Per-surface, not per-capability.

    Eleven surfaces across four capabilities. A gate that opened every surface when
    any capability arrived would pass the test above and fail here.
    """
    records = _record_with_only(unlocked)
    for surface in CapabilitySurface:
        expected = SURFACE_CAPABILITY[surface] is unlocked
        assert is_surface_available(surface, records=records) is expected, surface.value


@pytest.mark.parametrize("capability", CAPABILITIES, ids=[c.value for c in CAPABILITIES])
def test_each_closed_lock_refuses_with_its_own_code(
    capability: InteractionCapability,
) -> None:
    """Four capabilities, four distinct codes.

    A shared code would make the four locks indistinguishable to a caller, which is
    the same collapse as a shared gate — arriving through the message instead of
    through the logic.
    """
    surface = next(s for s, c in SURFACE_CAPABILITY.items() if c is capability)
    with pytest.raises(ContractViolation) as raised:
        require_surface(surface, records=unready_records(capability))
    assert raised.value.code is CAPABILITY_FAIL_CLOSED[capability]


def test_the_four_fail_closed_codes_are_four() -> None:
    """Stated once, so a collapse is visible in one place."""
    assert len(set(CAPABILITY_FAIL_CLOSED.values())) == 4
    assert set(CAPABILITY_FAIL_CLOSED) == set(CAPABILITIES)


def test_declared_without_evidence_unlocks_exactly_nothing() -> None:
    """A flag with nothing behind it must unlock as much as no flag: nothing.

    The tempting failure is treating ``declared`` as sufficient — which would let a
    record edited in advance of its evidence open a capability, and the readiness
    file would look like the approval.
    """
    records = _record_declared_without_evidence()
    assert available_capabilities(records=records) == frozenset()
    for capability in CAPABILITIES:
        assert not is_capability_available(capability, records=records)


# --- scenario 2: an unauthorized principal costs nothing -----------------------


def test_an_unresolvable_principal_reaches_no_surface() -> None:
    """Counted, not inspected. Six surfaces, all zero.

    `002`'s zero-cost precedent: the claim is about calls that did not happen, and
    the only way to assert that is to count what would have been.
    """
    from analytics_interaction.authorization.context_preflight import (
        resolve_authorization_context,
    )
    from analytics_interaction.authorization.refusal import AuthorizationRefused

    surfaces = Surfaces()
    with pytest.raises(AuthorizationRefused):
        resolve_authorization_context(SUPPLIED_PRINCIPAL, resolver=None)
    assert surfaces.counts() == dict.fromkeys(SURFACES, 0), surfaces.touched()


def test_the_contrast_case_proves_the_sequence_is_real() -> None:
    """An **authorized** principal refuses one stage later.

    Same outcome, different stage — which is what shows the zero above is a property
    of the ordering rather than of everything refusing everywhere. Without this, the
    zero-call assertion would pass against a system that did nothing at all.
    """
    authorized = authorize()
    assert authorized is not None

    with pytest.raises(ContractViolation) as raised:
        screen_question("installs de julho", policy=None, matcher=None)
    assert raised.value.code is Code.INTERPRETATION_POLICY_UNRESOLVABLE


def test_no_governed_limit_appears_in_an_authorization_refusal() -> None:
    """The refusal describes nothing about the identity system or the policy."""
    from analytics_interaction.authorization.refusal import authorization_refusal

    message = str(authorization_refusal())
    for leaked in ("p-1", "tenant-a", "authpol-1", "installs:read", "bytes", "threshold"):
        assert leaked not in message


# --- scenario 3: a question is data ------------------------------------------


@pytest.mark.parametrize("payload", PAYLOADS[:6], ids=lambda p: p[:24])
def test_an_injected_question_refuses_at_zero_cost(payload: str) -> None:
    """Scenario 3, through the shipped path.

    A subset of `T149`'s corpus, run here as the *scenario* rather than as the unit:
    what this adds is the surface count alongside the refusal, in the same test.
    """
    surfaces = Surfaces()
    intake = parse_intake(
        {
            "text": payload,
            "language": DeclaredLanguage.PT_BR,
            "reference_date": REFERENCE,
            "principal": SUPPLIED_PRINCIPAL,
        }
    )
    assert intake.text == payload

    with pytest.raises(ContractViolation) as raised:
        screen_question(intake.text, policy=None, matcher=None)
    assert raised.value.code is Code.INTERPRETATION_POLICY_UNRESOLVABLE
    assert surfaces.counts() == dict.fromkeys(SURFACES, 0)
    assert payload not in str(raised.value)


# --- scenario 4: disclosure symmetry ----------------------------------------


@pytest.mark.parametrize("slot", list(SlotKind), ids=[s.value for s in SlotKind])
def test_inaccessible_and_nonexistent_are_byte_identical(slot: SlotKind) -> None:
    """Scenario 4, over the whole slot matrix.

    Reuses `T151`'s access-filtered catalog rather than building a second one: two
    fixtures modelling the same upstream behaviour would eventually disagree, and the
    one that drifted would be the one asserting the symmetry.
    """

    def refusal(surface: str) -> str:
        with pytest.raises(ContractViolation) as raised:
            resolve_term(
                TermRequest(term=TermRef(start=0, length=len(surface)), slot=slot),
                surface,
                catalog=CATALOG,
                authorized=authorize(),
                on=ON,
            )
        return f"{raised.value.code.value}|{raised.value}"

    assert refusal(INACCESSIBLE) == refusal(NONEXISTENT)


# --- the cross-artifact CLI documentation check -----------------------------


#: A documented command line, as quickstart writes it.
COMMAND_PATTERN = re.compile(r"^python -m analytics_interaction\.cli (?P<args>.+?)\s*(?:#.*)?$")

#: Quickstart documents one command **deliberately incomplete**, to show that
#: omitting ``--on`` is a usage error. It is marked in the document rather than
#: guessed at here: a checker that inferred which examples were meant to fail would
#: eventually infer wrongly, and the example it excused would be a real drift.
COUNTER_EXAMPLE = "# intentionally incomplete"


def _documented_commands() -> list[list[str]]:
    """Every CLI invocation `quickstart.md` documents, parsed out of its fences.

    Parsed from the document rather than listed here, which is the point: a hand-kept
    list drifts from the document silently, and the drift is invisible precisely
    because both look maintained.
    """
    found: list[list[str]] = []
    for line in QUICKSTART.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if COUNTER_EXAMPLE in stripped:
            continue
        match = COMMAND_PATTERN.match(stripped)
        if match:
            found.append(match.group("args").split())
    return found


def _counter_examples() -> list[list[str]]:
    """The commands quickstart documents as *failing*, so they are checked too.

    A counter-example that stopped being a counter-example — because a default came
    back — would otherwise be excluded from every check in this file, which is the
    one place it most needs to be checked.
    """
    found: list[list[str]] = []
    for line in QUICKSTART.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if COUNTER_EXAMPLE not in stripped:
            continue
        match = COMMAND_PATTERN.match(stripped)
        if match:
            found.append(match.group("args").split())
    return found


def test_quickstart_documents_at_least_the_five_commands() -> None:
    """A scan that found nothing would pass every assertion below."""
    commands = _documented_commands()
    assert len(commands) >= 5, commands
    documented = {parts[0] for parts in commands}
    assert documented == {"vocabulary", "policy", "explain-intent", "messages", "schema"}


@pytest.mark.parametrize("argv", _documented_commands(), ids=lambda a: " ".join(a))
def test_every_documented_command_parses_against_the_real_parser(argv: list[str]) -> None:
    """**The cross-artifact check.** Structural, and no execution.

    ``parse_args`` answers whether the subcommand exists, whether the options exist
    and whether the required arguments are present — without touching a warehouse, a
    provider or a network. A documented command that no longer parses is documentation
    that will fail for the next person who copies it.

    ``explain-intent`` is checked with a path that need not exist: whether the file
    is readable is a runtime question, and this is a parser question.
    """
    parser = build_parser()
    try:
        namespace = parser.parse_args(argv)
    except SystemExit as exit_code:  # pragma: no cover - a documented command must parse
        pytest.fail(f"quickstart documents a command the parser rejects: {argv} ({exit_code})")
    assert getattr(namespace, "handler", None) is not None, argv


@pytest.mark.parametrize(
    "argv",
    [parts for parts in _documented_commands() if parts[0] in {"vocabulary", "policy"}],
    ids=lambda a: " ".join(a),
)
def test_every_dated_command_declares_its_date_explicitly(argv: list[str]) -> None:
    """**No documented command relies on a clock default.**

    `FR-099` bans a defaulted instant. A quickstart example without ``--on`` would
    either fail to parse — which the check above catches — or, if a default were
    reintroduced, silently document a command whose answer changes by the day.
    Asserted on the documented text so the documentation cannot drift back.
    """
    assert "--on" in argv, f"a dated command is documented without --on: {argv}"
    index = argv.index("--on")
    assert index + 1 < len(argv), f"--on is documented without a date: {argv}"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", argv[index + 1]), argv


def test_the_documented_counter_example_really_fails() -> None:
    """Quickstart documents omitting ``--on`` as a usage error. It is one.

    Run through ``main`` rather than through the parser, because the documented claim
    is about the **exit code** a caller sees: 2, not a governed 1. Reporting a
    governed outcome would claim the content had been inspected when the command
    never ran.
    """
    from analytics_interaction.cli.main import main

    examples = _counter_examples()
    assert examples, "quickstart no longer documents the usage error"
    for argv in examples:
        assert "--on" not in argv, f"a counter-example that succeeds is not one: {argv}"
        assert main(argv) == EXIT_INVOCATION, argv


def test_the_documented_exit_codes_are_the_three_the_cli_declares() -> None:
    """0, 1, 2 — and quickstart's table says so.

    Parsed out of the document, so a table edited to say something else fails here
    rather than misleading somebody scripting against it.
    """
    text = QUICKSTART.read_text(encoding="utf-8")
    assert (EXIT_OK, EXIT_VIOLATION, EXIT_INVOCATION) == (0, 1, 2)
    assert "Governed refusal" in text
    assert "Malformed or incomplete invocation" in text
    for code in ("`0`", "`1`", "`2`"):
        assert code in text, code


def test_every_documented_option_exists_on_its_own_subcommand() -> None:
    """Options live on subparsers, so the root help is the wrong place to look.

    Checked by parsing the command and confirming the option's destination is set,
    which is what "the option exists" actually means — a substring search against
    help text would pass for an option mentioned in a description and fail for one
    that exists but is undocumented.
    """
    parser = build_parser()
    for argv in _documented_commands():
        namespace = parser.parse_args(argv)
        for token in argv:
            if token.startswith("--"):
                dest = token.removeprefix("--").replace("-", "_")
                assert hasattr(namespace, dest), f"{token} is not an option of {argv[0]}"


def test_no_documented_command_names_a_provider_or_a_credential() -> None:
    """The documentation cannot invite an argument the parser refuses to have."""
    documented = " ".join(" ".join(argv) for argv in _documented_commands() + _counter_examples())
    for forbidden in ("--provider", "--model", "--key", "--fixture", "--readiness", "--sink"):
        assert forbidden not in documented


def test_the_parser_check_does_not_execute_anything() -> None:
    """Stated as a property of the check itself.

    ``parse_args`` returns a namespace carrying a handler; nothing calls it. A check
    that invoked the handler to "verify the command works" would run governed content
    resolution for every documented example, which is a different test and a slower
    one.
    """
    parser = build_parser()
    namespace = parser.parse_args(["messages"])
    assert isinstance(namespace, argparse.Namespace)
    assert callable(namespace.handler)


# --- the scenario file mutates nothing --------------------------------------


def test_no_scenario_mutated_the_shipped_readiness() -> None:
    """Run last in the file by name, and asserted rather than assumed.

    Every unlocking above passed synthetic records through a parameter. If one had
    written to the shipped files instead, this is where it would show — and a fixture
    that mutated production governance is the single worst thing a scenario runner
    could do.
    """
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )
    assert available_capabilities() == frozenset({"d_18", "d_21"})  # +OD-104
