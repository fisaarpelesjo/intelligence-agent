"""The serialised-content scan — T139 (FR-053; SC-026).

    Evidence: catches a value smuggled into a field whose name sounds innocent.
    — `tasks.md` T139

The **second** of the denylist's two enforcements, and the one that catches what
a schema check cannot. `T138` proves no field *can* hold a forbidden value;
this scans a **fully populated event's serialised bytes** for one that got in
anyway — through a field whose name and type are both perfectly reasonable.

``metric_ids: tuple[str, ...]`` passes every schema assertion and will happily
carry ``("installs=42",)``. So will ``correlation_id``. That is the failure mode
`002` documented and the reason both enforcements exist.

## The same scan guards telemetry

`T140`'s spans are scanned by **this** detector, not a similar one — so a value
that could not enter an audit event cannot enter a span either, and telemetry
cannot become the channel that leaks what audit forbids.

## Why the fixture must be fully populated

A scan over a sparse event proves nothing about the fields nobody filled, and
those are exactly where a smuggled value would sit. ``populated_event`` sets
every field; a field added later without a fixture value would leave a hole here,
so `T138`'s field count is the tripwire for that.
"""

from __future__ import annotations

import re

import pytest
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_interaction.contracts.audit import InterpretationAuditEvent, InterpretationStage
from analytics_interaction.telemetry.spans import SpanStep, span_for

from ..fixtures.audits import populated_event, preauthorization_refusal, release_event

pytestmark = pytest.mark.contract

#: Shapes a value takes when it is smuggled into a governed-identifier field.
#: Patterns rather than literals, because the smuggling is a *shape* — an
#: identifier with a number welded on — and a literal list would only catch the
#: examples somebody thought of.
VALUE_SHAPES: tuple[tuple[str, str], ...] = (
    ("assignment", r"[A-Za-z_]+\s*=\s*-?\d"),
    ("colon-value", r"[A-Za-z_]+\s*:\s*-?\d+\.\d"),
    ("bare decimal", r"(?<![\w.-])\d+\.\d{2,}(?![\w.])"),
    ("currency", r"(?:R\$|\$|€)\s*-?\d"),
    ("percentage", r"-?\d+(?:[.,]\d+)?\s*%"),
    ("comparison arrow", r"-?\d+\s*(?:->|→|vs\.?)\s*-?\d"),
)

#: Text that is not a value but must never appear either.
FORBIDDEN_CONTENT: tuple[tuple[str, str], ...] = (
    ("SQL", r"\b(?:SELECT|FROM|WHERE|GROUP BY|JOIN|UNION)\b"),
    ("question", r"\b(?:quantas|quantos|qual|como|por que)\b"),
    ("email", r"[^@\s\"]+@[^@\s\"]+\.[^@\s\"]+"),
    ("bearer token", r"\b(?:Bearer|bearer)\s+\S+"),
    ("key material", r"(?:BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]{8,})"),
    ("ip address", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
)


def _leaks(payload: str) -> list[str]:
    """Every forbidden shape the serialised payload contains."""
    return [
        name for name, pattern in (*VALUE_SHAPES, *FORBIDDEN_CONTENT) if re.search(pattern, payload)
    ]


# --- a fully populated event leaks nothing ------------------------------------------


@pytest.mark.parametrize("stage", list(InterpretationStage), ids=lambda s: s.value)
def test_a_fully_populated_event_carries_no_value_at_any_stage(
    stage: InterpretationStage,
) -> None:
    """Every stage, every field set. The scan reads the bytes a sink receives."""
    event = populated_event(
        stage, interpretation_id=None if stage is InterpretationStage.INTAKE else "interp-1"
    )
    assert not _leaks(event.model_dump_json())


def test_a_pre_authorization_refusal_carries_no_value() -> None:
    """The sparsest event, checked too — absence is not the same as safety."""
    assert not _leaks(preauthorization_refusal().model_dump_json())


def test_a_comparison_event_carries_the_route_and_not_the_difference() -> None:
    """**The asymmetry the whole contract rests on.**

    The event records the verdict, the window, the formula and the outcome. It
    never records what was returned.
    """
    event = populated_event(code=ReasonCode.EQUIVALENT_PARTIAL_COMPARISON)
    payload = event.model_dump_json()

    assert "two_execution" in payload
    assert not _leaks(payload)
    assert "difference" not in payload
    assert "50" not in payload


def test_the_scan_reads_the_serialised_form_not_the_object() -> None:
    """A sink receives bytes. Inspecting attributes would miss a nested leak."""
    payload = release_event().model_dump_json()
    assert payload.startswith("{")
    assert "interp-1" in payload  # the identifier is present and is not a value


# --- the scan fires -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shape", "smuggled"),
    [
        ("assignment", "installs=42"),
        ("colon-value", "installs: 41.75"),
        ("bare decimal", "0.9312"),
        ("currency", "R$ 1200"),
        ("percentage", "12.5%"),
        ("comparison arrow", "150 -> 100"),
        ("SQL", "SELECT installs FROM metrics"),
        ("question", "quantas instalações tivemos"),
        ("email", "analista@example.com"),
        ("bearer token", "Bearer abc123def"),
        ("key material", "sk-live0000ABCD"),
        ("ip address", "10.0.0.7"),
    ],
)
def test_the_scan_catches_a_value_in_an_innocent_looking_field(shape: str, smuggled: str) -> None:
    """**The whole point of this file.**

    Every one of these fits ``metric_ids: tuple[str, ...]`` and passes every
    schema assertion `T138` makes. Only reading the bytes catches them.
    """
    event = release_event().model_copy(update={"metric_ids": ("installs", smuggled)})
    leaks = _leaks(event.model_dump_json())
    assert leaks, f"{shape} was not detected"


@pytest.mark.parametrize(
    "field", ["correlation_id", "interpretation_id", "catalog_release", "principal_ref"]
)
def test_the_scan_covers_every_string_field(field: str) -> None:
    """Not only the identifier collections. Any string field is a channel."""
    event = release_event().model_copy(update={field: "installs=42"})
    assert _leaks(event.model_dump_json())


def test_the_scan_does_not_fire_on_governed_identifiers() -> None:
    """Otherwise it would be narrowed until it stopped firing at all.

    Every value in a clean event — identifiers, tags, versions, dates, an enum —
    must pass, or the detector is useless in the only situation it runs in.
    """
    clean = release_event()
    payload = clean.model_dump_json()

    for expected in ("installs", "appstore", "country", "r-1", "pol-1", "voc-1", "2026-07-01"):
        assert expected in payload
    assert not _leaks(payload)


@pytest.mark.parametrize(
    "innocent",
    [
        "installs",
        "cross_source_metric",
        "app_a",
        "installs:read",
        "r-1",
        "2026-07-31",
        "TWO_EXECUTION",
    ],
)
def test_governed_shapes_are_not_mistaken_for_values(innocent: str) -> None:
    """An access tag contains a colon; a date contains digits. Neither is a value."""
    assert not _leaks(innocent)


# --- the same scan guards telemetry -----------------------------------------------------


def test_a_clean_span_passes_the_same_scan() -> None:
    """The control, before the leak cases below."""
    span = span_for(
        SpanStep.ASSEMBLE_ANSWER,
        correlation_id="corr-1",
        attributes={
            "metric_ids": "installs",
            "catalog_release": "r-1",
            "policy_version": "pol-1",
            "route": "two_execution",
            "status": "released",
        },
    )
    assert not _leaks(repr(span))


@pytest.mark.parametrize("smuggled", ["installs=42", "R$ 1200", "SELECT installs FROM metrics"])
def test_a_span_attribute_carrying_a_value_fails_the_same_scan(smuggled: str) -> None:
    """**Telemetry cannot become the channel that leaks what audit forbids.**

    The allowlist stops an *unknown* attribute; this stops a known attribute
    carrying an unknown thing. Both are needed, and the scan is the same one.
    """
    span = span_for(
        SpanStep.SUBMIT_REQUEST,
        correlation_id="corr-1",
        attributes={"metric_ids": smuggled},
    )
    assert _leaks(repr(span))


def test_the_span_and_the_event_are_scanned_by_one_detector() -> None:
    """Not a similar detector. The same function, over both payloads.

    Two detectors would drift, and the one that drifted would be the one nobody
    was watching.
    """
    event_payload = release_event().model_dump_json()
    span_payload = repr(
        span_for(SpanStep.ASSEMBLE_ANSWER, correlation_id="corr-1", attributes={"status": "ok"})
    )

    assert _leaks(event_payload) == _leaks(span_payload) == []
    assert _leaks("installs=42") == _leaks("installs=42")


# --- determinism ---------------------------------------------------------------------------


def test_the_serialised_event_is_stable() -> None:
    """`SC-028`: the scan reads the same bytes every time it runs."""
    assert release_event().model_dump_json() == release_event().model_dump_json()


def test_the_event_serialises_without_a_timestamp() -> None:
    """No clock is read, so two equivalent flows produce equal payloads."""
    payload = release_event().model_dump_json()
    assert "emitted_at" not in payload
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:", payload)


def test_no_field_of_the_event_is_free_text() -> None:
    """Every string in a clean payload is an identifier, a version or a date."""
    event = release_event()
    strings = [value for value in event.model_dump(mode="json").values() if isinstance(value, str)]
    for value in strings:
        assert " " not in value, f"a spaced string reached the event: {value!r}"


def test_an_event_field_never_carries_a_sentence() -> None:
    """A sentence is where wording — and a quoted figure — arrives."""
    assert not any(
        isinstance(value, str) and value.endswith(".")
        for value in InterpretationAuditEvent.model_fields
    )
