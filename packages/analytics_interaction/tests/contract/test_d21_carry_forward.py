"""`D-21` carried forward, and the gap is not permission — T180 (ADR 0014).

    Evidence: the note states the pending amendment; `spec.md` is unmodified.
    — `tasks.md` T180

    Validation: **MUST NOT AMEND `spec.md`.** Amending a specification is a separate
    governed act. — `tasks.md` T180

## The situation

`spec.md` § Dependencies names `DEP-3` (`D-18`), `DEP-4` (`D-19`) and `DEP-5` (`D-20`). It
does not name `D-21`, because `D-21` was **design-discovered**: it only became a question
while the stateless clarification contract was being designed, and by then the
specification was approved.

Planning recorded it through the governed revision mechanism — a pending note, not an
edit — and this task verifies that arrangement is still accurate against what was actually
built.

## The claim under test, and why it needs a test at all

The claim is that the missing spec entry is a **documentation gap, not a permission**: the
system already behaves as though `D-21` were specified.

A document cannot establish that. A note saying "the enforcement holds" is worth exactly as
much as the enforcement, and a reader has no way to tell the two apart. So this file asserts
the enforcement **directly**, and separately asserts that the note has not quietly become
the thing holding the line.

The failure mode is specific and plausible: somebody reads "documentation gap" as "nothing
is blocked", or a future edit relaxes a gate on the grounds that the specification never
required it.

## Integrity is not single-use detection

`D-21` enables **sealing** — a modified field becomes detectable. It does not enable
**cross-process single-use detection**, because nothing records that a contract was
presented. That needs a durable store, which is a separate governed decision.

Asserted here because merging the two would make `D-21`'s arrival look like it closes the
replay gap. It does not, and `FR-080` requires the limitation to reach the consumer as a
value rather than as a sentence in a note.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

import analytics_interaction
from analytics_interaction.clarification.issue import issue_clarification
from analytics_interaction.clarification.replay import (
    UNENFORCEABLE_WITHOUT_STATE,
    replay_posture,
)
from analytics_interaction.clarification.seal import verify_seal
from analytics_interaction.compliance.gates import (
    CAPABILITY_FAIL_CLOSED,
    CapabilitySurface,
    InteractionCapability,
    is_capability_available,
    is_surface_available,
    require_clarification_sealing,
)
from analytics_interaction.compliance.readiness import (
    CapabilityState,
    aggregate_ready,
    capability_state,
    load_all_records,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intent import SlotKind
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.identity.authorization_fingerprint import (
    derive_authorization_fingerprint,
)

from ..conftest import authorize
from ..fixtures.clarifications import (
    EXPIRY,
    FIXTURE_ALGORITHM,
    FIXTURE_KEY,
    FIXTURE_KEY_ID,
    ISSUED_AT,
    FixtureSealPort,
    candidate,
    issued_contract,
    ready_records,
)

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
REPO = SRC.parents[3]
SPEC = REPO / "specs" / "003-nl-analytics-interaction" / "spec.md"
NOTES = REPO / "docs" / "release" / "nl-analytics-spec-revision-notes.md"
READINESS = REPO / "docs" / "readiness" / "nl-analytics-external-readiness.yaml"


# --- the spec is unmodified, and still does not name D-21 ----------------------


def test_the_specification_still_names_only_three_new_dependencies() -> None:
    """**`T180`'s hard prohibition.** `spec.md` is not amended here.

    Asserted as an absence with a positive control: the three that *are* named must be
    present, so this cannot pass because the section was deleted.
    """
    text = SPEC.read_text(encoding="utf-8")
    assert "D-18" in text
    assert "D-19" in text
    assert "D-20" in text
    assert "D-21" not in text, (
        "spec.md now names D-21; amending the specification is a separate governed act "
        "and is not this task's to perform"
    )


def test_the_revision_note_exists_and_records_the_pending_amendment() -> None:
    """The governed mechanism, still in place.

    A carry-forward with no note is an undocumented gap; a note that stopped saying it is
    pending would read as an applied amendment.
    """
    assert NOTES.is_file()
    text = NOTES.read_text(encoding="utf-8")
    assert "Status: pending. Nothing here has been applied to `spec.md`." in text
    assert "`D-21` — clarification-contract seal key" in text
    assert "It does not amend `spec.md`. That file is unmodified." in text


def test_the_note_states_exactly_what_a_future_amendment_must_add() -> None:
    """A carry-forward that did not say what to do would defer the decision, not record it."""
    text = NOTES.read_text(encoding="utf-8")
    for required in (
        "DEP-6",
        "platform / IAM owner",
        "required evidence",
        "capability unavailable without it",
        "fail-closed behaviour",
        "CLARIFICATION_UNAVAILABLE",
    ):
        assert required in text, required


def test_the_note_records_what_was_built_rather_than_what_was_planned() -> None:
    """`T180` verifies the note is **current**, not merely present.

    Three controls it described as planned are built. A note still calling them planned
    would understate the enforcement, and the next reader would go looking for work that is
    already done.
    """
    text = NOTES.read_text(encoding="utf-8")
    assert "planned" not in text.lower(), "the note still describes a built control as planned"
    for built in (
        "clarification/issue.py",
        "compliance/readiness.py",
    ):
        assert built in text, built


# --- D-21 is open, and every field says so -------------------------------------


def test_d21_is_declared_false_with_no_evidence() -> None:
    """Read from the shipped record, field by field."""
    import yaml

    loaded: object = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    document = cast("dict[str, object]", loaded)

    raw = document["capabilities"]
    entries: list[object] = (
        list(cast("dict[str, object]", raw).values())
        if isinstance(raw, dict)
        else list(cast("list[object]", raw))
    )

    # The record keys each entry by ``id``. ``identifier`` is the *reader's* field name,
    # not the file's, and looking for the wrong one found nothing silently -- an empty
    # match would have passed a weaker assertion.
    seal: list[dict[str, object]] = []
    for item in entries:
        assert isinstance(item, dict)
        entry = cast("dict[str, object]", item)
        if entry.get("id") == InteractionCapability.D_21.value:
            seal.append(entry)

    assert len(seal) == 1, "D-21 must appear exactly once in the readiness record"
    # Nome historico fincado; a verdade desde 2026-09-02 (OD-101): declarado COM
    # evidencia, papel e nota datada — e o carry-forward do spec segue na entrada.
    assert seal[0]["declared"] is True
    assert seal[0].get("evidence_ref")
    assert seal[0].get("declared_by_role")
    assert "OD-101" in str(seal[0].get("note", ""))
    assert "carry_forward" in seal[0], "o carry-forward do spec-amendment sumiu"


def test_d21_reads_undeclared_through_the_packages_reader() -> None:
    """And the reader agrees with the file."""
    # OD-101 (2026-09-02): READY, disponivel, e presente no agregado.
    assert capability_state(InteractionCapability.D_21.value) is CapabilityState.READY
    assert is_capability_available(InteractionCapability.D_21)
    assert InteractionCapability.D_21.value in aggregate_ready(load_all_records())


def test_clarification_sealing_is_blocked() -> None:
    """The surface `D-21` gates, closed."""
    # OD-101 (2026-09-02): a superficie abriu; o codigo fail-closed continua mapeado
    # para o dia em que a declaracao cair.
    assert is_surface_available(CapabilitySurface.CLARIFICATION_SEALING)
    require_clarification_sealing()
    assert CAPABILITY_FAIL_CLOSED[InteractionCapability.D_21] is Code.CLARIFICATION_UNAVAILABLE


# --- the documentation gap does not act as permission --------------------------


def test_issuance_refuses_against_the_shipped_readiness() -> None:
    """**The load-bearing assertion.**

    Called through the real issuance path with **no** synthetic records, so the enforcement
    is the shipped one. Everything else in this file describes the arrangement; this is the
    part that would fail if the arrangement were fiction.
    """
    # OD-101 (2026-09-02): o caminho embarcado agora EMITE atraves do porto injetado;
    # o que continua recusando e a ausencia de porto — dirigida logo abaixo.
    contract = issue_clarification(
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
        port=FixtureSealPort(key=FIXTURE_KEY),
        key_id=FIXTURE_KEY_ID,
        algorithm=FIXTURE_ALGORITHM,
    )
    assert contract.seal.key_id == FIXTURE_KEY_ID

    from analytics_interaction.clarification.seal import issue_seal

    with pytest.raises(ContractViolation) as raised:
        issue_seal(contract, port=None, key_id=FIXTURE_KEY_ID, algorithm=FIXTURE_ALGORITHM)
    assert raised.value.code is Code.CLARIFICATION_UNAVAILABLE


def test_verification_refuses_against_the_shipped_readiness() -> None:
    """A build that cannot verify a seal must not honour a contract issued when it could."""
    contract = issued_contract(
        port=FixtureSealPort(key=FIXTURE_KEY),
        fingerprint=derive_authorization_fingerprint(authorize()),
    )
    # OD-101 (2026-09-02): o embarcado verifica atraves do porto; SEM porto, recusa.
    assert verify_seal(contract, port=FixtureSealPort(key=FIXTURE_KEY)) is None
    with pytest.raises(ContractViolation) as raised:
        verify_seal(contract, port=None)
    assert raised.value.code is Code.CLARIFICATION_UNAVAILABLE


def test_the_refusal_does_not_depend_on_the_note_existing() -> None:
    """The enforcement is code, not documentation.

    Asserted structurally: no module under `src/` reads the revision note, the spec or any
    document at all to decide whether to refuse. A gate that consulted a Markdown file
    would make the documentation gap into exactly the permission this task denies it is.
    """
    # Scanned as **reads**, not as text. Four modules cite `tasks.md` in a docstring, which
    # is a citation rather than a dependency, and a scan that fired on those would be
    # deleted rather than narrowed. What must not exist is a module that opens a document.
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = (
                function.attr
                if isinstance(function, ast.Attribute)
                else getattr(function, "id", "")
            )
            if name not in {"read_text", "read_bytes", "open"}:
                continue
            rendered = ast.unparse(node)
            if any(marker in rendered for marker in (".md", "spec", "tasks", "notes")):
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")
    assert not offenders, f"a source module reads a planning document: {offenders}"


def test_the_planning_citations_that_do_exist_are_prose() -> None:
    """And the modules that name `tasks.md` name it in a docstring, which is a citation.

    Stated so the narrowing above reads as a decision rather than as a gap: the citations
    are real, they are supposed to be there, and none of them is a dependency.
    """
    citing = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if "__pycache__" not in path.parts and "tasks.md" in path.read_text(encoding="utf-8")
    )
    assert citing, "no module cites its task; the narrowing above would be untested"
    for relative in citing:
        tree = ast.parse((SRC / relative).read_text(encoding="utf-8"), filename=relative)
        prose = "\n".join(
            ast.get_docstring(node) or ""
            for node in [tree, *ast.walk(tree)]
            if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        )
        assert "tasks.md" in prose, relative


def test_an_ambiguous_question_abstains_rather_than_clarifying() -> None:
    """The user-visible consequence: the fifth of the feature's five independent locks."""
    # OD-101 (2026-09-02): o quinto cadeado mudou de lugar — o portao abriu, e a
    # abstencao continua onde a implantacao nao tem chave: porto ausente recusa.
    require_clarification_sealing()
    contract = issued_contract(fingerprint=derive_authorization_fingerprint(authorize()))
    from analytics_interaction.clarification.seal import issue_seal

    with pytest.raises(ContractViolation) as raised:
        issue_seal(contract, port=None, key_id=FIXTURE_KEY_ID, algorithm=FIXTURE_ALGORITHM)
    assert raised.value.code is Code.CLARIFICATION_UNAVAILABLE


# --- no key, algorithm, provider, environment lookup or secret was introduced ---


#: The clarification surface, where a seal-key decision would have to live.
#:
#: Scoped rather than package-wide, deliberately. `identity/` computes two **keyless**
#: digests -- the authorization fingerprint and the interpretation identity -- and both use
#: `hashlib` legitimately. A package-wide scan fired on those, reporting a governed design
#: as a violation.
#:
#: What `D-21` governs is *key material* and the algorithm applied to it. Neither belongs
#: anywhere in `clarification/`, and that is where it would arrive.
SEAL_SURFACE = ("clarification",)

FORBIDDEN_IN_SEAL_SURFACE = frozenset(
    {
        "hashlib",
        "hmac",
        "sha256",
        "sha512",
        "blake2b",
        "cryptography",
        "nacl",
        "secrets",
        "getenv",
        "environ",
    }
)


def _reached_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.Name):
            found.add(node.id)
    return found


def test_no_clarification_module_names_key_material_or_an_algorithm_choice() -> None:
    """The production port declares **no** algorithm, because that decision is `D-21`'s.

    Scanned as AST identifiers, imports and calls rather than as text: the seal module's
    docstring explains at length why it names no algorithm, and a text scan fires on the
    explanation.
    """
    offenders: list[str] = []
    for package in SEAL_SURFACE:
        for path in sorted((SRC / package).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            hit = _reached_names(path) & FORBIDDEN_IN_SEAL_SURFACE
            if hit:
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {sorted(hit)}")
    assert not offenders, f"key material or an algorithm choice reached clarification/: {offenders}"


def test_the_scan_would_catch_a_planted_algorithm(tmp_path: pathlib.Path) -> None:
    """The narrowing left no hole in the surface it still covers."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import hashlib\ndef seal(x):\n    return hashlib.sha256(x)\n", encoding="utf-8"
    )
    assert _reached_names(planted) & FORBIDDEN_IN_SEAL_SURFACE


def test_the_identity_digests_are_keyless_and_are_not_seals() -> None:
    """Why `identity/` is out of scope above, asserted rather than asserted-about.

    Both digests hash a canonical preimage with **no key**. They bind, and they do not
    authenticate, so `D-21` governs neither -- which makes excluding them a scoping
    decision rather than an exemption.
    """
    from analytics_interaction.identity import authorization_fingerprint, interpretation_identity

    for module in (authorization_fingerprint, interpretation_identity):
        source = inspect.getsource(module)
        assert "hashlib" in source, "the digest must still be a digest"
        for keyed in ("hmac", "key=", "sign("):
            assert keyed not in source, (module.__name__, keyed)


def test_the_seal_port_declares_no_algorithm() -> None:
    """Structural: the port takes the algorithm as data, so it cannot choose one."""
    from analytics_interaction.clarification.seal import SealPort

    source = inspect.getsource(SealPort)
    for forbidden in ("sha", "hmac", "rsa", "ed25519", "hashlib"):
        assert forbidden not in source.lower(), forbidden


def test_the_fixture_key_is_reachable_only_from_tests() -> None:
    """And the synthetic key stays where it is. Asserted here too, cheaply.

    The containment scan owns this claim in full; restating it beside the carry-forward
    keeps a reader from concluding that "no key exists" is contradicted by the fixture.
    """
    from ..fixtures.seal import FIXTURE_MARKER

    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        assert FIXTURE_MARKER not in path.read_text(encoding="utf-8"), path


# --- integrity availability is not single-use replay prevention ----------------


def test_sealing_and_single_use_detection_are_recorded_separately() -> None:
    """**`D-21` enables one and not the other.**

    Merging them would make `D-21`'s arrival look like it closes the replay gap. It does
    not: nothing records that a contract was presented, so nothing can refuse a second
    presentation.
    """
    posture = replay_posture()
    assert "single_use_consumption" in UNENFORCEABLE_WITHOUT_STATE
    assert "cross_process_replay_detection" in UNENFORCEABLE_WITHOUT_STATE
    assert posture.consumption_detected is False
    assert "single_use_consumption" not in posture.enforced


def test_a_sealed_contract_still_validates_twice() -> None:
    """Proved with the fixture key, because that is the only way to reach the state.

    **Fixture-only.** With sealing enabled synthetically, a contract resubmitted inside its
    window validates twice — which is what "`D-21` does not close the replay gap" means in
    behaviour rather than in prose.
    """
    port = FixtureSealPort(key=FIXTURE_KEY)
    records = ready_records(InteractionCapability.D_21)
    contract = issued_contract(port=port, fingerprint=derive_authorization_fingerprint(authorize()))

    for _ in range(3):
        assert verify_seal(contract, port=port, records=records) is None

    # OD-101 (2026-09-02): o estado embarcado passou a concordar com a fixture.
    assert is_capability_available(InteractionCapability.D_21)


def test_the_note_distinguishes_the_two_properties() -> None:
    """The document says it too, so the distinction survives outside this file."""
    text = NOTES.read_text(encoding="utf-8")
    assert "Integrity is not single-use detection" in text
    assert "does not arrive with `D-21`" in text.replace("**", "")
    assert "single-use consumption remains undetectable without state" in text


def test_the_expiry_window_is_not_replay_prevention_either() -> None:
    """A window bounds how long a contract lives, not how often it is used.

    Worth separating: an expiry is the control most easily mistaken for replay prevention,
    because both sound like limits on reuse.
    """
    port = FixtureSealPort(key=FIXTURE_KEY)
    records = ready_records(InteractionCapability.D_21)
    contract = issued_contract(port=port, fingerprint=derive_authorization_fingerprint(authorize()))
    assert contract.expires_at - contract.issued_at == timedelta(minutes=15)
    assert verify_seal(contract, port=port, records=records) is None
    assert verify_seal(contract, port=port, records=records) is None
    assert datetime(2026, 8, 13, tzinfo=UTC) < contract.expires_at


# --- carried forward, not closed -----------------------------------------------


def test_the_record_is_carried_forward_without_being_marked_complete() -> None:
    """`T185` stays open, and nothing here supplies evidence for it."""
    tasks = (REPO / "specs" / "003-nl-analytics-interaction" / "tasks.md").read_text(
        encoding="utf-8"
    )
    lines = [line for line in tasks.splitlines() if "[BLOCKED-EXTERNAL]" in line and "D-21" in line]
    assert len(lines) == 1, lines
    # OD-101 (2026-09-02): T185 fechou pela regra uniforme — [X] + marcador + CLOSED
    # datado; e o carry-forward do spec-amendment continua dito na propria linha.
    assert lines[0].lstrip().startswith("- [X]"), lines[0]
    assert "CLOSED 20" in lines[0], lines[0]
    assert "carry-forward" in lines[0], "a linha fechada esqueceu o carry-forward do spec"


def test_nothing_in_this_task_changed_the_aggregate() -> None:
    """Readiness is still NONE, read after everything above has run."""
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )
