"""Fixture governed-payload corpus — T088 (FR-072; SC-034).

**TEST-ONLY.** Every object here is a synthetic `AnalyticsAnswer` built directly from `003`'s
public contracts, plus the fixture capability matrix and resolved-wording lookup that Phase C
needs to render one. None of it is evidence of anything: `D-18` upstream carries no claim-class
wording and `D-28` locally carries no capability matrix, so production assembles no answer and
renders nothing. A fixture proves contract behaviour and says nothing about availability.

The corpus is chosen to cover the cases where preservation is hardest, not the easy ones:

* **maximum caveat count** — the case where a renderer showing a subset is most tempting;
* **multi-side provenance** — two sides, unmerged and unsummarised (`SC-023`);
* **a suppressed cell** — a limitation claim carrying no value at all;
* **a zero-row result** — a factual claim whose value is genuinely zero, which must not be rendered
  as "no data" or omitted;
* **all four claim classes together** — the distinguishability case (`SC-022`); * **an unresolved
  wording reference** — the ADR 0026 withhold case, where a reference has no resolved
  string and the correct behaviour is to withhold rather than render the reference.

The fixture wording lookup is a plain mapping. `004` never resolves a reference; the lookup stands
in for the resolution `003` performs inside ADR 0017's new module.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from analytics_interaction.contracts import LocalizedRef
from analytics_interaction.contracts.answer import (
    AnalyticsAnswer,
    AnswerClaim,
    AttributedCaveat,
    CaveatOrigin,
    CaveatSet,
    ClaimClass,
    ComparisonBasis,
    DeclaredLanguage,
)
from analytics_interaction.contracts.intent import ResolvedIntent
from analytics_query.contracts.provenance import CostProvenance
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.result_provenance import ResultProvenance, SourceUpdate

from channel_integration.outbound.payload import GovernedAnswerPayload, ResolvedWording

__all__ = [
    "CORPUS",
    "FIXTURE_CAPABILITY",
    "FixtureWording",
    "answer_with",
    "payload_for",
]

_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_REFERENCE_DATE = date(2026, 7, 31)

#: Obviously synthetic. No real metric, source, release or policy identifier appears here.
_CATALOG_RELEASE = "fixture-catalog-release-1"
_POLICY_VERSION = "fixture-policy-1"
_VOCABULARY_VERSION = "fixture-vocabulary-1"


class FixtureWording:
    """Stands in for the resolution `003` performs. A plain lookup, and nothing more.

    Satisfies `outbound.payload.ResolvedWording` structurally. A code absent from the mapping
    returns ``None``, which is the withhold condition ADR 0026 requires — so the corpus can
    exercise the missing-string case without any special mode.
    """

    def __init__(self, texts: dict[str, str], content_version: str = "fixture-content-1") -> None:
        self.content_version = content_version
        self._texts = dict(texts)

    def text_for(self, code: str) -> str | None:
        return self._texts.get(code)


class FixturePayload:
    """An answered outcome: the answer, unaltered, beside its resolved wording.

    The attributes are annotated at class level so this satisfies
    `outbound.payload.GovernedAnswerPayload` **structurally** — which is the whole point of that
    protocol. A fixture that only matched at runtime would let the production seam diverge from what
    the tests exercise without anything noticing.
    """

    answer: AnalyticsAnswer
    wording: ResolvedWording

    def __init__(self, answer: AnalyticsAnswer, wording: ResolvedWording) -> None:
        self.answer = answer
        self.wording = wording


def _intent(metrics: tuple[str, ...] = ()) -> ResolvedIntent:
    """The resolved intent. ``metrics`` defaults to empty, and `F98` is why it is a parameter.

    Every entry in this corpus resolved **no** metrics, and for six entries that was harmless. It
    stopped being harmless when `F97` made the renderer decide, from this very list, whether a claim
    subject is the metric's internal identifier or a row label a reader needs. With the list always
    empty, the corpus could not tell the two apart -- measured by the reviewer, who planted the leak
    coming back and watched all 425 renderer nodes pass.

    So the default stays for the six entries that never cared, and the seventh passes a real list.
    """
    return ResolvedIntent(
        metrics=metrics,
        language=DeclaredLanguage.PT_BR,
        reference_date=_REFERENCE_DATE,
        catalog_release=_CATALOG_RELEASE,
        policy_version=_POLICY_VERSION,
        vocabulary_version=_VOCABULARY_VERSION,
    )


def _provenance(source_id: str) -> ResultProvenance:
    """One side's provenance. Two of these in a corpus entry is the unmerged case."""
    return ResultProvenance(
        contributing_sources=(source_id,),
        resolved_metric_versions=(f"{source_id}:metric-v1",),
        data_revisions=(f"{source_id}:revision-1",),
        data_as_of=_AT,
        source_updates=(SourceUpdate(source_id=source_id, last_updated_at=_AT),),
        dimensional_coverage=("fixture-dimension",),
        limitations=(),
        cost=CostProvenance(dry_run_bytes=1, actual_bytes=1, maximum_bytes_billed=1),
        execution_identifiers=(f"{source_id}:execution-1",),
        policy_version=_POLICY_VERSION,
        catalog_release_id=_CATALOG_RELEASE,
    )


def _claim(
    claim_class: ClaimClass,
    subject: str,
    code: str,
    value: Decimal | None = None,
    unit: str | None = None,
    derived_from: tuple[str, str] | None = None,
    basis: ComparisonBasis | None = None,
) -> AnswerClaim:
    """One claim. A calculated comparison must carry its two operands and its basis.

    That requirement is `003`'s, and it is honoured here rather than worked around: a comparison
    without a recorded basis would be a verdict nobody could trace back to a formula and a window.
    """
    return AnswerClaim(
        claim_class=claim_class,
        subject=subject,
        value=value,
        unit=unit,
        message=LocalizedRef(code=code, language="pt-BR", content_version=_VOCABULARY_VERSION),
        derived_from=derived_from,
        basis=basis,
    )


#: The fixture basis for the one comparison claim in the corpus. Formula and reason are fixture
#: strings; `D-18` owns the real formula vocabulary and declares none.
_FIXTURE_BASIS = ComparisonBasis(
    formula="fixture-difference-formula",
    window_start=date(2026, 6, 1),
    window_end=date(2026, 6, 30),
    chosen_because="fixture-comparable-window",
)


#: One caveat-class analytics code, picked from `002`'s own ALLOW_WITH_CAVEAT set rather than
#: invented. A caveat carrying a DENY code would be a refusal wearing a caveat's clothes.
_CAVEAT_CODE = AnalyticsReasonCode.RESULT_CELL_SUPPRESSED


def _caveats(count: int) -> CaveatSet:
    """``count`` caveats, each already carrying resolved wording upstream."""
    return CaveatSet(
        caveats=tuple(
            AttributedCaveat(
                code=_CAVEAT_CODE,
                message_pt_br=f"ressalva governada de fixture numero {index}",
                origin=CaveatOrigin.SINGLE,
            )
            for index in range(1, count + 1)
        ),
        total=count,
    )


def answer_with(
    claims: tuple[AnswerClaim, ...],
    caveat_count: int,
    provenance: tuple[ResultProvenance, ...],
    metrics: tuple[str, ...] = (),
) -> AnalyticsAnswer:
    """One synthetic answer. Every field is a fixture value."""
    return AnalyticsAnswer(
        interpreted=_intent(metrics),
        claims=claims,
        caveats=_caveats(caveat_count),
        provenance=provenance,
        language=DeclaredLanguage.PT_BR,
        reference_date=_REFERENCE_DATE,
        catalog_release=_CATALOG_RELEASE,
        policy_version=_POLICY_VERSION,
        vocabulary_version=_VOCABULARY_VERSION,
    )


_ALL_CLASSES = (
    _claim(
        ClaimClass.FACTUAL_RESULT, "instalações em julho", "claim.factual", Decimal("1234"), "un"
    ),
    _claim(
        ClaimClass.CALCULATED_COMPARISON,
        "variação contra junho",
        "claim.comparison",
        Decimal("-12.5"),
        "%",
        derived_from=("instalações em julho", "instalações em junho"),
        basis=_FIXTURE_BASIS,
    ),
    _claim(ClaimClass.INTERPRETATION, "leitura do período", "claim.interpretation"),
    _claim(ClaimClass.LIMITATION, "cobertura parcial", "claim.limitation"),
)

_WORDING = FixtureWording(
    {
        "claim.factual": "o total apurado no período consultado",
        "claim.comparison": "a diferença apurada contra o período anterior",
        "claim.interpretation": "associação temporal, sem afirmação de causa",
        "claim.limitation": "parte das fontes não cobre o período inteiro",
        "claim.zero": "nenhuma linha foi retornada para o período",
        "claim.suppressed": "a célula foi suprimida por política de divulgação",
    }
)

#: The three names below are public deliberately. They are read by
#: `tests/contract/test_claim_classes.py`, and a leading underscore would declare them private to
#: this module while another one imported them -- which is what pyright's `reportPrivateUsage`
#: caught in CI after the first attempt named them `_METRIC_ID` and friends. `CORPUS`,
#: `FIXTURE_CAPABILITY` and `payload_for` are public for the same reason; `_WORDING` and
#: `_ALL_CLASSES` keep the underscore because nothing outside reads them.
#:
#: `F98`. The metric identifier the seventh corpus entry resolves, and the subject of one of its two
#: claims. Shaped like the identifier that actually leaked to the owner -- `summary_new_trials` on
#: every label line -- rather than like a word, so a node asserting its absence is asserting about
#: the kind of string that caused the finding.
INTERNAL_METRIC_ID = "summary_fixture_metric"

#: `F98`. A row label: authorised as a subject, NOT a metric, and therefore something the reader
#: must still see. This is the half the first attempt at `F97` deleted.
ROW_LABEL_SUBJECT = "Android"

#: `F98`. The seventh entry's name, bound once so a node cannot look it up by a string that drifts.
INTERNAL_SUBJECT_ENTRY = "an internal metric identifier beside a row label"

#: Every corpus entry, named for the property it makes hard. `T089` renders each against four
#: channels; `T093` asserts that what cannot be carried intact is withheld.
CORPUS: dict[str, FixturePayload] = {
    "all four claim classes": FixturePayload(
        answer_with(_ALL_CLASSES, 2, (_provenance("fixture-source-a"),)), _WORDING
    ),
    "maximum caveat count": FixturePayload(
        answer_with(_ALL_CLASSES[:1], 12, (_provenance("fixture-source-a"),)), _WORDING
    ),
    "multi-side provenance": FixturePayload(
        answer_with(
            _ALL_CLASSES[:2],
            1,
            (_provenance("fixture-source-a"), _provenance("fixture-source-b")),
        ),
        _WORDING,
    ),
    "a suppressed cell": FixturePayload(
        answer_with(
            (_claim(ClaimClass.LIMITATION, "célula suprimida", "claim.suppressed"),),
            1,
            (_provenance("fixture-source-a"),),
        ),
        _WORDING,
    ),
    "a zero-row result": FixturePayload(
        answer_with(
            (
                _claim(
                    ClaimClass.FACTUAL_RESULT,
                    "instalações no período",
                    "claim.zero",
                    Decimal("0"),
                    "un",
                ),
            ),
            1,
            (_provenance("fixture-source-a"),),
        ),
        _WORDING,
    ),
    "an unresolved wording reference": FixturePayload(
        answer_with(
            (_claim(ClaimClass.FACTUAL_RESULT, "sem wording", "claim.absent", Decimal("7"), "un"),),
            1,
            (_provenance("fixture-source-a"),),
        ),
        _WORDING,
    ),
    # `F98`. The seventh entry, and the only one whose intent resolved a metric.
    #
    # The other six pass `metrics=()`, which made them **blind** to the property `F97` created: the
    # renderer decides from `interpreted.metrics` whether a claim's subject is the metric's internal
    # identifier -- suppressed, because a reader should not be shown `INTERNAL_METRIC_ID` -- or a
    # row label, kept, because it is the only thing saying which figure is which. With no metrics
    # resolved, no
    # subject can be internal, so the suppression branch was never taken and the leak could return
    # unnoticed. Measured by the reviewer: 425 renderer nodes passed with the leak planted back.
    #
    # It carries **both** kinds deliberately. An entry with only the internal subject would prove
    # the identifier is hidden while saying nothing about the row labels that must survive -- and
    # the first attempt at `F97` deleted exactly those. One entry, both halves, so neither can be
    # broken alone.
    INTERNAL_SUBJECT_ENTRY: FixturePayload(
        answer_with(
            (
                _claim(
                    ClaimClass.FACTUAL_RESULT,
                    INTERNAL_METRIC_ID,
                    "claim.factual",
                    Decimal("18432"),
                    "un",
                ),
                _claim(
                    ClaimClass.FACTUAL_RESULT,
                    ROW_LABEL_SUBJECT,
                    "claim.factual",
                    Decimal("12105"),
                    "un",
                ),
            ),
            1,
            (_provenance("fixture-source-a"),),
            metrics=(INTERNAL_METRIC_ID,),
        ),
        _WORDING,
    ),
}


def payload_for(name: str) -> FixturePayload:
    """One corpus entry by name, so a failure reports which property broke."""
    return CORPUS[name]


#: Structural check that the corpus satisfies the port, performed at import time. An annotated
#: binding rather than a function, so the check actually runs instead of being dead code a linter
#: has to be told to excuse.
_CORPUS_SATISFIES_THE_PORT: GovernedAnswerPayload = CORPUS["all four claim classes"]


#: The fixture capability matrix entry. Every value is a fixture value: `D-28` is undeclared, so
#: production cannot resolve this at all and withholds instead. Generous limits on purpose — the
#: continuation and withhold cases are driven by tests that shrink them deliberately.
FIXTURE_CAPABILITY: dict[str, object] = {
    "maximum_body_characters": 4000,
    "expressible_structures": ["paragraph", "list"],
    "permitted_degradations": ["table-as-list", "emphasis-dropped"],
    "continuation_mechanism": "fixture-continuation",
    "ordering_guarantee": "ordered",
    "disclosure_wording": {
        "table-as-list": "a tabela foi apresentada como lista neste canal",
        "emphasis-dropped": "a ênfase não é expressável neste canal",
    },
    "claim_class_labels": {
        "label_factual_result": "Resultado",
        "label_calculated_comparison": "Comparação",
        "label_interpretation": "Interpretação",
        "label_limitation": "Limitação",
    },
}
