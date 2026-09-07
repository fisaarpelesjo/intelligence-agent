"""A secret reference carries no secret — T064 (FR-068 to FR-071; SC-031, SC-032).

`SecretRef` is a **name plus a custody declaration**. It has no field for material, which is a
stronger property than redaction: redaction can be forgotten in one code path, whereas a value that
was never stored cannot escape from any.

Four escape routes are closed and each is asserted separately, because they fail independently:

* ``repr`` and ``str`` — the two functions an f-string, a traceback, a log call and a pydantic error
  all end up calling;
* **serialisation** — ``model_dump`` and ``model_dump_json``, the shape that reaches an audit sink,
  a metric label or a file;
* **the field set** — there is no ``value``, ``secret``, ``token`` or ``material`` field, not even
  an optional one;
* **reachability** — nothing under `src` resolves a reference to material. Resolution is
  adapter-side (`FR-071`), and while `D-22` to `D-25` are undeclared the shipped resolver returns
  nothing at all.

The last one is the reason this test exists as a *static* scan rather than only a behavioural one: a
core that could resolve material would be one refactor away from logging it, and no runtime
assertion catches the code path nobody exercised.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.secrets.ref import SecretRef
from channel_integration.secrets.resolver import UnavailableSecretResolver

from ..fixtures.channels import FIXTURE_SECRET, secret_ref_for

pytestmark = pytest.mark.security

_SRC = Path(__file__).resolve().parents[2] / "src" / "channel_integration"

#: Field names that would mean the object carries material rather than naming it.
_VALUE_FIELDS = ("value", "secret", "token", "material", "key", "credential", "password")


def _hash_of(value: object) -> int:
    return hash(value)


def test_the_reference_declares_no_field_for_material() -> None:
    """`FR-068`, by field set. Redaction is the fallback; absence is the mechanism."""
    declared = set(SecretRef.model_fields)
    for name in _VALUE_FIELDS:
        assert name not in declared, f"SecretRef declares {name}"
    assert declared == {"name", "channel", "credential_record", "custody", "rotation"}


@pytest.mark.parametrize("channel", list(ChannelId))
def test_repr_and_str_are_redacted(channel: ChannelId) -> None:
    ref = secret_ref_for(channel)
    for rendered in (repr(ref), str(ref), f"{ref}", f"{ref!r}", "{}".format(ref)):  # noqa: UP032
        assert "<redacted>" in rendered
        assert FIXTURE_SECRET not in rendered


def test_serialisation_carries_no_material() -> None:
    """The shape that reaches a sink, a label or a file."""
    ref = secret_ref_for(ChannelId.SLACK)
    dumped = ref.model_dump()
    assert set(dumped) == set(SecretRef.model_fields)
    serialised = ref.model_dump_json()
    assert FIXTURE_SECRET not in serialised
    assert FIXTURE_SECRET not in json.dumps(dumped, default=str)


def test_a_validation_error_over_the_reference_discloses_nothing() -> None:
    """Pydantic error text is a real leak surface: it echoes inputs."""
    with pytest.raises(Exception) as caught:
        SecretRef(  # type: ignore[call-arg]
            name="",
            channel=ChannelId.SLACK,
            credential_record="not-a-record",  # type: ignore[arg-type]
            custody="fixture",
            rotation="never",
        )
    assert FIXTURE_SECRET not in str(caught.value)


def test_the_shipped_resolver_resolves_nothing() -> None:
    """`D-22` to `D-25` undeclared: the production resolver returns ``None``, by design."""
    resolver = UnavailableSecretResolver()
    for channel in ChannelId:
        assert resolver.material_for(secret_ref_for(channel)) is None
    assert "<redacted>" in repr(resolver) or FIXTURE_SECRET not in repr(resolver)


def test_no_core_module_resolves_a_reference_to_material() -> None:
    """`FR-071`, statically: resolution is adapter-side, and there are no adapters yet.

    Scanned over `inbound`, `identity`, `governance`, `audit`, `telemetry` and `contracts` — every
    directory a request currently passes through. `secrets/` itself is excluded: defining the port
    is what it is for.
    """
    scanned = ("inbound", "identity", "governance", "audit", "telemetry", "contracts", "messages")
    offenders: list[str] = []
    for directory in scanned:
        for source in sorted((_SRC / directory).rglob("*.py")):
            text = source.read_text(encoding="utf-8")
            for token in (
                "material_for(",
                "SecretResolver",
                "resolve_secret",
                "os.environ",
                "getenv",
            ):
                if token in text:
                    offenders.append(f"{directory}/{source.name}: {token}")
    assert not offenders, offenders


def test_no_module_reads_material_from_the_environment_or_a_file() -> None:
    """The other way material arrives without a port: an env var or a bundled file."""
    forbidden = re.compile(
        r"os\.environ|os\.getenv|getenv\(|dotenv|open\(\s*['\"].*(?:key|secret|token|cred)"
    )
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if forbidden.search(line.split("#", 1)[0]):
                offenders.append(f"{source.relative_to(_SRC)}:{number}: {line.strip()}")
    assert not offenders, offenders


def test_the_reference_is_usable_as_a_key_without_a_value_existing() -> None:
    """The positive half: opacity must not make the type useless."""
    a = secret_ref_for(ChannelId.SLACK)
    b = secret_ref_for(ChannelId.SLACK)
    assert a == b
    assert a != secret_ref_for(ChannelId.WHATSAPP)
    # Hashed through a helper taking ``object``: the model is frozen and therefore hashable, and
    # this is the shape that lets a reference be a lookup key without a value existing to compare.
    assert _hash_of(a) == _hash_of(b)
    assert _hash_of(a) != _hash_of(secret_ref_for(ChannelId.WHATSAPP))
