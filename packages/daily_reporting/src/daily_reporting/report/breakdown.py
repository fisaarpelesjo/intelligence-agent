"""The breakdown's governed shape — `D-1302` (`OD-111`), `FR-1303`, `SC-1304`.

**Everything a breakdown needs that is a DECISION arrives here as data, and nothing in this
module is written by the package.** The cut, the label of each axis and the word for the tail
are all his: the cut by `OD-111`, the three words literally from the example contract he
approved. This module holds the SHAPE that carries them and the rule that validates it.

## Why the cut cannot be a literal, measured rather than argued

`packages/daily_reporting/tests/contract/test_the_loop_enumerates_nothing.py:41` carries
`ENUMERATED_TOTALS = (20, 5, 19)` and sweeps the package for those integers written down. A
`TOP_N = 5` here would go red on the first run — and that guard is right: a total written in
code is a total that stops matching the world without anyone noticing. The precedent for the
other direction is `declared_order`, which reaches `summarise` as a parameter read from
`report_governance/section_order.yaml`.

## What is validated, and why each check is a refusal rather than a default

A governed file that cannot be read must never become a silent default — that is the same
class as the readiness record answering for the silence it did not carry (`S-41`, one feature
over). So: a missing key refuses, a cut outside `1..MAXIMUM_LINES` refuses, an empty label
refuses. **None of them falls back to a number this module chose.**
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from ..view.reading import aggregate, partition_by, sample_size
from ..view.shape import ViewRow

__all__ = [
    "MAXIMUM_LINES",
    "BreakdownGovernance",
    "BreakdownGovernanceError",
    "UnavailableAxis",
    "unavailable_breakdowns_of",
]

#: The ceiling `SC-1304` puts on any breakdown: *"no breakdown emits more than ten lines"*.
#: It is a boundary on what the governed file may say, not the cut itself — the cut is his and
#: lives in the file. Ten is a rule of the specification; five is a decision of his.
MAXIMUM_LINES = 10


class BreakdownGovernanceError(ValueError):
    """The governed breakdown file cannot be trusted. Never silently replaced by a default."""


@dataclass(frozen=True, slots=True)
class UnavailableAxis:
    """An axis he asked for by name that no governed source carries — `FR-1316`, `F5`.

    ``column`` is the dimension id in the catalogue, ``label`` his word for the axis,
    ``reason_code`` the governed reason (`semantic/content/reason-messages.pt-BR.yaml`) that says
    why, ``source`` the source the reason is about, and ``kpis`` the indicators his contract says
    should carry the axis. **This package renders none of the reason's words**: the caller, who
    holds the reason-message registry, renders the sentence and hands it in as data.
    """

    column: str
    label: str
    reason_code: str
    source: str
    kpis: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BreakdownGovernance:
    """The cut and the words, as the governed file states them.

    ``axis_labels`` maps a SOURCE COLUMN NAME to his word for that axis. The key is the
    column because that is what the data carries; the value is his because that is what a
    person reads.
    """

    top_n: int
    axis_labels: tuple[tuple[str, str], ...]
    tail_label: str
    tail_noun: str = ""
    #: His word for a breakdown's total, `OD-122`. **This package reads it and never renders
    #: it**, and that is not an oversight: a report breakdown sits under a KPI line that already
    #: carries the figure, so opening it with a total would print the same number twice. The bot
    #: ANSWER has no such line above it, which is the whole reason the word was needed. Empty
    #: stays the declared absence for a document that states none.
    total_label: str = ""
    sample_floor: int = 0
    kpis: tuple[str, ...] = ()
    excluded_values: tuple[tuple[str, tuple[str, ...]], ...] = ()

    #: `OD-119`: the marker that opens an axis line, and the one that opens a value line. ONE
    #: and TWO of the same character — the hierarchy is a count of markers, not a depth of
    #: indentation, and he wrote both forms out.
    axis_marker: str = ""
    value_marker: str = ""

    #: `OD-119`: the icon each value of an axis carries, keyed by axis and then by the value AS
    #: THE SOURCE WRITES IT. A value absent from here renders with no icon.
    icons: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()

    #: `F5` (`FR-1316`, `OD-127`): the axes he asked for that no governed source carries, with
    #: the governed reason each one is refused under. Empty is the normal case.
    unavailable_axes: tuple[UnavailableAxis, ...] = ()

    #: `OD-144` (2026-09-06): the three words a RATE's split tail needs, and the per-axis plural
    #: it borrows. `sampled_qualifier` says the first tail line is only the parts that HAVE a
    #: sample; `withheld_label` names the second population; `withheld_value` is what stands
    #: where that population's rate would be, because the whole point of the floor is that no
    #: rate is asserted for them. **All three empty is the declared absence**: the tail then
    #: renders exactly as it did before `OD-144`, one line, which is also what a count's
    #: breakdown does because a count has no floor to withhold anything.
    sampled_qualifier: str = ""
    withheld_label: str = ""
    withheld_value: str = ""
    #: His plural for an axis, where his contract carries one. An axis absent from here falls
    #: back to `tail_noun`, which is governed too — never to a plural invented here. The same
    #: rule and the same reason as `ContributionGovernance.axis_plural`, which met the same
    #: missing word first.
    axis_plural: tuple[tuple[str, str], ...] = ()
    #: His SINGULAR for an axis — `OD-153`, 2026-09-06. The same shape, the same fallback and
    #: the same refusal as `axis_plural`, and it exists because a tail can count exactly one
    #: partition: the message he read named one partition with the word for many, and the file
    #: carried no other word for the renderer to reach for. The governed file states both
    #: numbers for every axis it names, and the loader refuses a file that names only one.
    axis_singular: tuple[tuple[str, str], ...] = ()

    def plural_for(self, column: str) -> str:
        """His plural for this axis, or the governed noun that stands in for any axis.

        Neither word is quoted here, and that is the guard working: a docstring naming one
        would copy a governed word into the package.

        **Still a call site of its own** — `OD-153` did not fold this into `noun_for`. Where a
        sentence names the other parts without counting them there is no number for a word to
        agree with, and asking a counted method for that answer would mean inventing a count.
        """
        for axis, word in self.axis_plural:
            if axis == column:
                return word
        return self.tail_noun

    def singular_for(self, column: str) -> str:
        """His singular for this axis, or **empty when he named none** — `OD-153`.

        Empty is the answer rather than a fallback, and the two differ: `plural_for` falls back
        to the governed noun because every axis needs a word for many, while a missing singular
        has no stand-in at all. Deriving one from the plural — trimming a letter, say — would be
        this package authoring his vocabulary one character at a time, which is the `S-44`
        refusal in miniature. `noun_for` is what decides what to do with the emptiness.
        """
        for axis, word in self.axis_singular:
            if axis == column:
                return word
        return ""

    def noun_for(self, column: str, count: int) -> str:
        """The word for ``count`` parts of this axis — **singular at exactly one** (`OD-153`).

        The two maps are consulted INDEPENDENTLY: a singular he stated for an axis is used at a
        count of one whether or not a plural stands beside it. That keeps this from asking one
        map for permission to read the other, and the loader is what refuses a file carrying
        half an axis.

        **The fallback is unchanged and it does not agree by count**, which is a measurement and
        not an oversight: an axis he named no word for falls back to `tail_noun`, and his
        vocabulary states no singular for that generic noun. So the fallback stands for one and
        for many alike until he gives one. Choosing a word here instead is exactly what `D-28`
        forbids, and it is the same refusal that kept one axis on the generic noun until he
        spoke.
        """
        if count == 1:
            singular = self.singular_for(column)
            if singular:
                return singular
        return self.plural_for(column)

    @property
    def splits_the_tail(self) -> bool:
        """Whether his file states the three words a split tail needs — `OD-144`.

        All three or none. Half the vocabulary would print a qualifier with nothing to qualify
        against, or a second population with no word saying what it is, and either is worse
        than the one line this replaces.
        """
        return all(
            word.strip()
            for word in (self.sampled_qualifier, self.withheld_label, self.withheld_value)
        )

    def unavailable_for(self, kpi: str) -> tuple[UnavailableAxis, ...]:
        """The unavailable axes his file names for ``kpi``, in the declared order."""
        return tuple(axis for axis in self.unavailable_axes if kpi in axis.kpis)

    def icon_for(self, column: str, value: str) -> str:
        """His icon for this value of this axis, or **empty when he named none**.

        Empty is the answer, not a placeholder. A value the governed file does not carry gets
        no symbol: deriving one from the name — a flag from a country's spelling, say — would
        be this package inventing a symbol for a value that came from the source, which is the
        `S-44` defect wearing a different hat. A country that enters the top five tomorrow
        arrives without an icon, and that is the behaviour rather than a gap to close.
        """
        for axis, by_value in self.icons:
            if axis != column:
                continue
            for named, icon in by_value:
                if named == value:
                    return icon
        return ""

    def __post_init__(self) -> None:
        # `int` is what the annotation says and `bool` is a subclass of it, so the check that
        # matters at runtime is the one the type system cannot make: a governed file states
        # `true` and Python hands it a value that IS an int and means nothing like one.
        # `type(...) is not int` rather than `isinstance`, and both halves are on purpose:
        # the annotation already says `int`, so a type checker calls `isinstance` redundant —
        # but a governed file states `true` and hands us a `bool`, which IS an `int` by
        # inheritance and is not a cut. Exact type is the only check that separates them.
        if type(self.top_n) is not int:
            raise BreakdownGovernanceError(
                f"top_n is {type(self.top_n).__name__} and not an integer; a cut that is not a "
                "number is not a cut"
            )
        if not 1 <= self.top_n <= MAXIMUM_LINES:
            raise BreakdownGovernanceError(
                f"top_n is {self.top_n}, outside 1..{MAXIMUM_LINES}; SC-1304 caps a breakdown at "
                f"{MAXIMUM_LINES} lines and a cut of zero shows nothing at all"
            )
        if not self.tail_label.strip():
            raise BreakdownGovernanceError(
                "tail_label is empty; a tail nobody can name is a truncation that hides"
            )
        if not self.tail_noun.strip():
            raise BreakdownGovernanceError(
                "tail_noun is empty; the shape both FR-1303 and SC-1304 spell out has a noun "
                "after the count, and it is the half that says WHAT was cut"
            )
        for column, label in self.axis_labels:
            if not column.strip() or not label.strip():
                raise BreakdownGovernanceError(
                    f"an axis maps {column!r} to {label!r}; both halves have to say something"
                )

    def excluded_for(self, column: str) -> tuple[str, ...]:
        """Values of ``column`` that are not values of the axis — see the governed file.

        Empty for a column that declares none, which is the normal case: the exclusion exists
        because one axis was MEASURED to carry an aggregate beside its parts, not because
        exclusions are expected.
        """
        return dict(self.excluded_values).get(column, ())

    @property
    def columns(self) -> tuple[str, ...]:
        """The source columns this report may break down by, in the declared order."""
        return tuple(column for column, _label in self.axis_labels)

    @classmethod
    def from_document(cls, document: object) -> BreakdownGovernance:
        """Build from the parsed governed file, refusing anything it fails to state.

        The document is a parameter rather than a path: a module that opened a file of its own
        choosing could be handed a different world by nobody, and the caller already owns the
        repository root the way it does for `section_order.yaml`.
        """
        if not isinstance(document, dict):
            raise BreakdownGovernanceError(
                f"the governed breakdown is {type(document).__name__} and not a mapping"
            )
        for key in ("top_n", "axis_labels", "tail_label"):
            if key not in cast("dict[str, object]", document):
                raise BreakdownGovernanceError(
                    f"the governed breakdown states no {key!r}; silence is not a value"
                )
        stated = cast("dict[str, object]", document)
        labels = stated["axis_labels"]
        if not isinstance(labels, dict) or not labels:
            raise BreakdownGovernanceError(
                "axis_labels is not a non-empty mapping of source column to his word"
            )
        tail = stated["tail_label"]
        if not isinstance(tail, str):
            raise BreakdownGovernanceError(f"tail_label is {type(tail).__name__} and not a word")
        total = stated.get("total_label", "")
        if not isinstance(total, str):
            raise BreakdownGovernanceError(f"total_label is {type(total).__name__} and not a word")
        noun = stated.get("tail_noun", "")
        if not isinstance(noun, str) or not noun.strip():
            raise BreakdownGovernanceError(
                "tail_noun is missing or empty; both FR-1303 and SC-1304 spell the tail with a "
                "noun after the count, and dropping it is a shape neither artefact approved"
            )
        pairs = cast("dict[object, object]", labels)
        excluded: object = stated.get("excluded_values") or {}
        if not isinstance(excluded, dict):
            raise BreakdownGovernanceError(
                "excluded_values is stated and is not a mapping of column to values"
            )
        by_column = cast("dict[object, object]", excluded)
        named: object = stated.get("kpis") or []
        if not isinstance(named, list):
            raise BreakdownGovernanceError("kpis is stated and is not a list of KPI names")
        floor = stated.get("sample_floor", 0)
        if not isinstance(floor, int) or isinstance(floor, bool) or floor < 0:
            raise BreakdownGovernanceError(
                f"sample_floor is {floor!r}; a floor is a whole number of cases, never negative"
            )
        markers: dict[str, str] = {}
        for key in ("axis_marker", "value_marker"):
            marker = stated.get(key, "")
            if not isinstance(marker, str):
                raise BreakdownGovernanceError(f"{key} is {type(marker).__name__} and not a mark")
            markers[key] = marker
        if bool(markers["axis_marker"]) != bool(markers["value_marker"]):
            raise BreakdownGovernanceError(
                "one marker is stated and the other is not; the two levels are a hierarchy and "
                "half a hierarchy reads as a flat list with one stray character in it"
            )
        stated_icons: object = stated.get("icons") or {}
        if not isinstance(stated_icons, dict):
            raise BreakdownGovernanceError(
                "icons is stated and is not a mapping of axis to value-to-icon"
            )
        icons: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        for axis, by_value in cast("dict[object, object]", stated_icons).items():
            if not isinstance(by_value, dict):
                raise BreakdownGovernanceError(
                    f"icons for {axis!r} is not a mapping of value to icon"
                )
            icons.append(
                (
                    str(axis),
                    tuple(
                        (str(value), str(icon))
                        for value, icon in cast("dict[object, object]", by_value).items()
                    ),
                )
            )
        #: `OD-144`: the split tail's three words. Optional in the document — absence is the
        #: declared absence and the tail keeps the one-line shape — and refused when stated as
        #: anything but a word, which is the `S-41` rule and not a default.
        split: dict[str, str] = {}
        for key in ("sampled_qualifier", "withheld_label", "withheld_value"):
            word = stated.get(key, "")
            if not isinstance(word, str):
                raise BreakdownGovernanceError(f"{key} is {type(word).__name__} and not a word")
            split[key] = word
        #: `OD-153`: the two NUMBERS an axis is named in. Read the same way, refused the same
        #: way, and then checked against each other — an axis named in one and not the other
        #: renders the wrong word for the count it has no word for, and nothing else would say
        #: so. Absent from the document is the declared absence: the axis falls back to
        #: `tail_noun` for every count, which is what it did before either map existed.
        by_number: dict[str, dict[str, str]] = {}
        for key in ("axis_plural", "axis_singular"):
            stated_words: object = stated.get(key) or {}
            if not isinstance(stated_words, dict):
                raise BreakdownGovernanceError(
                    f"{key} is stated and is not a mapping of axis to his word"
                )
            #: Not `named` — that name already holds the KPI list a few lines above, and
            #: shadowing it silently handed `kpis` the axis names. The suite caught it.
            by_axis: dict[str, str] = {}
            for axis, word in cast("dict[object, object]", stated_words).items():
                if not isinstance(word, str) or not word.strip():
                    raise BreakdownGovernanceError(
                        f"{key} states no word for {axis!r}; an axis listed with nothing "
                        "beside it is an axis nobody named"
                    )
                by_axis[str(axis)] = word
            by_number[key] = by_axis
        for key, other in (("axis_plural", "axis_singular"), ("axis_singular", "axis_plural")):
            for axis in by_number[key].keys() - by_number[other].keys():
                raise BreakdownGovernanceError(
                    f"{other} states no word for {axis!r} while {key} does; an axis named in "
                    "one number and not the other has no word for the count it is missing, and "
                    "the tail would print the word for the other one"
                )
        stated_unavailable: object = stated.get("unavailable_axes") or {}
        if not isinstance(stated_unavailable, dict):
            raise BreakdownGovernanceError(
                "unavailable_axes is stated and is not a mapping of axis to its declaration"
            )
        unavailable: list[UnavailableAxis] = []
        for axis, declaration in cast("dict[object, object]", stated_unavailable).items():
            if not isinstance(declaration, dict):
                raise BreakdownGovernanceError(
                    f"unavailable axis {axis!r} is not a mapping with label, reason_code, "
                    "source and kpis"
                )
            fields = cast("dict[object, object]", declaration)
            for key in ("label", "reason_code", "source"):
                word = fields.get(key)
                if not isinstance(word, str) or not word.strip():
                    raise BreakdownGovernanceError(
                        f"unavailable axis {axis!r} states no {key!r}; a refusal that cannot name "
                        "its axis, its reason or its source is silence with a heading"
                    )
            named_kpis = fields.get("kpis")
            if not isinstance(named_kpis, list) or not named_kpis:
                raise BreakdownGovernanceError(
                    f"unavailable axis {axis!r} names no KPI; an axis nobody expected to carry "
                    "is not refused, it is absent"
                )
            unavailable.append(
                UnavailableAxis(
                    column=str(axis),
                    label=str(fields["label"]),
                    reason_code=str(fields["reason_code"]),
                    source=str(fields["source"]),
                    kpis=tuple(str(name) for name in cast("list[object]", named_kpis)),
                )
            )
        return cls(
            unavailable_axes=tuple(unavailable),
            sampled_qualifier=split["sampled_qualifier"],
            withheld_label=split["withheld_label"],
            withheld_value=split["withheld_value"],
            axis_plural=tuple(sorted(by_number["axis_plural"].items())),
            axis_singular=tuple(sorted(by_number["axis_singular"].items())),
            axis_marker=markers["axis_marker"],
            value_marker=markers["value_marker"],
            icons=tuple(icons),
            top_n=cast("int", stated["top_n"]),
            axis_labels=tuple((str(column), str(label)) for column, label in pairs.items()),
            tail_label=tail,
            total_label=total,
            tail_noun=noun,
            sample_floor=floor,
            kpis=tuple(str(name) for name in cast("list[object]", named)),
            excluded_values=tuple(
                (str(column), tuple(str(value) for value in cast("list[object]", values)))
                for column, values in by_column.items()
            ),
        )


@dataclass(frozen=True, slots=True)
class Breakdown:
    """One axis of one KPI, already cut: the lines a person reads and the tail behind them.

    ``tail_count`` and ``tail_total`` are **both** carried because a tail that says only how
    many is a tail that hides how much, and one that says only how much hides how many. When
    nothing was cut they are zero and ``has_tail`` is false — an empty tail line is not
    printed, because a tail that is always there teaches a reader to skip it.

    ## `OD-144`: the tail is ONE population again, and ``withheld_count`` is the other

    ``tail_count``/``tail_total`` used to hold **two** populations at once — the parts that did
    not fit the cut, and the parts the sample floor WITHHELD — and the second has no assertable
    rate by construction. On the real message that put `Australia 0,00 %` visibly above a tail
    reading `4,47 %`, with nothing on screen to say the tail contained partitions whose rate was
    deliberately not asserted.

    Now the two are apart: ``tail_total`` aggregates the CUT rows only, and ``withheld_count``
    counts the withheld ones without asserting anything about them. **They are still in the
    reconciliation** — ``len(lines) + tail_count + withheld_count`` is the number of partitions
    the axis had, and a node measures exactly that — which is what he refused to give up.
    """

    column: str
    label: str
    lines: tuple[tuple[str, Decimal], ...]
    tail_count: int
    tail_total: Decimal
    #: `OD-144`: how many partitions the sample floor withheld. **A count and never a number**:
    #: `SC-1301` withholds them precisely because their rate is not assertable, so a total over
    #: them would be the assertion the floor exists to refuse.
    withheld_count: int = 0
    #: `F5` (`FR-1316`): the governed sentence that says why this axis has no values today.
    #: Empty for a breakdown that was measured; non-empty for one his file declares unavailable,
    #: which then carries no line and no tail — the reason IS what is rendered under the axis.
    reason: str = ""

    @property
    def has_tail(self) -> bool:
        return self.tail_count > 0

    @property
    def has_withheld(self) -> bool:
        """`OD-144`: whether the sample floor kept partitions out of the ranking."""
        return self.withheld_count > 0

    @property
    def is_unavailable(self) -> bool:
        return bool(self.reason)

    def scaled(self, scale: Callable[[Decimal], Decimal]) -> Breakdown:
        """The same breakdown with every number read at the KPI's own scale.

        **Measured against the real warehouse on 2026-09-04, and it would have shipped a lie**:
        the view stores a rate as a fraction of one, the caller reads that scale ONCE for the
        KPI's own value (`as_percent`), and the breakdown did not go through it. `Trial
        conversion` rendered its parts a hundred times smaller than its total — Brazil at
        `0,03 %` where the source says `1,24 %`.

        The scale stays the caller's to apply, for the reason the caller's comment already
        gives: it is read in one place. This method exists so that applying it cannot mean
        rebuilding the object and forgetting the tail.
        """
        return Breakdown(
            column=self.column,
            label=self.label,
            lines=tuple((value, scale(number)) for value, number in self.lines),
            tail_count=self.tail_count,
            tail_total=scale(self.tail_total),
            withheld_count=self.withheld_count,
            reason=self.reason,
        )


def cut_to_top(
    partitions: Sequence[tuple[str, Sequence[ViewRow]]],
    governance: BreakdownGovernance,
    column: str,
    value_column: str,
    sample_floor: int = 0,
) -> Breakdown | None:
    """Rank, cut, and AGGREGATE THE TAIL — `FR-1303`, `SC-1301`, `SC-1304`.

    **The tail is aggregated from the rows it cut, never summed from their numbers**, and that
    is not a refinement: measured against the real warehouse on 2026-09-04, summing a rate's
    parts printed a tail of *1,95 %* over a hundred countries — a number that is not a
    percentage of anything. A
    rate's tail is `SUM(numerator) / SUM(denominator)` over the cut rows, which is what
    :func:`aggregate` already computes; a count's tail is the sum, which is the same function
    answering the other way. One call, two correct answers, because the class comes from the
    rows.

    **``sample_floor`` keeps `SC-1301`**, and the same measurement is why: without it the
    country ranking of `Trial conversion` opened with *"Lithuania 0,50 %"* — a partition whose
    entire sample is a handful of cases. A partition under the floor does not have its rate
    ASSERTED: it is not ranked and falls into the tail, where it still counts toward a number
    that is honest because the tail is aggregated. The floor applies only where a denominator
    exists; a count of five is a count of five.

    Returns ``None`` when nothing survived — an axis with no assertable partition renders no
    heading, because a heading with nothing under it claims a measurement happened.
    """
    ranked: list[tuple[str, Decimal, Sequence[ViewRow]]] = []
    withheld: list[Sequence[ViewRow]] = []
    for value, group in partitions:
        number = aggregate(group, value_column)
        if number is None:
            continue
        size = sample_size(group)
        if size is not None and size < sample_floor:
            withheld.append(group)
            continue
        ranked.append((value, number, group))
    if not ranked:
        return None
    ranked.sort(key=lambda entry: (-abs(entry[1]), entry[0]))
    kept = ranked[: governance.top_n]
    cut = ranked[governance.top_n :]
    #: **`OD-144`, 2026-09-06: the withheld rows no longer join the tail's number.**
    #:
    #: They did, and the reasoning was sound as far as it went — a withheld part still counts
    #: toward a tail that is AGGREGATED rather than summed, so the figure stayed arithmetically
    #: honest. What it was not is READABLE: one line then answered two questions, and on the
    #: real message `Australia 0,00 %` sat above a tail reading `4,47 %` with nothing on screen
    #: to say the tail held partitions whose rate the floor refuses to assert.
    #:
    #: So the tail aggregates the CUT rows only, and the withheld are carried as a COUNT beside
    #: it. **They are not dropped** — he refused that, because it contradicts the reconciliation
    #: he approved — and `len(lines) + tail_count + withheld_count` is still every partition the
    #: axis had.
    tail_rows = [row for _value, _number, group in cut for row in group]
    return Breakdown(
        column=column,
        label=dict(governance.axis_labels)[column],
        lines=tuple((value, number) for value, number, _group in kept),
        tail_count=len(cut),
        tail_total=(aggregate(tail_rows, value_column) or Decimal(0)) if tail_rows else Decimal(0),
        withheld_count=len(withheld),
    )


def breakdowns_of(
    rows: Sequence[ViewRow],
    value_column: str,
    allowed: Sequence[str],
    governance: BreakdownGovernance,
    sample_floor: int = 0,
) -> tuple[Breakdown, ...]:
    """Every breakdown this KPI is ALLOWED to show, cut and ready to render — `FR-1302`.

    ``allowed`` is the metric contract's ``allowed_dimensions``, which is **deny-by-default**
    by the catalogue's own design: an axis that is not listed is forbidden, not merely
    undocumented. It arrives as a parameter because reading the catalogue is not this
    package's job — the caller already loads the contracts and knows which version is bound to
    the view.

    The intersection is taken in the GOVERNED order, not the contract's, so two KPIs that
    allow the same axes render them the same way round. A KPI that allows an axis the report
    does not govern shows nothing for it, and a report that governs an axis the KPI does not
    allow shows nothing either — the two lists have to agree for a line to exist, which is
    what makes this deny-by-default in both directions.
    """
    permitted = set(allowed)
    answered: list[Breakdown] = []
    for column in governance.columns:
        if column not in permitted:
            continue
        partitions = partition_by(rows, column, governance.excluded_for(column))
        if not partitions:
            continue
        found = cut_to_top(partitions, governance, column, value_column, sample_floor)
        if found is not None:
            answered.append(found)
    return tuple(answered)


def unavailable_breakdowns_of(
    kpi: str,
    governance: BreakdownGovernance,
    reasons: Mapping[str, str],
) -> tuple[Breakdown, ...]:
    """The axes his file declares unavailable for ``kpi``, each SAID, not skipped — `FR-1316`.

    ``reasons`` maps an unavailable axis's column to the governed sentence that says why, rendered
    by the caller from the reason-message registry. **An axis whose sentence the caller did not
    supply is refused here**, not rendered without one: a heading that says nothing under it is the
    silent-total shape this slice exists to replace.
    """
    said: list[Breakdown] = []
    for axis in governance.unavailable_for(kpi):
        sentence = reasons.get(axis.column, "")
        if not sentence.strip():
            raise BreakdownGovernanceError(
                f"no governed sentence was supplied for the unavailable axis {axis.column!r} "
                f"({axis.reason_code}); a refusal without its reason is a heading over nothing"
            )
        said.append(
            Breakdown(
                column=axis.column,
                label=axis.label,
                lines=(),
                tail_count=0,
                tail_total=Decimal(0),
                reason=sentence,
            )
        )
    return tuple(said)
