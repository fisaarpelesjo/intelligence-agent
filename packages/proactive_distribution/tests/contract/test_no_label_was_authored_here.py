"""The five labels are his, and this repository wrote none of them — T711, T712.

The owner chose the shape on 2026-08-27: label and value, one line per field, five
fields. **The shape is his choice and the words are also his**, and he has not written
them.

## The labels arrived on 2026-08-27, and these nodes were RE-DERIVED rather than deleted

They asserted the emptiness, and the emptiness ended when he chose. **Going red was
their function**, and the honest response to a node that goes red for the right reason
is to re-derive what it asserts — not to delete it, and not to loosen it until it passes
again. So they now assert the properties that survive his decision: the labels are HIS,
they cover exactly the model's fields, and **a field with no approved label still
refuses**.

A plausible label is a word this repository wrote that a reader would attribute to him,
and that rule did not change — what changed is that five words are no longer this
repository's. `metric:` would have looked harmless until the message reached a person who
believed he approved it, which is **fabricating an approval**, forbidden by `D-28`.

**And the disguises are named because that is how it would arrive**: labelled
provisional, then read as approved. So `EXAMPLE_`, `DRAFT_` and a fixture are checked
for by name, over this package's own source.

## The refusal has its own code, and that is `T701`'s point

*Nothing was worth sending* and *there is no approved way to say it* are different
facts about different parties. A reader seeing one code must know which stopped them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from proactive_distribution.contracts import DistributionReasonCode, field_names_of_the_model
from proactive_distribution.distribute import APPROVED_LABELS, MissingLabels, labels_for

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package.
PACKAGE = Path(__file__).resolve().parents[2]

#: How a written-here label would arrive if it arrived: labelled provisional, then read
#: as approved. Named rather than guarded against generally, so the check is checkable.
DISGUISES = ("EXAMPLE_", "DRAFT_", "SAMPLE_", "PLACEHOLDER_")


def test_the_labels_cover_exactly_the_fields_and_nothing_else() -> None:
    """**What replaced `APPROVED_LABELS == {}` when he wrote the five.**

    The old node asserted the emptiness and went red the moment it ended — which is what
    it was for. This is its re-derivation: a label for every field and no label for
    anything that is not a field.

    **A label without a field is the shape that matters here.** It would be a word he
    approved for a line that is never emitted, sitting in the mapping looking approved,
    ready to be attached to whatever field somebody adds next.
    """
    fields = set(field_names_of_the_model())
    labelled = set(APPROVED_LABELS)
    assert labelled == fields, (
        f"fields with no approved label: {sorted(fields - labelled)}; "
        f"labels for nothing the report emits: {sorted(labelled - fields)}"
    )


def test_no_label_is_blank() -> None:
    """A blank label is a line whose value arrives with nothing in front of it."""
    blank = sorted(name for name, label in APPROVED_LABELS.items() if not label.strip())
    assert not blank, f"these fields carry an empty label: {blank}"


def test_the_five_labels_are_distinct() -> None:
    """Two fields sharing a label is two lines a reader cannot tell apart."""
    labels = list(APPROVED_LABELS.values())
    assert len(set(labels)) == len(labels), f"a label is used twice: {labels}"


def test_every_field_now_gets_his_label() -> None:
    """The premise of everything below: the five he chose are the five that come back."""
    fields = field_names_of_the_model()
    resolved = labels_for(fields)
    assert set(resolved) == set(fields)
    assert all(resolved[name] == APPROVED_LABELS[name] for name in fields)


def test_a_field_with_no_approved_label_still_refuses() -> None:
    """**The refusal did not go away with the five words; it moved to where it belongs.**

    The day a sixth field is decided on, its word will not exist yet — and that is the
    case this node holds. Driven with a field name the mapping cannot satisfy, so it
    measures the refusal rather than the emptiness that used to produce it.
    """
    with pytest.raises(MissingLabels) as caught:
        labels_for(("a_field_he_has_not_named",))
    assert caught.value.missing == ("a_field_he_has_not_named",)
    assert caught.value.code is DistributionReasonCode.DISTRIBUTION_LABELS_NOT_APPROVED


def test_the_label_refusal_is_not_the_unplaced_finding_refusal() -> None:
    """**Two absences, two codes.** One is a fact about the warehouse, the other about a
    decision nobody has taken, and a reader who sees one must know which."""
    assert (
        DistributionReasonCode.DISTRIBUTION_LABELS_NOT_APPROVED
        is not DistributionReasonCode.DISTRIBUTION_FINDING_NOT_PRIORITISABLE
    )


def test_labels_are_all_or_nothing() -> None:
    """Four labels and one bare value is a message whose fifth line nobody can read.

    One field is labelled and one is not, and the whole call refuses — the refusal is
    over the SET, so a caller cannot receive a partial mapping and fill in the rest.
    """
    with pytest.raises(MissingLabels) as caught:
        labels_for(("metric", "a_field_he_has_not_named"))
    assert caught.value.missing == ("a_field_he_has_not_named",)


def test_no_disguised_label_was_written_into_this_package() -> None:
    """**The named disguises, searched for in CODE and not in prose.**

    A first version of this node read the raw text of every module and went red on the
    modules that FORBID the disguises — `report.py` and `labels.py` both say "not
    `EXAMPLE_`, not `DRAFT_`" in their docstrings. The guard was finding the
    prohibition's own words, which is the same self-reference this repository corrected
    twice this week: a check whose subject includes the check.

    So it walks the syntax tree. **A label written here would be a NAME BOUND TO A
    VALUE**, not a sentence saying it must not be — so assignments and their string
    values are what is searched, and docstrings and comments are not in the tree at all
    except as their own expressions, which carry no binding.
    """
    offenders: list[str] = []
    for path in sorted((PACKAGE / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and any(
                node.id.startswith(disguise) for disguise in DISGUISES
            ):
                offenders.append(f"{path.name}: name {node.id}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # A docstring is a bare expression; anything else is a value something
                # binds, passes or emits, which is where a smuggled label would live.
                if node.value.count(" ") > 3:
                    continue
                offenders.extend(
                    f"{path.name}: value {node.value!r}"
                    for disguise in DISGUISES
                    if node.value.startswith(disguise)
                )
    assert not offenders, (
        f"a label was written here under a provisional name: {offenders}. The words are the "
        "owner's, and a provisional label is read as approved the moment it is sent."
    )


def test_his_labels_survive_the_file_they_live_in() -> None:
    """**Three of the five carry accents, and this runs on Windows.**

    Not a hypothetical: this repository already paid for a Windows encoding defect this
    week, when a node floor silently stopped applying because a job list arrived with
    CRLF. A module re-saved in `cp1252` by an editor turns the accented labels into
    mojibake -- and a mangled label is a word he did not approve, sent under his
    authority.

    So the file is read as **bytes** and decoded explicitly, rather than trusting whatever
    encoding a reader happens to default to. And the accented characters are named BY
    CODE POINT: a node comparing the file's text against a string literal in this same
    file would agree with any mangling, because both would have been mangled together.
    """
    module = PACKAGE / "src" / "proactive_distribution" / "distribute" / "labels.py"
    source = module.read_bytes()
    assert not source.startswith(bytes((0xEF, 0xBB, 0xBF))), (
        "the module carries a UTF-8 BOM; a tool that does not expect one reads three stray "
        "characters in front of the first label"
    )
    text = source.decode("utf-8")
    expected = {
        "metric": "M" + chr(0xE9) + "trica",
        "period": "Per" + chr(0xED) + "odo",
        "direction": "Dire" + chr(0xE7) + chr(0xE3) + "o",
    }
    wrong = sorted(name for name, label in expected.items() if label not in text)
    assert not wrong, (
        f"these labels are not the characters he chose: {wrong}; the file was probably "
        "re-saved in a single-byte encoding"
    )
    assert all(APPROVED_LABELS[name] == label for name, label in expected.items()), (
        "the mapping disagrees with the code points, so the label reaching a reader is not "
        "the one written in the file"
    )
