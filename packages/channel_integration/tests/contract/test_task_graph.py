"""The task-graph gate — T166 (review finding I; `tasks.md` § Task dependency graph).

The ledger declares its dependency graph as **seven rules**, not as an edge list, and then states
properties that follow. Until this file existed those properties had only ever been asserted **by
inspection**, twice, in two handoffs. Inspection is not a gate: it agrees with whoever performed it,
it is not re-run when the ledger changes, and it cannot fail.

So the graph is **derived** here from the ledger text and the properties are asserted mechanically.
Derived, never transcribed — a hand-written edge list of 156 rows would drift from the ledger the
first time a task moved, and then this file would be testing its own copy of the past.

The seven rules, verbatim in effect:

* `R1` — a `[P]` task depends only on its phase's **entry** task;
* `R2` — a non-`[P]` task depends on the **immediately preceding** task in its own phase;
* `R3` — each phase's **last** task is its convergence node and depends on every other task in that
  phase, which is what makes a `[P]` task a participant rather than a leaf;
* `R4` — phase entry tasks depend across phases through the previous phase's convergence node;
* `R5` — `T154` additionally depends on every Phase E task, and `T155` depends on `T154`;
* `R6` — `T156` to `T165` are **records, not nodes**;
* `R7` — `T166` depends on `T030` **and on `T155`**, and is therefore the terminus.

**What this gate does not claim.** It proves the declared graph is well-formed and that the ledger
is consistent with its own rules. It does not prove the *ordering is wise* — that a task really
needs its predecessor is a judgement, and no test settles it. Stating the limit here so the green
is not read as more than it is.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_LEDGER = (
    Path(__file__).resolve().parents[4] / "specs" / "004-multichannel-integration" / "tasks.md"
)

#: A task line: state, id, and everything after it.
_TASK_LINE = re.compile(r"^- \[([ Xx])\] T(\d{3})(.*)$", re.M)
#: A phase heading. `Phase A0 — COMPLETED` is deliberately matched too, then discarded: it carries
#: no task number, and a scan that silently skipped it could also silently skip a real phase.
_PHASE_HEADING = re.compile(r"^## Phase ([A-E]0?) — (.+)$", re.M)
_LEDGER_SECTION = re.compile(r"^## (.+)$", re.M)
_EXTERNAL_RECORD = "[BLOCKED-EXTERNAL]"
_PARALLEL = "[P]"

#: Declared in the ledger's `R3` and `R7`. Written out because they are the **claim** — deriving
#: them from the phases would make this assertion agree with any ledger.
_DECLARED_CONVERGENCE = {"A": 30, "B": 70, "C": 105, "D0": 117, "D": 135, "E": 155}
#: `T155` closes the phases; `T166` closes the ledger (`R7`). The two are distinct on purpose.
_RELEASE_RECORD = 155
_TERMINUS = 166
_GRAPH_GATE = 166


# --------------------------------------------------------------------------- #
# Parsing the ledger                                                           #
# --------------------------------------------------------------------------- #


def _sections() -> list[tuple[str, int]]:
    """Every `##` heading with its offset, in document order."""
    return [(m.group(1).strip(), m.start()) for m in _LEDGER_SECTION.finditer(_TEXT)]


_TEXT = _LEDGER.read_text(encoding="utf-8")


def _owning_section(offset: int) -> str:
    """Which `##` section a task line at ``offset`` belongs to."""
    owner = "«preamble»"
    for title, start in _sections():
        if start < offset:
            owner = title
        else:
            break
    return owner


class Task:
    """One ledger row, with the facts the rules need.

    ``written`` is the row's position in the document, kept because sorting by id throws that
    information away and one assertion below needs it — review finding F8.
    """

    __slots__ = ("complete", "number", "parallel", "record", "section", "text", "written")

    def __init__(self, number: int, state: str, text: str, section: str, written: int) -> None:
        self.number = number
        self.complete = state.lower() == "x"
        self.text = text
        self.section = section
        self.written = written
        self.parallel = _PARALLEL in text
        self.record = _EXTERNAL_RECORD in text

    def __repr__(self) -> str:  # pragma: no cover - failure readability
        return f"T{self.number:03d}"


def _tasks() -> list[Task]:
    """Every ledger row, **sorted by id**, carrying the position it was written at.

    The sort is deliberate and is what `R2` needs: "the immediately preceding task" is the preceding
    **id**, everywhere in this file, and that is what makes "no forward edge" true by construction
    rather than by inspection.

    It also means ``PHASES[phase][-1]`` is the phase's **highest id**, which is not the same claim
    as "the last line written in that phase". Those two coincide only while every phase is written
    in id order, and review finding F8 caught this file asserting the positional reading while
    measuring the id one: swapping the adjacent `T104` and `T105` rows left
    :func:`test_the_convergence_nodes_are_the_last_task_of_their_phase` green. The gap is closed by
    asserting the coincidence itself, in :func:`test_every_phase_is_written_in_id_order` — so both
    readings hold, rather than by quietly narrowing the claim to whichever one was measured.
    """
    found = [
        Task(int(m.group(2)), m.group(1), m.group(3), _owning_section(m.start()), written)
        for written, m in enumerate(_TASK_LINE.finditer(_TEXT))
    ]
    return sorted(found, key=lambda task: task.number)


TASKS = _tasks()
BY_NUMBER = {task.number: task for task in TASKS}
RECORDS = {task.number for task in TASKS if task.record}
EXECUTABLE = [task for task in TASKS if not task.record]


def _phase_of(task: Task) -> str | None:
    """The phase letter for an executable task, or ``None`` when it is not in a phase section."""
    match = re.match(r"Phase ([A-E]0?) — ", task.section)
    return match.group(1) if match else None


PHASES: dict[str, list[Task]] = {}
for task in EXECUTABLE:
    phase = _phase_of(task)
    if phase is not None:
        PHASES.setdefault(phase, []).append(task)

#: Executable tasks outside every phase section. `T166` is the only legitimate member, and the
#: assertion below says so — an accidental second one would be a task nobody scheduled.
UNPHASED = [task for task in EXECUTABLE if _phase_of(task) is None]


# --------------------------------------------------------------------------- #
# Deriving the edge set from R1 to R7                                           #
# --------------------------------------------------------------------------- #


#: `R5` names this one explicitly: `T154` is the internal validation record gathering Phase E, and
#: `T155` depends on it. Named rather than left a literal because the guard below has to report it.
_INTERNAL_VALIDATION = 154


#: Every id the rules name by number rather than derive. Checked to exist **before** any edge is
#: derived from it — review finding F9. Deleting the `T166` row used to raise a bare
#: ``KeyError: 166`` inside `R7`, at import time, which took the whole module out of collection
#: without saying what was missing. It failed loudly, so nothing was hidden; it failed illegibly,
#: which is its own defect.
def _named_ids() -> dict[str, int]:
    named = {
        f"_DECLARED_CONVERGENCE[{phase!r}]": number
        for phase, number in _DECLARED_CONVERGENCE.items()
    }
    named["_RELEASE_RECORD"] = _RELEASE_RECORD
    named["_INTERNAL_VALIDATION"] = _INTERNAL_VALIDATION
    named["_TERMINUS"] = _TERMINUS
    named["_GRAPH_GATE"] = _GRAPH_GATE
    return named


def _assert_named_ids_exist() -> None:
    """Every hand-written id the rules name is a task the ledger declares.

    This is the precondition of the whole derivation. It runs before edges are built, and it names
    what is missing, because "the ledger no longer declares a task the rules depend on" is a
    sentence a reader can act on and ``KeyError: 166`` is not.
    """
    missing = {name: number for name, number in _named_ids().items() if number not in BY_NUMBER}
    assert not missing, (
        f"the rules name ids the ledger does not declare: {missing}. Either the ledger lost a task "
        "the rules depend on, or a rule changed and this module's named ids must be re-derived — "
        "never the other way round"
    )
    records = {name: number for name, number in _named_ids().items() if number in RECORDS}
    assert not records, (
        f"the rules name external dependency records as graph nodes: {records}. R6 makes records "
        "non-nodes, so deriving an edge from one would schedule third-party work"
    )


def _edges() -> dict[int, set[int]]:
    """``{dependent: {dependencies}}``, derived from the rules and nothing else."""
    _assert_named_ids_exist()
    edges: dict[int, set[int]] = {task.number: set() for task in EXECUTABLE}
    ordered_phases = [phase for phase in ("A", "B", "C", "D0", "D", "E") if phase in PHASES]

    for index, phase in enumerate(ordered_phases):
        members = PHASES[phase]
        entry, convergence = members[0], members[-1]

        for position, task in enumerate(members):
            if task is entry:
                continue
            if task is convergence:
                # R3: the convergence node depends on every other task in its phase.
                edges[task.number] |= {other.number for other in members if other is not task}
            elif task.parallel:
                edges[task.number].add(entry.number)  # R1
            else:
                edges[task.number].add(members[position - 1].number)  # R2

        # R4: the entry task depends on the previous phase's convergence node. Phase D depends on
        # B, C and D0 together, which the ledger states explicitly rather than by position.
        if phase == "B" or phase == "C" or phase == "D0":
            edges[entry.number].add(_DECLARED_CONVERGENCE["A"])
        elif phase == "D":
            edges[entry.number] |= {
                _DECLARED_CONVERGENCE["B"],
                _DECLARED_CONVERGENCE["C"],
                _DECLARED_CONVERGENCE["D0"],
            }
        elif phase == "E" and index > 0:
            edges[entry.number].add(_DECLARED_CONVERGENCE["D"])

    # R5: T154 depends on every Phase E task before it; T155 depends on T154.
    if "E" in PHASES:
        edges[_INTERNAL_VALIDATION] |= {
            task.number for task in PHASES["E"] if task.number < _INTERNAL_VALIDATION
        }
        edges[_RELEASE_RECORD].add(_INTERNAL_VALIDATION)

    # R7: the graph gate depends on Phase A's convergence node and on the release record, which is
    # what keeps every edge pointing at a lower id.
    edges[_GRAPH_GATE] |= {_DECLARED_CONVERGENCE["A"], _RELEASE_RECORD}

    return edges


EDGES = _edges()


# --------------------------------------------------------------------------- #
# The ledger parsed as expected — without this, every property below is vacuous #
# --------------------------------------------------------------------------- #


def test_the_ledger_was_parsed_and_is_not_empty() -> None:
    assert len(TASKS) >= 156, f"only {len(TASKS)} task rows were parsed"
    assert len(RECORDS) == 10, f"expected ten external records, found {sorted(RECORDS)}"
    assert len(EXECUTABLE) == len(TASKS) - 10


def test_every_task_id_is_unique_and_the_sequence_has_no_hole() -> None:
    numbers = [task.number for task in TASKS]
    assert len(numbers) == len(set(numbers)), "a task id is declared twice"
    assert numbers == list(range(1, len(numbers) + 1)), "the id sequence skips or repeats"


def test_every_phase_declared_in_the_ledger_has_tasks() -> None:
    headings = {m.group(1) for m in _PHASE_HEADING.finditer(_TEXT)}
    assert "A0" in headings, "the completed-phase heading must still be present"
    for phase in headings - {"A0"}:
        assert PHASES.get(phase), f"phase {phase} declares no task"


def test_the_only_task_outside_a_phase_is_the_graph_gate() -> None:
    """A task in no phase is a task no phase ordering covers. `T166` is the declared exception."""
    assert [task.number for task in UNPHASED] == [_GRAPH_GATE], (
        f"unscheduled executable tasks: {UNPHASED}"
    )


def test_every_phase_is_written_in_id_order() -> None:
    """The coincidence the node below depends on, asserted instead of assumed — finding F8.

    `_tasks` sorts by id, so ``PHASES[phase][-1]`` is a phase's **highest id**. The node below
    claims something narrower in its name: the phase's **last written task**. The two are the same
    statement only while each phase is written in ascending id order, and that was never checked —
    swapping the adjacent `T104` and `T105` rows left the convergence assertion green while a reader
    scanning the file top to bottom would see a different last task than the gate measured.

    Closing it this way rather than by renaming the node is deliberate. Renaming would have made the
    prose accurate and left the blind spot open: the ledger is read by people in written order and
    by this file in id order, and a divergence between those two is worth a failure on its own. With
    this node green, both readings are true and the positional name is honest.
    """
    for phase, members in sorted(PHASES.items()):
        written = [task.number for task in sorted(members, key=lambda task: task.written)]
        by_id = [task.number for task in members]
        assert written == by_id, (
            f"phase {phase} is written in a different order than its ids: written {written}, "
            f"by id {by_id}. Every rule here reads ids, so a reader scanning the ledger sees a "
            "different order than the gate measures"
        )


def test_the_convergence_nodes_are_the_last_task_of_their_phase() -> None:
    """`R3`'s claim, checked against the ledger rather than trusted.

    "Last task" is the **positional** reading, and it holds only because
    :func:`test_every_phase_is_written_in_id_order` asserts that written and id order coincide.
    Without that node this one measures the highest id and says something stronger than it checks,
    which is what review finding F8 caught. The two nodes are one claim in two halves.
    """
    for phase, number in _DECLARED_CONVERGENCE.items():
        assert phase in PHASES, f"phase {phase} is missing"
        assert PHASES[phase][-1].number == number, (
            f"phase {phase} ends at T{PHASES[phase][-1].number:03d}, not T{number:03d}"
        )


def test_every_id_the_rules_name_is_a_declared_executable_task() -> None:
    """Finding F9, asserted as a property and not only enforced at derivation time.

    `_assert_named_ids_exist` already guards `_edges`, so a ledger missing one of these ids fails
    before any edge is built. This node states the same invariant where a reader looks for it, and
    names the ids involved so the set is visible rather than buried in a helper.
    """
    _assert_named_ids_exist()
    for name, number in sorted(_named_ids().items()):
        assert number in BY_NUMBER, f"{name} names T{number:03d}, which the ledger does not declare"
        assert number not in RECORDS, f"{name} names T{number:03d}, an external dependency record"


# --------------------------------------------------------------------------- #
# The declared properties                                                      #
# --------------------------------------------------------------------------- #


def test_no_forward_edge_exists() -> None:
    """Every dependency has a strictly lower id, so the graph is a DAG by construction."""
    offenders = [
        f"T{dependent:03d} <- T{dependency:03d}"
        for dependent, dependencies in EDGES.items()
        for dependency in dependencies
        if dependency >= dependent
    ]
    assert not offenders, offenders


def test_no_self_edge_exists() -> None:
    offenders = [f"T{n:03d}" for n, deps in EDGES.items() if n in deps]
    assert not offenders, offenders


def test_no_edge_touches_an_external_record() -> None:
    """`R6`: a record is not a node. Depending on one would make external work look schedulable."""
    into = [
        f"T{dependent:03d} <- T{dependency:03d}"
        for dependent, dependencies in EDGES.items()
        for dependency in dependencies
        if dependency in RECORDS
    ]
    assert not into, into
    assert not (RECORDS & set(EDGES)), "a record was given outgoing edges"


def test_no_undefined_edge_exists() -> None:
    executable = {task.number for task in EXECUTABLE}
    dangling = [
        f"T{dependent:03d} <- T{dependency:03d}"
        for dependent, dependencies in EDGES.items()
        for dependency in dependencies
        if dependency not in executable
    ]
    assert not dangling, dangling


def test_the_graph_is_acyclic_by_topological_order() -> None:
    """Asserted independently of the no-forward-edge property.

    Two instruments for one claim on purpose: the id ordering makes a cycle inexpressible, and a
    topological sort would still find one if the derivation ever stopped respecting ids.
    """
    remaining = {n: set(deps) for n, deps in EDGES.items()}
    ordered: list[int] = []
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if not deps)
        assert ready, f"cycle among {sorted(remaining)}"
        for n in ready:
            del remaining[n]
            ordered.append(n)
        for deps in remaining.values():
            deps -= set(ready)
    assert len(ordered) == len(EDGES)


def test_exactly_one_terminal_task_exists_and_it_is_the_graph_gate() -> None:
    """A second sink would be work nothing depends on, which is work nobody closes."""
    depended_on: set[int] = set()
    for dependencies in EDGES.values():
        depended_on |= dependencies
    sinks = sorted(set(EDGES) - depended_on)
    assert sinks == [_TERMINUS], f"expected T{_TERMINUS:03d} alone as terminus, found {sinks}"


def test_every_executable_task_reaches_the_terminus() -> None:
    """The property the convergence nodes exist for: no `[P]` task is a leaf."""
    dependents: dict[int, set[int]] = {task.number: set() for task in EXECUTABLE}
    for dependent, dependencies in EDGES.items():
        for dependency in dependencies:
            dependents[dependency].add(dependent)

    reaching_terminus: set[int] = set()
    frontier = [_TERMINUS]
    while frontier:
        current = frontier.pop()
        for upstream in EDGES[current]:
            if upstream not in reaching_terminus:
                reaching_terminus.add(upstream)
                frontier.append(upstream)

    unreached = sorted({task.number for task in EXECUTABLE} - reaching_terminus - {_TERMINUS})
    assert not unreached, f"tasks that reach nothing: {[f'T{n:03d}' for n in unreached]}"


def test_every_parallel_task_is_a_participant_rather_than_a_leaf() -> None:
    """`R3` stated from the other side: something must depend on every `[P]` task."""
    depended_on: set[int] = set()
    for dependencies in EDGES.values():
        depended_on |= dependencies
    leaves = sorted(
        task.number for task in EXECUTABLE if task.parallel and task.number not in depended_on
    )
    assert not leaves, f"[P] tasks nothing depends on: {[f'T{n:03d}' for n in leaves]}"


def test_the_graph_gate_is_wired_as_the_ledger_declares() -> None:
    """`R7`, explicitly: this very task must not be the exception that escapes the graph.

    Direction matters and is asserted both ways: the gate depends on the release record, and the
    release record does **not** depend on the gate. The reverse would be a forward edge, which is
    exactly the mistake this rule was rewritten to avoid.
    """
    assert EDGES[_GRAPH_GATE] == {_DECLARED_CONVERGENCE["A"], _RELEASE_RECORD}
    assert _GRAPH_GATE not in EDGES[_RELEASE_RECORD]


def test_the_rules_are_still_declared_in_the_ledger() -> None:
    """The derivation above is only legitimate while the ledger still states these rules.

    If a rule were deleted from the document, this file would keep deriving edges from it and would
    keep passing — testing a graph nobody had agreed to any more.
    """
    for rule in ("**R1**", "**R2**", "**R3**", "**R4**", "**R5**", "**R6**", "**R7**"):
        assert rule in _TEXT, f"{rule} is no longer declared in the ledger"
