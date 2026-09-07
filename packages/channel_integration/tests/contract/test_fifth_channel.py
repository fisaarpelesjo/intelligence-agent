"""T129 — a fifth channel needs the two declared ports, and touches nothing upstream (`SC-042`).

The claim under test is an extensibility claim, and it splits into two halves that are worth
proving separately because only one of them is unconditional.

## The unconditional half: upstream never learns a channel exists

`001`, `002` and `003` contain **no channel-specific surface at all**. Measured 2026-08-19 across
all three packages' `src/`: one occurrence of any channel vocabulary, in
`analytics_interaction/answer/assemble.py`, and it is a docstring asserting the *absence* of a
webhook field. So adding a fifth channel is a zero-diff event upstream by construction, not by
discipline, and this file asserts it by scanning rather than by citing.

## The conditional half: `ChannelId` is closed, and closed is the point

A fifth channel does require declaring things inside `004`, and `contracts/descriptor.py` says
exactly which six: "a descriptor, a verification scheme, normalisation rules, a `D-28` capability
entry, a delivery adapter and a credential record". That is not a gap in `SC-042`; it is the
fail-closed rule doing its job. An open registry would mean a channel could exist without a declared
credential record, and `FR-097` exists precisely so no file, flag or environment variable can bring
one into being. `test_the_declared_extension_points_all_exist` reads that list out of the contract
rather than restating it, so a seventh extension point cannot appear unannounced.

So what `SC-042` actually promises, and what is asserted below, is that the **pipeline** is
channel-agnostic: conversion, identity, rendering, preservation, delivery and audit contain no
per-channel branch. The measured per-channel sites are three registries and four adapter modules,
and each adapter is one channel's provider seam — which is what an adapter is for.

## The synthetic channel

`_FifthChannelScheme` and `_FifthChannelDelivery` implement `VerificationScheme` and `DeliveryPort`
and nothing else. They are declared here rather than in `tests/fixtures/` deliberately: they exist
to answer "is the port surface sufficient?", and a fixture module shared with other tests would
invite them to grow a second purpose and stop answering it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from channel_integration.contracts.audit import DetailClass
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.delivery.ports import DeliveryPort, FragmentReceipt
from channel_integration.inbound.schemes import (
    VerificationMaterial,
    VerificationOutcome,
    VerificationScheme,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from channel_integration.contracts.delivery import ChannelDestination
    from channel_integration.contracts.presentation import RenderedPresentation

pytestmark = pytest.mark.contract


def _package_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "channel_integration").is_dir():
            return parent
    raise AssertionError("package root not found")


_PACKAGE = _package_root()
_SRC = _PACKAGE / "src" / "channel_integration"
_REPO = _PACKAGE.parents[1]
_UPSTREAM = ("semantic_catalog", "analytics_query", "analytics_interaction")

#: Channel vocabulary, matched case-insensitively. Deliberately the provider names rather than the
#: enum members: an upstream package that learned a channel exists would most likely say so in the
#: provider's own words.
_CHANNEL_WORDS = re.compile(r"slack|telegram|whatsapp|webhook", re.IGNORECASE)

#: The one upstream occurrence, measured 2026-08-19. Pinned rather than excluded by pattern: an
#: allowance that matched by shape would silently cover a second, real occurrence.
_KNOWN_UPSTREAM_MENTION = (
    "analytics_interaction/answer/assemble.py",
    "No format, no markup, no length limit, no thread id, no webhook field, no",
)

#: The `004` modules that legitimately name a specific channel: three closed registries and the
#: four provider adapters. Anything else naming one is a per-channel branch in the pipeline, which
#: is what `SC-042` forbids.
_PERMITTED_CHANNEL_SITES = frozenset(
    {
        "contracts/descriptor.py",
        "inbound/verify.py",
        "compliance/readiness.py",
        "adapters/whatsapp/delivery.py",
        "adapters/slack/delivery.py",
        "adapters/telegram/delivery.py",
        "adapters/generic/delivery.py",
    }
)


class _FifthChannelScheme:
    """A synthetic channel's verification, implementing the declared port and nothing else."""

    name = "fifth-channel-scheme"
    provides_signed_timestamp = False

    def verify(
        self,
        body: bytes,
        headers: tuple[tuple[str, str], ...],
        material: VerificationMaterial,
    ) -> VerificationOutcome:
        """Agrees when the body was signed with the active material, byte for byte."""
        presented = dict(headers).get("x-fifth-signature", "")
        expected = material.active + ":" + str(len(body))
        if presented == expected:
            return VerificationOutcome.verified()
        return VerificationOutcome.failed(DetailClass.SIGNATURE_MISMATCH)

    def signed_timestamp(self, headers: tuple[tuple[str, str], ...]) -> int | None:
        """None: this scheme signs no timestamp, which the replay rule must handle on its own."""
        return None


class _FifthChannelDelivery:
    """A synthetic channel's transport, implementing the declared port and nothing else."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, ...]] = []

    def send(
        self,
        presentation: RenderedPresentation,
        destination: ChannelDestination,
    ) -> tuple[DeliveryOutcome, tuple[FragmentReceipt, ...]]:
        bodies = tuple(fragment.body for fragment in presentation.fragments)
        self.sent.append(bodies)
        receipts = tuple(
            FragmentReceipt(index=index, accepted=True, indeterminate=False)
            for index, _ in enumerate(bodies)
        )
        return DeliveryOutcome.DELIVERED, receipts


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_the_two_declared_ports_are_the_whole_surface_a_channel_implements() -> None:
    """Structural conformance, checked against the ports themselves rather than described."""
    assert isinstance(_FifthChannelScheme(), VerificationScheme)
    assert isinstance(_FifthChannelDelivery(), DeliveryPort)


def test_the_synthetic_channel_verifies_and_delivers_without_touching_governed_code() -> None:
    """The ports are sufficient: a channel can be driven end to end through them alone.

    Not vacuous — the scheme genuinely refuses a body it did not sign, so this exercises both
    outcomes rather than proving that a stub returns what a stub returns.
    """
    scheme = _FifthChannelScheme()
    material = VerificationMaterial(active="fifth-channel-material", retired=())
    body = b'{"text": "quantas instalacoes?"}'
    good = (("x-fifth-signature", "fifth-channel-material:" + str(len(body))),)

    assert scheme.verify(body, good, material).ok
    assert not scheme.verify(body + b" ", good, material).ok, (
        "the scheme accepted a body it did not sign, so this test proves nothing about either port"
    )
    assert scheme.signed_timestamp(good) is None


def test_no_upstream_package_names_a_channel() -> None:
    """The zero-diff half of `SC-042`, scanned rather than cited.

    One occurrence is permitted and it is pinned by file **and** by line text: a docstring in `003`
    asserting that no webhook field exists. Excluding it by pattern instead would have excluded a
    real second occurrence too.
    """
    offenders: list[str] = []
    for package in _UPSTREAM:
        root = _REPO / "packages" / package / "src"
        if not root.is_dir():
            continue
        for source in _python_files(root):
            relative = source.relative_to(root).as_posix()
            for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
                if not _CHANNEL_WORDS.search(line):
                    continue
                known = (
                    relative == _KNOWN_UPSTREAM_MENTION[0] and _KNOWN_UPSTREAM_MENTION[1] in line
                )
                if not known:
                    offenders.append(f"{relative}:{number}: {line.strip()}")
    assert not offenders, (
        f"an upstream package names a channel: {offenders}. A fifth channel would then be a diff "
        "in a package that must not know channels exist"
    )


def test_the_known_upstream_mention_is_still_there_and_still_says_nothing_exists() -> None:
    """The allowance above is held to the line it allows.

    If `003` ever deletes or rewrites that docstring, the allowance stops describing anything and
    would quietly start covering whatever appeared at the same path. This fails first instead.
    """
    path = _REPO / "packages" / "analytics_interaction" / "src" / _KNOWN_UPSTREAM_MENTION[0]
    assert path.is_file(), f"{path} moved; re-measure the upstream scan"
    assert _KNOWN_UPSTREAM_MENTION[1] in path.read_text(encoding="utf-8"), (
        "the pinned upstream line changed, so the allowance no longer describes what it allows"
    )


def test_only_the_registries_and_the_adapters_name_a_channel() -> None:
    """The pipeline is channel-agnostic. Measured on `ChannelId.<MEMBER>` attribute access.

    Matched with `ast` rather than by text so a docstring naming a channel — this package is full of
    prose about Slack — is not mistaken for a branch on one.
    """
    offenders: dict[str, list[str]] = {}
    for source in _python_files(_SRC):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        named = sorted(
            {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "ChannelId"
            }
        )
        relative = source.relative_to(_SRC).as_posix()
        if named and relative not in _PERMITTED_CHANNEL_SITES:
            offenders[relative] = named
    assert not offenders, (
        f"these modules branch on a specific channel: {offenders}. A fifth channel would have to "
        "edit each one, which is the cost `SC-042` says it does not have"
    )


def test_every_permitted_site_actually_names_a_channel() -> None:
    """The allowlist above is held to reality from the other direction.

    A permitted entry that no longer names a channel is an allowance covering nothing, and an
    allowance covering nothing is how a scan's exclusion list grows past what it can justify.
    """
    stale: list[str] = []
    for relative in sorted(_PERMITTED_CHANNEL_SITES):
        source = _SRC / relative
        if not source.is_file():
            stale.append(f"{relative} (missing)")
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names = any(
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ChannelId"
            for node in ast.walk(tree)
        )
        declares = any(
            isinstance(node, ast.ClassDef) and node.name == "ChannelId" for node in ast.walk(tree)
        )
        # `contracts/descriptor.py` **declares** the enum rather than reading a member of it, which
        # the attribute scan cannot see. Measured while writing this node: without the second form
        # the declaring module reads as an allowance justifying nothing, which is the opposite of
        # true — it is the one site a fifth channel certainly edits.
        if not (names or declares):
            stale.append(f"{relative} (no longer names or declares a channel)")
    assert not stale, f"the permitted-site list has entries that justify nothing: {stale}"


def test_the_registries_are_total_over_the_enum() -> None:
    """Closed is only safe when it is also complete.

    Every declared channel must have a verification scheme and a credential record. A channel
    present in the enum and absent from either registry would be a channel with no way to verify a
    message or no way to be reported unready — both fail open in the direction that matters.
    """
    import channel_integration.compliance.readiness as readiness_module
    import channel_integration.inbound.verify as verify_module

    # Reached through the module namespace rather than imported, which is what lets this node
    # follow a registry whose VISIBILITY changes without following its NAME.
    #
    # **The scheme map stopped being private on 2026-08-28, and the reason is worth keeping.**
    # This comment used to say both registries were private *by design* — "publishing one so a
    # test could import it would widen the surface to suit the test", which was and is right.
    # What changed is not a test's convenience: `OD-20-A` split the readiness key, and the
    # INBOUND half has to ask which channels' schemes evaluate an instant. That is production
    # asking production. Reaching through an underscore to answer it would have been the
    # boundary crossing this repository refuses elsewhere, so the name became public rather
    # than the reach becoming sneaky.
    #
    # `_CHANNEL_CREDENTIAL` stays private: nothing outside its module asks it anything.
    verify_names = vars(verify_module)
    readiness_names = vars(readiness_module)
    assert "EXPECTED_SCHEME" in verify_names, "inbound.verify no longer declares EXPECTED_SCHEME"
    assert "_CHANNEL_CREDENTIAL" in readiness_names, (
        "compliance.readiness no longer declares _CHANNEL_CREDENTIAL"
    )

    schemes: Mapping[ChannelId, object] = verify_names["EXPECTED_SCHEME"]
    credentials: Mapping[ChannelId, object] = readiness_names["_CHANNEL_CREDENTIAL"]

    assert set(schemes) == set(ChannelId)
    assert set(credentials) == set(ChannelId)
    assert len(set(credentials.values())) == len(ChannelId), (
        "two channels share a credential record, so one could be enabled by the other's material"
    )


def test_the_declared_extension_points_all_exist() -> None:
    """`contracts/descriptor.py` states the cost of a fifth channel. It is held to that statement.

    Its docstring names six: "a descriptor, a verification scheme, normalisation rules, a `D-28`
    capability entry, a delivery adapter and a credential record — and **zero** changes to any
    upstream contract or to the canonical channel contracts (`FR-088`, asserted by T129)". This is
    that assertion, and it checks both halves: each of the six is a real place, and the zero holds.

    The list is read out of the docstring rather than restated, so a future edit that adds a seventh
    extension point without telling anyone fails here.
    """
    declaration = (_SRC / "contracts" / "descriptor.py").read_text(encoding="utf-8")
    for point in (
        "a descriptor",
        "a verification scheme",
        "normalisation rules",
        "capability entry",
        "a delivery adapter",
        "a credential record",
    ):
        assert point in declaration, (
            f"the descriptor contract no longer names {point!r} as an extension point, so this "
            "test is holding the code to a statement it stopped making"
        )
    assert "asserted by T129" in declaration, (
        "the descriptor contract no longer points at this file, so nothing asserts its claim"
    )

    for path in (
        _SRC / "contracts" / "descriptor.py",
        _SRC / "inbound" / "verify.py",
        _SRC / "inbound" / "normalise.py",
        _SRC / "governance" / "capabilities.py",
        _SRC / "compliance" / "readiness.py",
    ):
        assert path.is_file(), f"{path} is a declared extension point and it does not exist"

    adapters = sorted(path.parent.name for path in (_SRC / "adapters").rglob("delivery.py"))
    assert len(adapters) == len(ChannelId), (
        f"one adapter per channel, and no channel without one: found {adapters}"
    )
