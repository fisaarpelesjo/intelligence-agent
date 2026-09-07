"""The reconciled baseline — T179 (BD-1; ADR 0014).

    Evidence: a `baseline_reconciliation` entry naming ADR 0014; unrelated architecture
    unchanged. — `tasks.md` T179

    Validation: the **only** authorized edit to the baseline, and only in this phase.
    — `tasks.md` T179

## What was contradicted, and what the correction is

`docs/intelligence-agent.yaml` declared `agent.state_management.conversational_state:
PostgreSQL`. No feature implements a conversational state store, and `003`'s approved
design says none will: a clarification is stateless, self-contained, versioned, sealed and
identity-bound, with continuity travelling in the contract rather than in a store.

ADR 0014 recorded the divergence and stated explicitly that it did **not** edit the
baseline. `T179` is the corresponding edit, authorized only in this phase.

## Recorded absent, not removed

The field is corrected to `deferred_not_implemented` with the intended store kept beside
it, rather than deleted. Both alternatives mislead in opposite directions:

* leaving `PostgreSQL` asserts a capability that does not exist — a reader takes the
  baseline as a description of the system;
* deleting the field implies the question was never decided, and the next feature to need
  conversational state would re-litigate a settled decision without knowing it was settled.

So the baseline now says: absent, intended store named, and why.

## Why these tests assert state rather than an edit

A test that checked "the file changed" would pass for any change, including one that
deleted the block. Every assertion below reads the **resulting document** and states what
must be true of it — that the deviation exists and names ADR 0014, that the corrected value
is what it should be, that `001`'s block is untouched field for field, and that every
capability the baseline could be read as promising is recorded with its real state.

## What must stay future or unavailable

Channel integrations, the production model provider, production governed content and the
seal key are all recorded as future or unavailable rather than quietly dropped. A baseline
that stopped mentioning them would read as a system that never needed them.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import analytics_interaction

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
REPO = SRC.parents[3]
BASELINE = REPO / "docs" / "intelligence-agent.yaml"
ADR_0014 = REPO / "docs" / "adr" / "0014-stateless-sealed-clarification-contract.md"

#: This feature's reconciliation block, kept separate from `001`'s.
#:
#: `001`'s block declares `feature: 001-semantic-catalog` and `applied_by: T111`. Adding a
#: `003` deviation there would attribute it to the wrong feature, and BD numbering is
#: per-feature exactly as FR and SC numbering is.
BLOCK = "baseline_reconciliation_nl_analytics"


def _document() -> dict[str, Any]:
    loaded: object = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def _block() -> dict[str, Any]:
    document = _document()
    assert BLOCK in document, f"{BLOCK} is absent from the baseline"
    return cast("dict[str, Any]", document[BLOCK])


def _deviation(identifier: str) -> dict[str, Any]:
    for entry in cast("list[dict[str, Any]]", _block()["deviations"]):
        if entry["id"] == identifier:
            return entry
    raise AssertionError(f"{identifier} is not recorded")


# --- the baseline still parses, and 001's block is untouched --------------------


def test_the_baseline_is_well_formed() -> None:
    """A corrupted baseline would make every assertion below vacuous."""
    document = _document()
    assert document
    for section in ("agent", "delivery", "security", "semantic_layer", "analytics_query"):
        assert section in document, section


def test_the_001_reconciliation_block_is_untouched() -> None:
    """**The unrelated-architecture guarantee, at its most likely failure point.**

    `001`'s block is the thing a careless edit would extend. Asserted field by field rather
    than by presence, because appending a `003` deviation to `001`'s list would leave the
    block present and its attribution wrong.
    """
    inherited = cast("dict[str, Any]", _document()["baseline_reconciliation"])
    assert inherited["feature"] == "001-semantic-catalog"
    assert inherited["applied_by"] == "T111"
    assert inherited["deviation_count"] == 5
    assert [entry["id"] for entry in inherited["deviations"]] == [
        "BD-1",
        "BD-2",
        "BD-3",
        "BD-4",
        "BD-5",
    ]
    assert inherited["deviations"][0]["path"] == "data_freshness.rules.use_lowest_common_coverage"


def test_the_two_blocks_are_separate_and_both_numbered_from_one() -> None:
    """Two `BD-1`s, and they are different deviations.

    Per-feature numbering, like FR and SC. Stated so a reader encountering the collision
    finds the reason next to it rather than assuming one of them is a mistake.
    """
    inherited = cast("dict[str, Any]", _document()["baseline_reconciliation"])
    assert inherited["deviations"][0]["id"] == "BD-1"
    assert _deviation("BD-1")["id"] == "BD-1"
    assert inherited["deviations"][0]["path"] != _deviation("BD-1")["path"]


# --- the deviation is recorded, and names ADR 0014 -----------------------------


def test_the_block_is_attributed_to_this_feature_and_task() -> None:
    block = _block()
    assert block["feature"] == "003-nl-analytics-interaction"
    assert block["applied_by"] == "T179"
    assert block["deviation_count"] == 1
    assert len(block["deviations"]) == 1


def test_bd_1_names_adr_0014_and_the_adr_exists() -> None:
    """**`T179`'s named evidence.**

    The ADR is asserted to exist and to be the one that recorded the divergence, so the
    citation cannot point at a document that says something else.
    """
    deviation = _deviation("BD-1")
    assert deviation["adr"] == "docs/adr/0014-stateless-sealed-clarification-contract.md"
    assert ADR_0014.is_file()

    text = ADR_0014.read_text(encoding="utf-8")
    assert "BD-1" in text
    assert "agent.state_management.conversational_state" in text
    assert "does **not** edit the baseline" in text, (
        "ADR 0014 must still say it did not edit the baseline; this task is that edit"
    )


def test_bd_1_records_the_previous_and_corrected_values() -> None:
    """Both halves, so the record says what changed rather than only what is true now."""
    deviation = _deviation("BD-1")
    assert deviation["path"] == "agent.state_management.conversational_state"
    assert deviation["previous"] == "PostgreSQL"
    assert deviation["corrected_to"] == "deferred_not_implemented"
    assert "ADR 0014" in deviation["governing_source"]


def test_bd_1_points_at_the_implementation() -> None:
    """The clarification package exists and is what the deviation names."""
    deviation = _deviation("BD-1")
    assert "clarification" in deviation["implemented_in"]
    package = SRC / "clarification"
    assert package.is_dir()
    for module in ("issue.py", "resume.py", "seal.py", "replay.py", "future_store.py"):
        assert (package / module).is_file(), module


# --- the corrected value says absent, and names the intended store -------------


def test_the_conversational_state_field_is_recorded_absent() -> None:
    """**Neither `PostgreSQL` nor deleted.**

    Leaving the old value asserts a capability that does not exist; deleting the field
    implies the question was never decided. The corrected form says absent, names the
    intended store separately, and explains why.
    """
    state = cast("dict[str, Any]", _document()["agent"]["state_management"])
    assert state["conversational_state"] == "deferred_not_implemented"
    assert state["conversational_state_intended_store"] == "PostgreSQL"
    assert "stateless" in state["conversational_state_note"].lower()
    assert "ADR 0014" in state["conversational_state_note"]


def test_the_checkpoint_field_is_recorded_the_same_way() -> None:
    """Contradicted by the same fact, so corrected by the same rule.

    No implemented feature runs a persisted graph. Leaving one field honest and the other
    asserting a store would make the baseline half-true in a way a reader cannot detect.
    """
    state = cast("dict[str, Any]", _document()["agent"]["state_management"])
    assert state["graph_checkpoints"] == "deferred_not_implemented"
    assert state["graph_checkpoints_intended_store"] == "PostgreSQL"


def test_no_state_field_still_asserts_a_live_store() -> None:
    """Swept, so a third field added later cannot quietly assert one.

    Any value naming a concrete store must be an ``_intended_store`` field, which reads as a
    plan rather than as a description.
    """
    state = cast("dict[str, Any]", _document()["agent"]["state_management"])
    for name, value in state.items():
        if not isinstance(value, str) or name.endswith(("_note", "_intended_store")):
            continue
        assert value not in {"PostgreSQL", "Redis", "DynamoDB", "SQLite"}, (name, value)


# --- absent capabilities are recorded rather than dropped ----------------------


@pytest.mark.parametrize(
    "capability,state",
    [
        ("conversational_state_store", "absent"),
        ("cross_process_single_use_detection", "unenforceable_without_state_store"),
        ("channel_integrations", "future"),
        ("production_model_provider", "unavailable"),
        ("production_governed_content", "unavailable"),
        ("clarification_seal_key", "unavailable"),
    ],
)
def test_every_absent_capability_is_recorded_with_its_state(capability: str, state: str) -> None:
    """A baseline that stopped mentioning them would read as a system that never needed them."""
    recorded = cast("dict[str, Any]", _block()["capabilities_recorded_absent"])
    assert capability in recorded, capability
    assert recorded[capability]["state"] == state


def test_the_unavailable_capabilities_name_their_governing_records() -> None:
    """So a reader can find the record rather than infer which one applies."""
    recorded = cast("dict[str, Any]", _block()["capabilities_recorded_absent"])
    assert recorded["production_model_provider"]["governing_record"] == "D-20"
    assert recorded["clarification_seal_key"]["governing_record"] == "D-21"
    assert "D-18" in recorded["production_governed_content"]["governing_record"]
    assert "D-19" in recorded["production_governed_content"]["governing_record"]


def test_integrity_is_distinguished_from_single_use_detection() -> None:
    """**Two different things, and the baseline must not merge them.**

    A seal detects tampering. It does not detect resubmission. Recording "sealing is
    unavailable" alone would let a reader conclude that `D-21`'s arrival closes the replay
    gap — it does not, and `FR-080` says so.
    """
    entry = cast("dict[str, Any]", _block()["capabilities_recorded_absent"])[
        "cross_process_single_use_detection"
    ]
    assert entry["state"] == "unenforceable_without_state_store"
    note = entry["note"].lower()
    assert "adulteração" in note or "tamper" in note
    assert "duas vezes" in note or "twice" in note


# --- the channels and the rest of the architecture are unchanged ---------------


def test_every_delivery_channel_remains_disabled() -> None:
    """`003` produces channel-neutral contracts and implements no adapter."""
    channels = cast("dict[str, Any]", _document()["delivery"]["channels"])
    assert set(channels) == {"slack", "microsoft_teams", "email", "webhook"}
    for name, channel in channels.items():
        assert channel["enabled"] is False, name


@pytest.mark.parametrize(
    "path,expected",
    [
        (("agent", "architecture"), "single_orchestrator"),
        (("agent", "multi_agent_enabled"), False),
        (("agent", "framework", "primary"), "LangGraph"),
        (("agent", "state_management", "unlimited_memory"), False),
        (("delivery", "pattern"), "transactional_outbox"),
    ],
)
def test_unrelated_architecture_is_unchanged(path: tuple[str, ...], expected: object) -> None:
    """The reconciliation corrected one contradiction, not the architecture.

    A short, load-bearing sample rather than a whole-file hash: a hash would fail on every
    legitimate future edit and would be deleted the first time it did.
    """
    node: Any = _document()
    for key in path:
        node = node[key]
    assert node == expected


def test_the_block_lists_what_it_preserved() -> None:
    """Stated in the document, so a reviewer sees the intended scope without a diff."""
    preserved = cast("list[str]", _block()["preserved_unchanged"])
    assert preserved
    joined = " ".join(preserved)
    assert "delivery.channels" in joined
    assert "001-semantic-catalog" in joined


# --- the reconciliation claims nothing --------------------------------------


def test_the_block_claims_no_readiness_and_closes_no_record() -> None:
    """A reconciliation is a correction, not a release note."""
    block = _block()
    not_claimed = " ".join(cast("list[str]", block["not_claimed"])).lower()
    assert "prontidão de produção" in not_claimed
    note = block["not_claimed_note"].lower()
    assert "não encerra nenhum registro blocked-external" in note
    assert "t181" in note


def test_the_baseline_edit_did_not_touch_readiness() -> None:
    """Every external record is still open, read through the package's own reader."""
    from analytics_interaction.compliance.readiness import aggregate_ready, load_all_records

    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )


def test_no_key_provider_or_secret_entered_the_baseline() -> None:
    """The correction records absences; it must not have introduced a value.

    Scoped to the block this task added, and matched against **material** rather than the
    word "secret". The baseline legitimately names `Secret_Manager`, `secret_rotation` and
    `secretmanager.secretAccessor` — a bare token scan fired on all three, which is a scan
    that gets deleted rather than narrowed.

    What must not appear is a value: a key, a key id, an algorithm choice, a provider
    endpoint, an environment lookup or a fixture marker.
    """
    block = yaml.safe_dump(_block(), allow_unicode=True, sort_keys=True)
    for forbidden in (
        "key_id",
        "api_key",
        "private_key",
        "BEGIN PRIVATE",
        "sha256",
        "hmac",
        "os.environ",
        "getenv",
        "fixture-only",
        "https://",
        "Bearer ",
    ):
        assert forbidden not in block, forbidden

    # And the seal key is named only as an unavailable capability, never valued.
    seal = _block()["capabilities_recorded_absent"]["clarification_seal_key"]
    assert seal["state"] == "unavailable"
    assert set(seal) == {"state", "governing_record", "note"}


def test_the_correction_introduced_no_new_secret_bearing_field() -> None:
    """The whole-document half, done by **comparison against the committed file**.

    A token scan is wrong here in both directions. The baseline has always named secret
    *management* — `Secret_Manager`, `secret_rotation`, `secretmanager.secretAccessor` — so
    a denylist fires on three pre-existing lines; and this task's own note says no secret
    material was introduced, so the denylist fires on the denial too.

    What matters is not whether the word appears but whether **this task added any of it**.
    So the check is a diff: the secret-adjacent lines outside the new block must be exactly
    the ones `HEAD` already had.
    """
    import subprocess

    committed = subprocess.run(
        ["git", "show", "HEAD:docs/intelligence-agent.yaml"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout

    def secret_lines(text: str) -> list[str]:
        # The new block is excluded because a *denial* of secret material legitimately
        # contains the word, and permitting explicit negations is the same rule the
        # production-claim scan uses.
        head, _, _ = text.partition(f"{BLOCK}:")
        return sorted(line.strip() for line in head.splitlines() if "secret" in line.lower())

    assert secret_lines(BASELINE.read_text(encoding="utf-8")) == secret_lines(committed)


def test_the_new_block_mentions_secrets_only_to_deny_them() -> None:
    """And the exclusion above is not a hole.

    Every occurrence inside the new block is a negation. A line that named one instead
    would fail here rather than ride on the exclusion.
    """
    _, _, tail = BASELINE.read_text(encoding="utf-8").partition(f"{BLOCK}:")
    for line in tail.splitlines():
        if "secret" not in line.lower():
            continue
        assert "nenhum" in line.lower() or "material secreto foi introduzido" in line.lower(), line
