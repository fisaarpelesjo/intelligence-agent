"""Two authored strings, both his, and a third is a violation — `T809`.

## The number in this file was corrected, and the correction is the point

`FR-804` first said **one** authored string: the footnote. Writing the header revealed a
second — the word the form opens with beside the date, because `OD-15-C` put it there.
**Both came from the form he selected**; neither is this repository's wording. The
requirement was corrected to name two rather than letting the code quietly contradict
it.

**Which is why this node counts from the module instead of against a literal.** A node
asserting *two* would have to be edited the day a decision of his adds a third — and
editing the number is exactly how a guard stops guarding. It compares the strings the
package emits against the set that module exports, so a third string fails without
anybody choosing a new number.
"""

from __future__ import annotations

import ast
from inspect import signature
from pathlib import Path

import pytest

from daily_reporting.report import summary, template

pytestmark = pytest.mark.contract

#: Every module of this package that a person's eyes ever reach.
EMITTING_MODULES = (Path(template.__file__), Path(summary.__file__))

#: Fragments that carry no words: punctuation, separators, a marker. A string is
#: "authored" when it says something; these say nothing.
WORDLESS = set(" -*:()\n")


def _string_constants(module: Path) -> list[str]:
    """Every string literal in the module, docstrings excluded.

    Docstrings are for the reader of the source, never for the reader of the report.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
    }
    # `__all__` holds NAMES, not content. A node counting them as authorship would be
    # red for every module that exports anything, which is a node nobody keeps -- and
    # the first run of this file found exactly that.
    exported: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.List | ast.Tuple):
            exported.update(
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
        and node.value not in exported
    ]


def _carries_words(text: str) -> bool:
    """Does this string say anything, as opposed to separating two things?"""
    return bool(set(text) - WORDLESS) and any(character.isalpha() for character in text)


def test_the_authored_set_is_what_the_template_exports() -> None:
    """Read this first: an empty export would make everything below vacuous."""
    assert template.AUTHORED_WORDS, "the template exports no authored words at all"
    assert template.CLOSED_DAY_WORD in template.AUTHORED_WORDS
    assert template.SHORT_OR_EMPTY_SOURCE in template.AUTHORED_WORDS


def test_no_module_a_reader_sees_authors_a_word_of_its_own() -> None:
    """**Counted from the module, never against a number this file wrote.**"""
    for module in EMITTING_MODULES:
        offending = sorted(
            {
                text
                for text in _string_constants(module)
                if _carries_words(text) and text not in template.AUTHORED_WORDS
            }
        )
        assert not offending, f"{module.name} authors {offending}, which is nobody's decision"


def test_the_scan_would_catch_a_third_string() -> None:
    """**Proof it bites**, over source this file parses rather than over the package.

    The stand-in is the plausible one: a sentence somebody adds because the report
    read a little bluntly.
    """
    smuggled = ast.parse('HEADER = "resumo diario dos indicadores"\n')
    found = [
        node.value
        for node in ast.walk(smuggled)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    offending = [text for text in found if _carries_words(text)]
    assert offending, "the scan accepts a sentence nobody approved"
    assert all(text not in template.AUTHORED_WORDS for text in offending)


def test_punctuation_is_not_counted_as_authorship() -> None:
    """Otherwise the node would be red always, which is a node nobody keeps."""
    for separator in (": ", " (", ")", " *", "-", "\n"):
        assert not _carries_words(separator), f"{separator!r} was counted as a word"


def test_the_daily_description_is_his_two_day_words_and_claims_no_set() -> None:
    """`OD-131` (2026-09-05) composed it; `OD-145` (2026-09-06) stopped RENDERING it.

    `T1329` made the 08:00 daily carry three of the nineteen active KPIs, and *"Os indicadores
    ativos"* — a definite plural — then claimed more than the message delivers. He chose to cut
    that half and keep the other, so what is left is his `Ontem`, his `Anteontem`, and the
    connector that already stood between them.

    **The next day he cut the rest**: *"ai esse ontem contra anteontem, arranca essa frase
    fora"*, because the line under it already prints the same two days as dates. The STRING
    stays in the ledger with its reintroduction condition; what this node still measures is
    that it is a composition of his own day words and claims no set — so that a future
    description, if one is ever printed again, is checked the same way.

    **Mutation**: any sentence that names the indicators again — for instance
    `"Os indicadores ativos, ontem contra anteontem"` or `"Os tres indicadores, ontem contra
    anteontem"` → this node red (`1 failed, 10 passed`, measured 2026-09-05 22:32 -03).
    """
    description = template.REPORT_DESCRIPTION
    assert description == f"{template.CLOSED_DAY_WORD} contra {template.PREVIOUS_DAY_WORD.lower()}"
    #: Nothing in it counts, names or quantifies the set — the defect `OD-131` removed.
    for claim in ("indicador", "ativ", "vinte", "dezenove", "tres", "três"):
        assert claim not in description.casefold(), claim
    assert description in template.AUTHORED_WORDS


def test_the_budget_is_twelve_and_every_member_is_dated_in_the_module() -> None:
    """**The count is measured against the module, and it moved because HE moved it.**

    Eight until 2026-09-06, twelve after it: `OD-147` named the movement row (`Variação`),
    `OD-150` named the second currency's block, and `OD-151` named the threshold row and the
    preposition that binds its two numbers. Four decisions, one message, all his, each written
    beside its constant with the words he used.

    **Mutation**: add a thirteenth string to `template.py` without a decision beside it — this
    node red. Take one away — red as well, which is the half that stops a silent deletion from
    passing as tidying.
    """
    assert len(template.AUTHORED_WORDS) == 12, sorted(template.AUTHORED_WORDS)
    for word in (
        template.VARIATION_WORD,
        template.IN_BRL_WORD,
        template.THRESHOLD_LABEL,
        template.OVER_PERIOD_WORD,
    ):
        assert word in template.AUTHORED_WORDS, word
        assert word.strip(), "an authored string with nothing in it names nothing"


def test_the_threshold_label_spends_no_vocabulary_it_did_not_already_have() -> None:
    """`OD-151`: every word of the threshold's label already stood in the alert's subtitle.

    That is the `OD-131` precedent in the other direction — a subtraction spends no budget, and
    a RECOMPOSITION of words already his spends none either. What changed is WHERE the sentence
    is said: `OD-149` took it off the top of the message and `OD-151` put it under the numbers
    it explains, on every indicator, because the threshold is the reason that indicator is in
    the alert at all.

    **Mutation**: replace the label with a word the subtitle never carried — red here, and the
    budget argument beside the constant becomes false.
    """
    subtitle = template.ALERT_DESCRIPTION.casefold()
    for word in template.THRESHOLD_LABEL.split():
        assert word.casefold() in subtitle, word


def test_the_two_descriptions_are_kept_and_neither_is_rendered_any_more() -> None:
    """`OD-145` and `OD-149`, 2026-09-06 — **kept in the ledger, gone from the screen**.

    They arrived visually identical (`OD-49`) and he asked twice which one was the alert, so
    each product got a title and a description of his. The descriptions are now removed for two
    DIFFERENT reasons, and conflating them would lose both: the daily's said in words what the
    line below it says in dates, and the alert's said something real until `OD-151` moved that
    same fact onto every indicator's own row.

    **What tells the two products apart now** is the title, which is still his and still
    counted, plus the threshold row `OD-43` put on an alert line and never on a report line.

    **Mutation**: delete either description from `template.py` — this node red, and the record
    of his own wording is gone with it, which is the thing the ledger is for.
    """
    titles = (template.REPORT_TITLE, template.ALERT_TITLE)
    assert len(set(titles)) == 2, "the two products share a title, which is the defect"
    for title in titles:
        assert title in template.AUTHORED_WORDS, title
    for description in (template.REPORT_DESCRIPTION, template.ALERT_DESCRIPTION):
        assert description in template.AUTHORED_WORDS, description

    #: `render` takes a TITLE, not a pair. A caller that hands it a tuple no longer type-checks,
    #: and a caller that hands it the description prints the description as the title -- read
    #: off the signature so that restoring the pair cannot happen without this node noticing.
    assert list(signature(summary.render).parameters["heading"].annotation.split()) == ["str"]

    #: The alert's description says a threshold OF WHAT -- he refused the shorter wording that
    #: did not, and that refusal is the difference between naming the product and labelling it.
    assert "limiar" in template.ALERT_DESCRIPTION, template.ALERT_DESCRIPTION
    assert "série" in template.ALERT_DESCRIPTION, template.ALERT_DESCRIPTION
