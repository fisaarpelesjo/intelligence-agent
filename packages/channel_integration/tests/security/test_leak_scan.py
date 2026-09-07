"""The serialised leak scan — T065 (FR-076 to FR-079, FR-082, FR-085; SC-031, SC-040).

Every field-set assertion elsewhere proves a value cannot be **added**. This proves it cannot be
**smuggled** — hidden inside a field that is allowed to exist.

The difference matters because the two failures have different causes. A forbidden field is caught
by a closed model. A forbidden *value* in an allowed string field is caught only by looking at the
bytes, and the bytes are what reach the audit sink, the log line, the trace attribute, the metric
label and the refusal a sender reads.

So this scan takes a marked corpus — every value that must never appear, each given a distinctive
sentinel — drives it through the record-producing surfaces available in Phase B, serialises the
result, and asserts no sentinel survives:

* the **secret** and the signature computed from it;
* the **question text** the sender wrote;
* the raw **external identity**;
* an **analytical value**, which is the one this project cares about most: a number that reached a
  channel record would be an analytical result outside the governed boundary;
* the raw **headers** and the raw **body**.

Outbound payloads and CLI output are named by `T065` and belong to Phase C and Phase E; they do not
exist yet. Rather than pretend otherwise, the surfaces that exist are scanned and the gap is stated,
with the assertion that no module capable of producing those surfaces is present. A scan claiming to
cover an outbound payload that no code can produce would be theatre.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from channel_integration.audit.emit import build_event
from channel_integration.contracts._base import MessageKey
from channel_integration.contracts.audit import ChannelAuditEvent, ChannelStage
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.identity import ExternalIdentity
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.inbound.convert import convert
from channel_integration.telemetry.spans import span_attributes, span_name

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    FIXTURE_SECRET,
    bounds_for,
    descriptor_for,
    signed_request,
    wire_payload,
)
from ..fixtures.identity import (
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
    fixture_pseudonymiser,
)

pytestmark = pytest.mark.security

_SRC = Path(__file__).resolve().parents[2] / "src" / "channel_integration"
_CHANNEL = ChannelId.SLACK

#: A distinctive sentinel per forbidden category. Distinctive so a failure names the category rather
#: than reporting "a string appeared somewhere".
_MARKED_QUESTION = "LEAKMARK-QUESTION quantas instalações em julho?"
_MARKED_IDENTITY = "LEAKMARK-IDENTITY-+5511999990000"
_MARKED_VALUE = "LEAKMARK-VALUE-1234567.89"

_SENTINELS = {
    "the sender's question": "LEAKMARK-QUESTION",
    "the external identity": "LEAKMARK-IDENTITY",
    "an analytical value": "LEAKMARK-VALUE",
    "the credential material": FIXTURE_SECRET,
}


def _assert_clean(surface: str, serialised: str) -> None:
    for category, sentinel in _SENTINELS.items():
        assert sentinel not in serialised, f"{surface} leaked {category}"


def _refusal(text: str) -> ChannelRefusal:
    outcome = convert(
        signed_request(_CHANNEL, payload=wire_payload(text=text, tenant="tenant-b")),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=ExternalIdentity(_MARKED_IDENTITY),
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal), "the tenant mismatch must refuse"
    return outcome


def _event() -> ChannelAuditEvent:
    pseudonymiser = fixture_pseudonymiser()
    return build_event(
        stage=ChannelStage.IDENTIFIED,
        channel=_CHANNEL,
        tenant=FIXTURE_TENANT,
        principal_ref=FIXTURE_PRINCIPAL,
        correlation_id=pseudonymiser.derive("correlation", "fixture"),  # type: ignore[arg-type]
        message_key=MessageKey("fixture-message-key-1"),
        code=ChannelReasonCode.CHANNEL_TENANT_MISMATCH,
        pseudonymiser=pseudonymiser,
        external=ExternalIdentity(_MARKED_IDENTITY),
    )


def test_a_refusal_carries_no_marked_value() -> None:
    """The sender-facing surface: governed wording only, never an echo of the input."""
    refusal = _refusal(_MARKED_QUESTION)
    _assert_clean("the refusal projection", refusal.sender_text())
    _assert_clean("the serialised refusal", refusal.model_dump_json())


def test_a_refusal_does_not_echo_the_question_even_when_the_question_caused_it() -> None:
    """The tempting leak: "we could not understand *this*". `FR-045` forbids it."""
    refusal = _refusal(_MARKED_QUESTION + " " + _MARKED_VALUE)
    assert "LEAKMARK" not in refusal.sender_text()
    assert refusal.message_pt_br.strip(), "a governed wording must still be present"


def test_a_serialised_audit_event_carries_no_marked_value() -> None:
    _assert_clean("the serialised audit event", _event().model_dump_json())


def test_the_audit_event_has_no_field_that_could_hold_one() -> None:
    """Belt and braces: the smuggling scan above and the field set together."""
    declared = set(ChannelAuditEvent.model_fields)
    for forbidden in (
        "payload",
        "body",
        "text",
        "question",
        "answer",
        "value",
        "filter_value",
        "provenance",
        "caveat",
        "headers",
        "signature",
        "credential",
        "token",
        "url",
        "error",
        "detail",
        "message",
    ):
        assert forbidden not in declared, f"ChannelAuditEvent declares {forbidden}"


def test_a_telemetry_attribute_set_carries_no_marked_value() -> None:
    """Traces and metric labels are the same surface as a log line, and the same rule applies."""
    event = _event()
    attributes = {
        "channel": event.channel.value,
        "tenant": str(event.tenant),
        "principal_ref": str(event.principal_ref),
        "stage": event.stage.value,
        "outcome": event.outcome.value,
        "code": event.code,
        "detail_class": event.detail_class.value,
    }
    permitted = span_attributes(attributes)
    _assert_clean("the span attributes", json.dumps(permitted))
    _assert_clean("the span name", span_name(event.stage))


def test_a_content_bearing_attribute_cannot_be_attached_at_all() -> None:
    """The allowlist refuses the whole set rather than dropping the offender."""
    for name in ("text", "question", "answer", "value", "body", "signature", "phone"):
        with pytest.raises(ValueError, match="not permitted"):
            span_attributes({name: "LEAKMARK-VALUE-anything"})


def test_no_raw_header_or_body_reaches_any_record() -> None:
    """A signature and a raw body are the two things an adapter is most tempted to log."""
    raw = signed_request(_CHANNEL, payload=wire_payload(text=_MARKED_QUESTION))
    signature = dict(raw.headers)["x-slack-signature"]
    refusal = _refusal(_MARKED_QUESTION)
    for serialised in (refusal.model_dump_json(), _event().model_dump_json()):
        assert signature not in serialised
        assert raw.body.decode() not in serialised
        assert "x-slack-signature" not in serialised


def test_no_core_module_logs_anything_at_all() -> None:
    """The simplest way to guarantee a log line carries nothing: emit no log line.

    Logging is `D-30`'s concern, where the listener lives. A `logging` call in the core would be a
    record-producing surface outside the audit contract, which is exactly what `FR-085` closes.

    **The CLI is excluded here and covered separately below.** A steward command whose whole purpose
    is to print cannot satisfy "writes to no stream", and `T150` declared it. Excluding it without
    replacing the coverage would have been the loophole; the two assertions that follow are the
    replacement, and they are stricter about the CLI than this one could be.
    """
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        if source.is_relative_to(_SRC / "cli"):
            continue
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            for token in (
                "logging.",
                "logger.",
                "print(",
                "warnings.warn",
                "sys.stderr",
                "sys.stdout",
            ):
                if token in code:
                    offenders.append(f"{source.relative_to(_SRC)}:{number}: {token}")
    assert not offenders, offenders


def test_the_outbound_and_delivery_surfaces_are_now_covered() -> None:
    """The gap this test used to assert has closed, and the closure is the assertion.

    Until Phase C this file asserted that `outbound` and `delivery` did **not exist**, because a
    module that could produce an outbound payload while this scan ignored it would be an untested
    leak surface. Phase C created both, and that absence-assertion failed — which is the test doing
    its job rather than an inconvenience.

    So the coverage is now structural: every module under `outbound` and `delivery` is scanned for
    the same forbidden surfaces as the rest of the package, and no module there may log, print,
    warn, or write to a stream. The CLI is still absent and its absence is still asserted, with
    `T154` named as the owner that extends this scan when it arrives.
    """
    covered = sorted((_SRC / "outbound").rglob("*.py")) + sorted((_SRC / "delivery").rglob("*.py"))
    assert len(covered) >= 10, f"only {len(covered)} outbound/delivery modules were found"

    offenders: list[str] = []
    for source in covered:
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            for token in ("logging.", "logger.", "print(", "warnings.warn", "sys.std"):
                if token in code:
                    offenders.append(f"{source.relative_to(_SRC)}:{number}: {token}")
    assert not offenders, offenders

    #: The CLI arrived with `T150`, and this is the extension this line used to demand.
    assert (_SRC / "cli").exists(), "the CLI is gone; fold its coverage back into the core scan"


def test_the_cli_logs_nothing_and_writes_only_through_its_one_emitter() -> None:
    """The CLI may print. It may not log, and it may not print from anywhere it likes.

    Two separate statements, because they fail differently. A `logging` call in the CLI would be a
    record-producing surface outside the audit contract, exactly as in the core. A
    `sys.stdout.write` scattered across command bodies would bypass `emit`, and `emit` is what
    enforces the `FR-099` limitation field — so a second write path is a path on which a report
    ships without its disclaimer.

    `sys.stderr` is permitted in command bodies: a broken invocation must say what was wrong, and
    diagnostics do not travel through the report shape.
    """
    cli_sources = sorted((_SRC / "cli").rglob("*.py"))
    assert len(cli_sources) >= 2, f"only {len(cli_sources)} CLI modules were found"

    logging_offenders: list[str] = []
    stdout_offenders: list[str] = []
    for source in cli_sources:
        module = ast.parse(source.read_text(encoding="utf-8"))
        emitters = {
            node.name: (node.lineno, node.end_lineno or node.lineno)
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef) and node.name == "emit"
        }
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            for token in ("logging.", "logger.", "print(", "warnings.warn"):
                if token in code:
                    logging_offenders.append(f"{source.relative_to(_SRC)}:{number}: {token}")
            if "sys.stdout" in code and not any(
                start <= number <= end for start, end in emitters.values()
            ):
                stdout_offenders.append(f"{source.relative_to(_SRC)}:{number}")

    assert not logging_offenders, logging_offenders
    assert not stdout_offenders, (
        f"{stdout_offenders} write to stdout outside `emit`, so a report can ship without the "
        "FR-099 limitation field"
    )


def test_no_outbound_module_can_format_or_alter_a_value() -> None:
    """`FR-110`, structurally: the rendering path has no content-altering operation.

    Scanned by identifier rather than by comment, so a helper named ``_truncate`` fails wherever it
    is defined. The list is `outbound.degrade.FORBIDDEN_CONTENT_OPERATIONS`, imported rather than
    retyped, so the scan and the rule cannot drift apart.
    """
    from channel_integration.outbound.degrade import FORBIDDEN_CONTENT_OPERATIONS

    offenders: list[str] = []
    for source in sorted((_SRC / "outbound").rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        called = {
            node.func.attr if isinstance(node.func, ast.Attribute) else ""
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        for name in defined | called:
            for forbidden in FORBIDDEN_CONTENT_OPERATIONS:
                if forbidden and forbidden in name.lower():
                    offenders.append(f"{source.name}: {name}")
    assert not offenders, offenders
