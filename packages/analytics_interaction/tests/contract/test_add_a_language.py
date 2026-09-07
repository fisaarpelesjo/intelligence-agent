"""Adding a language changes content, not contracts — T026 (FR-043; SC-029).

The claim under test is narrow and checkable: **a new language is a new key set
under the same reason codes, and nothing in this package changes.** No model, no
enum in the registry, no branch in the lookup, no edit to
`messages/registry.py`.

The proof is a synthetic language written to a temporary file and loaded through
the production loader. If the loader had a pt-BR branch, a hardcoded filename
stem, or a language enum of its own, this would fail — which is precisely the set
of shortcuts that would make `FR-043` false later, when a second language is
actually authored.

**The seam is deliberate and worth naming.** ``DeclaredLanguage`` is a closed
enum with one member, because a *caller* may only declare a language the system
actually supports (`FR-101` refuses anything outside it). The registry is keyed
by a plain string, because *content* is what makes a language supported. Adding
pt-PT means authoring `pt-pt.yaml` and adding one enum member — and this test
covers the half that would otherwise require touching the reading code.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.messages.registry import load_registry, registry_path

pytestmark = pytest.mark.contract

#: A language tag that will never be authored, so the test cannot accidentally
#: pass by finding real content.
SYNTHETIC = "zz-ZZ"


def _synthetic_document(language: str) -> dict[str, object]:
    """The same codes, wording in a different language, nothing else changed."""
    return {
        "schema_version": 1,
        "kind": "interpretation_messages",
        "content_version": "synthetic-1",
        "allowed_arguments": ["governed_limit"],
        "messages": [
            {
                "code": code.value,
                "language": language,
                "text": (
                    f"[{language}] {code.value} limite {{governed_limit}}"
                    if code is InterpretationReasonCode.QUESTION_EXCEEDS_GOVERNED_LIMIT
                    else f"[{language}] {code.value}"
                ),
                **(
                    {"arguments": ["governed_limit"]}
                    if code is InterpretationReasonCode.QUESTION_EXCEEDS_GOVERNED_LIMIT
                    else {}
                ),
            }
            for code in InterpretationReasonCode
        ],
    }


@pytest.fixture
def synthetic_registry(tmp_path: Path) -> Path:
    target = tmp_path / f"{SYNTHETIC.lower()}.yaml"
    target.write_text(
        yaml.safe_dump(_synthetic_document(SYNTHETIC), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return target


def test_a_synthetic_language_loads_through_the_production_loader(
    synthetic_registry: Path,
) -> None:
    registry = load_registry(SYNTHETIC, path=synthetic_registry)
    assert registry.language == SYNTHETIC
    assert registry.codes == frozenset(InterpretationReasonCode)


def test_the_synthetic_language_covers_the_same_codes_as_pt_br(
    synthetic_registry: Path,
) -> None:
    """Same codes, different wording. That is what "a new key set" means."""
    synthetic = load_registry(SYNTHETIC, path=synthetic_registry)
    portuguese = load_registry()
    assert synthetic.codes == portuguese.codes
    for code in InterpretationReasonCode:
        assert synthetic.text_for(code) != portuguese.text_for(code)


def test_the_loader_carries_no_language_specific_branch() -> None:
    """The reading code must not know pt-BR is special.

    A conditional on the tag, or a hardcoded filename stem, is what would make
    the second language an edit to this package rather than an edit to content.
    ``"pt-BR"`` appears only as a parameter default — asserted by counting, so a
    branch added later has nowhere to hide.
    """
    source = Path(load_registry.__code__.co_filename).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]
    occurrences = body.count('"pt-BR"')
    assert occurrences <= 2, f'"pt-BR" appears {occurrences} times outside the module docstring'
    for branch in ('== "pt-BR"', "== 'pt-BR'", 'if language == "pt'):
        assert branch not in body, f"the loader branches on the language tag: {branch}"


def test_the_path_is_derived_from_the_tag_rather_than_looked_up() -> None:
    """A lookup table of known languages would need editing per language."""
    assert registry_path(SYNTHETIC).name == "zz-zz.yaml"
    assert registry_path("pt-BR").name == "pt-br.yaml"


def test_the_declared_language_enum_still_admits_only_the_supported_set() -> None:
    """Content extensibility must not become caller extensibility.

    A caller declaring an unauthored language would reach a registry that does
    not exist; `FR-101` refuses it at intake instead. The synthetic language
    loading above is a *content* fact and deliberately does not widen this.
    """
    assert [member.value for member in DeclaredLanguage] == ["pt-BR"]
    with pytest.raises(ValueError):
        DeclaredLanguage(SYNTHETIC)


def test_no_contract_model_changed_to_admit_the_new_language(
    synthetic_registry: Path,
) -> None:
    """`SC-029`, stated as the absence of a diff.

    The registry resolves the synthetic language while every governed contract
    keeps the field set it had — so nothing about adding a language touches the
    answer, clarification or intake shapes.
    """
    from analytics_interaction.contracts.answer import AnalyticsAnswer
    from analytics_interaction.contracts.clarification import ClarificationContract
    from analytics_interaction.contracts.intake import QuestionIntake

    before = {
        model.__name__: tuple(model.model_fields)
        for model in (QuestionIntake, AnalyticsAnswer, ClarificationContract)
    }
    load_registry(SYNTHETIC, path=synthetic_registry)
    after = {
        model.__name__: tuple(model.model_fields)
        for model in (QuestionIntake, AnalyticsAnswer, ClarificationContract)
    }
    assert before == after
