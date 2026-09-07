"""A statistic that cannot say how it was produced is a number with no provenance — `P-2`.

**`MetricStatistics` used to say it carried a metric's normal *"as `002`/`003` measured
it"*, and neither seam produces one.** Measured on 2026-08-27: the word *mean* appears in
those two packages only in prose; `002` asks for a figure over a WINDOW and exposes no
statistic over a SERIES; `003` derives between exactly TWO values. **Prose attributing a
figure to a source without the capability** is the class this loop hunts, and it was
sitting in the socket built to receive that very figure.

**And the classic pair was not what the owner's baseline authorizes.** Its second
detection level — `robust_statistics`, `enabled: true`, `priority: second` — names
`rolling_median`, `median_absolute_deviation`, `robust_z_score` and five more. **Robust
centre and dispersion, and not one of them is a mean or a standard deviation.**

So the fields are `centre` and `dispersion`, each record NAMES THE METHOD that produced
it, and the name is checked against **his document** rather than a list copied here.

## What this file does NOT decide

**Which method this feature will use.** That belongs to the specification that builds the
second level, and inventing it here would be this package choosing a detection method on
the owner's behalf. Until it is chosen, no statistic is constructed, magnitude keeps
answering `None`, and the finding stays not prioritisable — which is the same shape `007`
uses for the labels it may not write.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from insights_prioritisation.contracts import PriorityContractViolation
from insights_prioritisation.score import components
from insights_prioritisation.score.components import (
    DECLARED_METHODS,
    MagnitudeZScore,
    MetricStatistics,
    declared_methods,
)

pytestmark = pytest.mark.contract

#: The module whose binding is under test, located from the reader it exports rather than
#: by a path spelled here: a path written twice ages, and this file is about exactly that.
BASELINE_READER_MODULE = Path(components.__file__)


def test_there_are_methods_to_check() -> None:
    """**The premise.** An empty set would make every refusal below fire for the wrong reason."""
    assert DECLARED_METHODS, (
        "no detection method could be read from the baseline, so this package cannot tell "
        "an authorized statistic from an invented one"
    )
    assert "median_absolute_deviation" in DECLARED_METHODS, (
        f"the baseline's second level no longer declares the robust dispersion this socket "
        f"was rebuilt around: {sorted(DECLARED_METHODS)}"
    )


def test_the_methods_are_read_and_a_correct_literal_copy_fails_this(tmp_path: Path) -> None:
    """**THIS IS THE NODE A CORRECT LITERAL COPY FAILS.**

    The premise above used to carry this title, and it was the one node in this file that did
    NOT measure the property it named. Every node here read the same module constant, so none
    could tell a reading from a copy.

    **Measured: replacing the whole reader with a correct literal copy of the eight methods
    left the package at 255 passed and nothing bit.**

    A reader answers whatever document it is handed. A literal answers the same to both,
    however right the copy is — which is exactly why the copy has to be CORRECT for this node
    to mean anything: a wrong copy is caught by the premise above, and a right one only here.

    The shape is `007`'s, applied rather than relearned: *the node a correct literal fails*.
    """
    other = tmp_path / "another-baseline.yaml"
    other.write_text(
        "proactive_insights:\n"
        "  detection_levels:\n"
        "    robust_statistics:\n"
        "      methods:\n"
        "        - a_method_his_baseline_does_not_name\n",
        encoding="utf-8",
    )

    from_his = declared_methods()
    from_other = declared_methods(other)

    assert from_other == {"a_method_his_baseline_does_not_name"}, (
        f"the reader did not answer the document it was handed: {sorted(from_other)}; a literal "
        "copy answers the same set whatever document it is given"
    )
    assert from_his != from_other, (
        "two different documents produced the same methods, so nothing here is being read"
    )
    assert from_his == DECLARED_METHODS, (
        "the module constant is not what the reader answers for his baseline, so the constant "
        "came from somewhere else"
    )


def test_the_constant_production_reads_is_bound_by_calling_the_reader() -> None:
    """**The reader became drivable and the constant did not, which is where production reads.**

    `MetricStatistics` validates against `DECLARED_METHODS`, the module constant — it never
    calls the reader. So making the reader drivable held the reader, and left the one value
    the production path actually consults free to be a literal.

    **Measured: replacing that single binding with a correct literal copy of the eight
    methods left the package at 259 passed and nothing bit.**

    ## Why the node above did not catch it, spelled out because the message nearly did

    It asserts `from_his == DECLARED_METHODS` and says *"the constant came from somewhere
    else"*. A correct literal copy IS somewhere else — and it passes, because the comparison
    is against what the reader answers for his document TODAY, and a correct copy agrees with
    that **by construction**.

    It would bite the day he edits the baseline: the reader answers the new set, the literal
    answers the old one. But **"later" depends on an event outside this repository**, and the
    rule this house follows is that a correct literal copy fails NOW.

    ## So this reads the CODE, not the value

    The binding must be a CALL to the reader. A set literal, a `frozenset(...)` of literals,
    or anything that is not that call is refused — the same move as the reach sweep one file
    over: **look at what the module does, not at what it ends up equal to.**
    """
    module = ast.parse(BASELINE_READER_MODULE.read_text(encoding="utf-8"))

    bindings = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.AnnAssign | ast.Assign)
        for target in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
        if isinstance(target, ast.Name) and target.id == "DECLARED_METHODS"
    ]
    assert len(bindings) == 1, (
        f"DECLARED_METHODS is bound {len(bindings)} times; with more than one, a node reading "
        "the first says nothing about the value the module ends up with"
    )

    value = bindings[0].value
    assert value is not None, "DECLARED_METHODS is declared without a value"
    assert isinstance(value, ast.Call), (
        f"DECLARED_METHODS is bound to {type(value).__name__} and not to a call; a literal "
        "copy answers his baseline correctly today and stops answering the day he edits it"
    )
    assert isinstance(value.func, ast.Name) and value.func.id == "declared_methods", (
        f"DECLARED_METHODS is bound by calling {ast.unparse(value.func)}, which is not the "
        "reader this file drives; whatever that call returns is not what any node measured"
    )
    assert not value.args and not value.keywords, (
        "the binding passes an argument to the reader, so the constant is read from a document "
        f"this file never checked: {ast.unparse(value)}"
    )


def test_the_binding_scan_would_catch_a_literal() -> None:
    """**Proof the scan bites**, over source this file parses rather than over the module.

    A node asserting *the binding is a call* while the binding is a call is green for two
    different reasons and cannot tell them apart. This is the second reason, measured: the
    two shapes a literal copy would actually take are fed to the same test and must both be
    rejected.
    """
    for source in (
        "DECLARED_METHODS: Final[frozenset[str]] = frozenset({'a', 'b'})\n",
        "DECLARED_METHODS = {'a', 'b'}\n",
    ):
        bound = ast.parse(source).body[0]
        assert isinstance(bound, ast.AnnAssign | ast.Assign)
        value = bound.value
        called_the_reader = (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "declared_methods"
        )
        assert not called_the_reader, f"the scan accepts a literal binding: {source.strip()}"


def test_a_document_the_reader_cannot_use_answers_the_empty_set(tmp_path: Path) -> None:
    """**Failing closed, driven.** An unreadable baseline must not silently authorize anything.

    Four shapes, each a different way a document can be useless, and every one must answer the
    empty set rather than guess — because the empty set is what makes `MetricStatistics` refuse.
    """
    assert declared_methods(tmp_path / "not-there.yaml") == frozenset()

    for name, text in (
        ("not-a-mapping.yaml", "- just\n- a\n- list\n"),
        ("no-levels.yaml", "proactive_insights:\n  something_else: true\n"),
        (
            "methods-not-a-list.yaml",
            "proactive_insights:\n"
            "  detection_levels:\n"
            "    robust_statistics:\n"
            "      methods: all\n",
        ),
    ):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        assert declared_methods(path) == frozenset(), name


def test_neither_mean_nor_standard_deviation_is_an_authorized_method() -> None:
    """**The finding, asserted rather than remembered.**

    The socket asked for the textbook pair while his baseline authorized robust ones. If a
    future baseline names them, this node goes red and the rebuild was for nothing — which
    is worth knowing loudly rather than discovering in a message.
    """
    classic = {"mean", "average", "standard_deviation", "stddev", "variance"}
    overlap = sorted(classic & DECLARED_METHODS)
    assert not overlap, (
        f"the baseline now authorizes {overlap}; the fields and this file were rebuilt on the "
        "premise that it authorizes only robust methods"
    )


@pytest.mark.parametrize("method", sorted(DECLARED_METHODS))
def test_every_method_the_baseline_declares_is_accepted(method: str) -> None:
    """Each one, individually — so a validator narrowed by hand fails naming the method."""
    statistic = MetricStatistics(centre=Decimal("748"), dispersion=Decimal("315"), method=method)
    assert statistic.method == method


@pytest.mark.parametrize("method", ["mean", "standard_deviation", "", "AVG", "rolling"])
def test_a_method_the_baseline_does_not_declare_is_refused(method: str) -> None:
    """**Never invented, and the refusal names what IS authorized.**

    `rolling` is in the list on purpose: it is a prefix of two declared methods, so a
    validator matching loosely would accept it.
    """
    with pytest.raises(PriorityContractViolation, match="not a method the baseline declares"):
        MetricStatistics(centre=Decimal("1"), dispersion=Decimal("1"), method=method)


def test_the_classic_pair_is_gone_from_the_shape() -> None:
    """The names were half the false claim; removing the docstring alone would leave it.

    A record still called `mean` would keep inviting a mean, whatever the docstring says.
    """
    fields = set(MetricStatistics.__dataclass_fields__)
    assert fields == {"centre", "dispersion", "method"}, fields


def test_magnitude_still_answers_none_because_no_method_was_chosen() -> None:
    """**The honest state, and it did not change with this repair.**

    Which method to use is the new specification's decision. Until it exists no statistic is
    registered, so the component is absent rather than invented — and the day one is
    registered, this node goes red and says so.
    """
    reader = MagnitudeZScore()
    assert reader.statistics == {}, (
        f"a statistic was registered without a method being chosen: {reader.statistics}"
    )

    class _Figure:
        value = Decimal("100")

    class _Finding:
        rule_id = "r-new-trials-percentage-change"
        figure = _Figure()

    assert reader(_Finding()) is None


def test_a_registered_statistic_would_make_magnitude_answer() -> None:
    """**Proof the reader is wired to the pair it now names**, driven rather than described.

    Without this, `None` could be coming from the reader ignoring `centre` and `dispersion`
    entirely — green for the wrong reason. The numbers here are this node's own arithmetic
    and are asserted as such, not as anything the warehouse said.
    """
    statistic = MetricStatistics(
        centre=Decimal("100"), dispersion=Decimal("10"), method=sorted(DECLARED_METHODS)[0]
    )
    reader = MagnitudeZScore(statistics={"r-x": statistic})

    class _Figure:
        value = Decimal("130")

    class _Finding:
        rule_id = "r-x"
        figure = _Figure()

    assert reader(_Finding()) == Decimal("3")


def test_a_dispersion_of_zero_answers_none_rather_than_dividing() -> None:
    """A metric that never moves has no *outside its normal*, and division by it is undefined."""
    statistic = MetricStatistics(
        centre=Decimal("100"), dispersion=Decimal("0"), method=sorted(DECLARED_METHODS)[0]
    )
    reader = MagnitudeZScore(statistics={"r-x": statistic})

    class _Figure:
        value = Decimal("130")

    class _Finding:
        rule_id = "r-x"
        figure = _Figure()

    assert reader(_Finding()) is None
