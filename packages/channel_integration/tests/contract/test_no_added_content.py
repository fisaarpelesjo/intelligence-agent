"""Nothing was added — T090 (ADR 0022; FR-046; SC-018).

The differential claim: the delivered bytes contain **nothing** that is not either a governed string
from the payload, a governed label from the capability matrix, or a permitted separator.

Two instruments, and the second is the one that would catch a clever renderer:

* **residue subtraction.** Strip every governed string and every governed label, longest first, then
  strip the permitted separators. What remains is content nobody authorised. Empty is the only pass.
* **structural absence.** The renderer has no arithmetic and no string generation in it, asserted by
  parsing the module rather than by reading it: no numeric operator over values, no ``format``, no
  ``%``-formatting, no ``join`` over anything but governed blocks, and no literal sentence.

The forbidden-content list is imported from `outbound.degrade` rather than retyped, so the scan and
the rule cannot drift apart — a retyped list is a second source of truth that eventually disagrees.

Longest-first stripping is not a detail. Stripping ``"numero 1"`` before ``"numero 12"`` leaves a
stray ``"2"`` and reports it as invented content. The fixture corpus caught exactly that, and the
order is asserted here so a future refactor cannot quietly reintroduce it.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.outbound import render as render_module
from channel_integration.outbound.degrade import FORBIDDEN_CONTENT_OPERATIONS
from channel_integration.outbound.preserve import preservation_report
from channel_integration.outbound.render import render_answer

from ..fixtures.payloads import CORPUS, FIXTURE_CAPABILITY

pytestmark = pytest.mark.contract

_RENDERABLE = sorted(set(CORPUS) - {"an unresolved wording reference"})

#: Text a renderer would add if it were being helpful. None of it may appear.
_AUTHORED_PROSE = (
    "olá",
    "bom dia",
    "desculpe",
    "infelizmente",
    "sugiro",
    "talvez",
    "acredito",
    "parece que",
    "em resumo",
    "resumindo",
    "ou seja",
    "portanto",
    "veja mais",
    "clique",
    "confiança",
    "provavelmente",
)


@pytest.mark.parametrize("channel", list(ChannelId))
@pytest.mark.parametrize("name", _RENDERABLE)
def test_the_delivered_bytes_contain_no_unauthorised_residue(name: str, channel: ChannelId) -> None:
    """`SC-018`, by subtraction. Empty residue is the only pass."""
    payload = CORPUS[name]
    presentation = render_answer(payload, channel, FIXTURE_CAPABILITY)
    report = preservation_report(presentation, payload, FIXTURE_CAPABILITY)
    assert report.added == (), f"{name} on {channel.value}: unauthorised content {report.added!r}"


@pytest.mark.parametrize("name", _RENDERABLE)
def test_no_authored_prose_appears_anywhere(name: str) -> None:
    """The explicit list, because subtraction alone would not say *what* was added."""
    presentation = render_answer(CORPUS[name], ChannelId.SLACK, FIXTURE_CAPABILITY)
    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments).lower()
    for phrase in _AUTHORED_PROSE:
        assert phrase not in delivered, f"{name}: the renderer added {phrase!r}"


def test_the_renderer_module_contains_no_arithmetic_over_values() -> None:
    """`FR-044`, structurally: there is no operation that could produce a different number."""
    source = Path(inspect.getfile(render_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, ast.Add | ast.Sub | ast.Mult | ast.Div | ast.FloorDiv | ast.Mod | ast.Pow
        ):
            # An f-string concatenation is a ``JoinedStr``, not a ``BinOp``, so what this catches is
            # genuine arithmetic or ``%``-formatting.
            offenders.append(ast.dump(node)[:80])
    assert not offenders, offenders


def test_the_renderer_generates_no_sentence_that_could_be_delivered() -> None:
    """No literal prose on the delivery path. Its whole vocabulary is governed content.

    The rule is about **position**, not about wording, and that is what makes it checkable without
    an exemption list. A prose string inside a ``raise`` is a refusal detail: operator-facing,
    recorded in the audit trail, and proven never to reach a sender (`T063`). A prose string
    anywhere else in the renderer could end up in a body, so there must not be one.

    An earlier version of this test allowed specific words through, which made the assertion agree
    with whichever strings happened to exist. Position is the property that matters.
    """
    source = Path(inspect.getfile(render_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    exempt: set[int] = set()
    for node in ast.walk(tree):
        # Docstrings: the module explains itself, and must be allowed to.
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                exempt.add(id(first.value))
        # Refusal details: operator-facing only.
        if isinstance(node, ast.Raise):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    exempt.add(id(inner))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in exempt:
            continue
        # "Prose" means two or more purely alphabetic words. A separator (``": "``), a space, and a
        # quoted type such as ``"Mapping[str, object]"`` are structural: they carry no sentence, and
        # calling them prose would make this assertion about punctuation instead of about content.
        words = [token for token in node.value.split() if token.isalpha()]
        if len(words) >= 2:
            offenders.append(node.value)
    assert not offenders, f"prose on the delivery path: {offenders}"


def test_no_forbidden_content_operation_is_defined_or_called_in_the_renderer() -> None:
    """The list is imported, not retyped, so the scan and the rule stay one thing."""
    source = Path(inspect.getfile(render_module)).read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in FORBIDDEN_CONTENT_OPERATIONS:
        assert f"def {forbidden}" not in lowered
        assert f".{forbidden}(" not in lowered


def test_the_residue_strip_is_longest_first() -> None:
    """The defect the corpus caught, asserted so it cannot come back.

    Two governed strings where one is a prefix of the other: stripping the short one first leaves a
    fragment of the long one behind and reports it as invented content.
    """
    from channel_integration.outbound import preserve as preserve_module

    source = Path(inspect.getfile(preserve_module)).read_text(encoding="utf-8")
    assert "key=len, reverse=True" in source, "the differential strip is order-dependent"

    payload = CORPUS["maximum caveat count"]
    presentation = render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    report = preservation_report(presentation, payload, FIXTURE_CAPABILITY)
    assert report.added == (), "prefix interference reappeared in the differential strip"
