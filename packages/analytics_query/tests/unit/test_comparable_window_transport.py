"""The reader consumes `001`'s complete window — ADR 0016.

``window_from_decision`` was always right and was always refusing, because the
decision it read could only carry half a window. ADR 0016 repaired the transport
upstream; this file guards the reader's half of the seam.

**What changed here is what can be read, not what is accepted.** The reader now
recognises ``chosen_because`` — `001`'s own name for the reason, the one its
coverage gate has always used — alongside the two names it already accepted. All
four parts are still required, and a bare range is still refused.

That distinction is the whole design. Widening what is *accepted* would have hidden
the loss: a window without its reason reads as a choice somebody made rather than a
constraint the data imposed, and a consumer shown one has no way to tell that the
basis went missing. Widening what can be *read* fixes the name mismatch and leaves
the strictness where it was.

**Nothing is defaulted, derived or recomputed.** Not the reason, not the sources,
not the dates. If `001` stated them, they are reported as given; if it did not,
the window refuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef
from semantic_catalog.contracts.reason_codes import ReasonCode, outcome_for
from semantic_catalog.validation.decision import (
    CatalogDecision,
    Subject,
    SubjectKind,
)
from semantic_catalog.validation.decision import (
    ComparableWindow as CatalogComparableWindow,
)

from analytics_query.contracts._base import ContractViolation
from analytics_query.contracts.comparable_window import (
    REASON_ATTRIBUTES,
    ComparableWindow,
    window_from_decision,
)
from analytics_query.contracts.reason_codes import AnalyticsReasonCode

pytestmark = pytest.mark.unit

JULY = (date(2026, 7, 1), date(2026, 7, 31))
REASON = "janela comparável entre appstore, playstore: interseção das coberturas observadas"
SOURCES = ("appstore", "playstore")


def _decision(window: CatalogComparableWindow | None = None) -> CatalogDecision:
    code = ReasonCode.REQUEST_ALLOWED
    return CatalogDecision(
        decision_id="dec-1",
        policy_version="pol-1",
        catalog_release_id="r-1",
        evaluated_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
        outcome=outcome_for(code),
        reason_code=code,
        message_pt_br="decisão de teste",
        subject=Subject(kind=SubjectKind.REQUEST, id="req-1"),
        evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="r-1"),),
        comparable_window=window,
    )


@dataclass(frozen=True)
class _Carrier:
    """A decision-shaped stand-in, for the shapes a real decision now rejects.

    ``CatalogDecision.comparable_window`` is typed to `001`'s ``ComparableWindow``
    since ADR 0016, so a bare range or a partially stated window can no longer be
    put on one — which is itself the repair working. The reader is nonetheless
    duck-typed on purpose, and its tolerance to older and malformed shapes is
    exactly what these cases exercise.
    """

    comparable_window: object


def _catalog_window() -> CatalogComparableWindow:
    return CatalogComparableWindow(
        start=JULY[0], end=JULY[1], sources=SOURCES, chosen_because=REASON
    )


# --- the governed window is read whole -------------------------------------------


def test_the_complete_catalog_window_is_read() -> None:
    """The end of the defect: four parts in, four parts out."""
    window = window_from_decision(_decision(_catalog_window()))

    assert window is not None
    assert (window.start, window.end) == JULY
    assert window.sources == SOURCES
    assert window.reason == REASON


def test_the_reason_is_carried_byte_for_byte() -> None:
    """Governed wording. Not summarised, not re-cased, not truncated."""
    window = window_from_decision(_decision(_catalog_window()))
    assert window is not None
    assert window.reason == REASON
    assert len(window.reason) == len(REASON)


def test_nothing_is_recomputed_from_the_dates() -> None:
    """A derived reason would be plausible and wrong. There is no derivation.

    The stated reason names both sources and the intersection; a reader that
    composed one from the dates would produce a different sentence, and the
    difference is what nobody could detect.
    """
    stated = _catalog_window()
    window = window_from_decision(_decision(stated))
    assert window is not None
    assert window.reason == stated.chosen_because
    assert window.sources == stated.sources


def test_a_single_source_window_reads_whole() -> None:
    single = CatalogComparableWindow(
        start=JULY[0], end=JULY[1], sources=("appstore",), chosen_because="cobertura completa"
    )
    window = window_from_decision(_decision(single))
    assert window is not None
    assert window.sources == ("appstore",)


# --- what the reader will answer to ------------------------------------------------


def test_the_accepted_reason_names_are_declared_and_ordered() -> None:
    """``chosen_because`` first: it is what the upstream type is actually called."""
    assert REASON_ATTRIBUTES == ("chosen_because", "reason", "rationale")


@dataclass(frozen=True)
class _Stated:
    start: date
    end: date
    sources: tuple[str, ...]


@pytest.mark.parametrize("attribute", REASON_ATTRIBUTES)
def test_each_accepted_reason_name_is_read(attribute: str) -> None:
    """The older two are kept so no consumer of an earlier shape breaks."""
    stated = type("Window", (_Stated,), {})(start=JULY[0], end=JULY[1], sources=SOURCES)
    object.__setattr__(stated, attribute, REASON)

    window = window_from_decision(_Carrier(stated))  # type: ignore[arg-type]
    assert window is not None
    assert window.reason == REASON


# --- a bare range is still insufficient ---------------------------------------------


def test_a_bare_range_remains_insufficient() -> None:
    """The behaviour that made the defect visible. Unchanged.

    Weakening this would have hidden the loss instead of repairing it.
    """

    @dataclass(frozen=True)
    class BareRange:
        start: date
        end: date

    with pytest.raises(ContractViolation) as refusal:
        window_from_decision(_Carrier(BareRange(start=JULY[0], end=JULY[1])))  # type: ignore[arg-type]
    assert refusal.value.code is AnalyticsReasonCode.RESULT_SHAPE_MISMATCH


@pytest.mark.parametrize(
    "incomplete",
    [
        pytest.param({"sources": ()}, id="no-sources"),
        pytest.param({"chosen_because": ""}, id="no-reason"),
    ],
)
def test_a_partially_stated_window_refuses(incomplete: dict[str, object]) -> None:
    """Never completed on a guess, whichever part is absent."""

    @dataclass(frozen=True)
    class Partial:
        start: date = JULY[0]
        end: date = JULY[1]
        sources: tuple[str, ...] = SOURCES
        chosen_because: str = REASON

    with pytest.raises(ContractViolation):
        window_from_decision(_Carrier(Partial(**incomplete)))  # type: ignore[arg-type]


def test_a_decision_stating_no_window_reports_none() -> None:
    """``None`` is not an empty window: an empty one asserts a comparison over no days."""
    assert window_from_decision(_decision()) is None


def test_none_is_not_an_empty_window() -> None:
    """Stated as a contrast, because the two are easy to conflate downstream."""
    assert window_from_decision(_decision()) is None
    assert window_from_decision(_decision(_catalog_window())) is not None


# --- the reader is not on the execution path -----------------------------------------


def test_the_reader_takes_only_a_decision() -> None:
    """No adapter, no policy, no ledger. Reading a window costs nothing.

    Asserted because the repair touched a module `002` publishes, and the thing
    worth proving is that nothing about ordering or cost moved with it.
    """
    import inspect

    assert list(inspect.signature(window_from_decision).parameters) == ["decision"]


def test_the_returned_window_is_002s_own_type() -> None:
    """Converted at this boundary, as `002` owns. Not passed through raw."""
    window = window_from_decision(_decision(_catalog_window()))
    assert isinstance(window, ComparableWindow)
    assert not isinstance(window, CatalogComparableWindow)


def test_the_converted_window_is_deterministic() -> None:
    first = window_from_decision(_decision(_catalog_window()))
    second = window_from_decision(_decision(_catalog_window()))
    assert first is not None
    assert second is not None
    assert first.model_dump_json() == second.model_dump_json()


# --- 002 composes no window of its own — ADR 0016 -------------------------------------


def test_no_analytics_query_module_composes_a_comparable_window() -> None:
    """`002` converts; it does not compose.

    ``ComparableWindow(...)`` appears exactly once in this package — inside
    ``window_from_decision``, building the converted value from parts the upstream
    decision stated. Anywhere else it would be a window this feature invented, and
    the part it would have to invent is the governed reason.
    """
    import ast
    import inspect
    from pathlib import Path

    import analytics_query

    src = Path(inspect.getfile(analytics_query)).resolve().parent
    sites: list[str] = []
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        sites += [
            path.relative_to(src).as_posix()
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ComparableWindow"
        ]
    # By file rather than by line: pinning a line number would make this fail on
    # a docstring edit, and a guard that cries wolf gets deleted.
    assert sites == ["contracts/comparable_window.py"], sites


def test_the_reader_derives_no_part_of_the_window() -> None:
    """No min, max, sort, intersection or join on the conversion path.

    Deriving the window here would produce something plausible that occasionally
    differs from what `001` actually validated — and the caller would be told the
    wrong basis for a number computed on a different one.
    """
    import ast
    import inspect

    from analytics_query.contracts import comparable_window as module

    tree = ast.parse(inspect.getsource(module))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & {"min", "max", "sorted", "intersection", "range"}
