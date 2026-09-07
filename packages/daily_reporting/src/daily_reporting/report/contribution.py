"""Who pulled the deviation — `FR-1308`, `FR-1309`, `FR-1310`, slice `F3`.

A total moved. This decomposes that movement across a declared dimension and says which
parts explain it: for each part, what it was, what it became, and what fraction of the
total's deviation it accounts for.

## The reconciliation is a REFUSAL, not a warning — `SC-1302`

The parts' deviations have to close against the total's. When they do not, **the block is not
published**: a "who pulled it" list that does not add up to what moved is a list that invents
an explanation, and an explanation nobody can check is worse than no explanation at all.

**Over 100% is legitimate and is NOT a failure to reconcile.** One part can explain more than
the whole deviation when other parts moved the opposite way and cancelled some of it — the
classic case where a single country's collapse is masked by everyone else's growth. That is
exactly the finding worth surfacing, so it publishes, and the text says the others
compensated. What does not publish is a sum that does not close.

## Why this is written here and not imported

`anomaly_investigation` already carries this shape — `SegmentContribution`, `reconcile`, a
`NOT_ATTEMPTED` verdict — and it is a good shape. It is also another feature's package, with
its own reason-code namespace and its own contracts. Importing across that line to save a
hundred lines would couple two features whose separation this repository maintains on purpose.
So the idea is reused and the code is not, and this paragraph exists so the next reader knows
the duplication was measured rather than missed.

## What "did not attempt" means, and why it is not "did not reconcile"

Three states, not two. A deviation of zero has no fractions to compute — dividing by it would
manufacture infinities — and a part whose before or after was never measured cannot be given a
share of anything. Those are NOT_ATTEMPTED: the block is absent and the reason is available,
which is different from a reconciliation that was tried and failed.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final, Protocol, cast

from ..view.reading import aggregate, partition_by, sample_size
from ..view.shape import ViewRow

__all__ = [
    "Contribution",
    "ContributionBlock",
    "ContributionGovernance",
    "ContributionGovernanceError",
    "Pull",
    "Verdict",
    "contributions_of",
    "pulls_of",
]

#: Every word the block needs, and the one number that is not a word. Absence of ANY of them
#: refuses the whole file rather than being answered for — the `S-41` rule.
_GOVERNED_WORDS: Final = (
    "heading",
    "heading_emoji",
    "deviation_noun",
    "approximately",
    "became",
    "unit_singular",
    "unit_plural",
    "others",
    "others_noun",
    "compensated",
    "quiet_day",
    "dash",
    "heading_alert",
    #: `T1334` / `FR-1320`, peça 6 do contrato aprovado. Transcritas da frase dele
    #: (`docs/exemplos-analise-dimensional.md`, linhas 140-141), não compostas aqui.
    "discarded_heading",
    "inside_band",
    "none_of",
    "concentrated",
)


class ContributionGovernanceError(ValueError):
    """The governed block file cannot be trusted. Never silently replaced by a default."""


@dataclass(frozen=True, slots=True)
class ContributionGovernance:
    """His words for the block, and the folded-in tolerance — all from `report_governance/`.

    **Not one of these is authored here.** They are transcribed from the contract he approved
    in seven rounds (`OD-108`), and the file that carries them cites his line for each, so the
    next reader checks the transcription instead of trusting it.
    """

    heading: str
    heading_emoji: str
    heading_alert: str
    deviation_noun: str
    approximately: str
    became: str
    unit_singular: str
    unit_plural: str
    others: str
    others_noun: str
    compensated: str
    quiet_day: str
    dash: str
    #: **O que foi medido e ELIMINADO** — `T1334`, peça 6. Quatro palavras dele, e a razão de
    #: serem quatro e não uma frase inteira está no ficheiro governado: das três orações do
    #: exemplo dele só uma tem medição que a sustente hoje. As outras duas ficam lá nomeadas,
    #: cada uma com o que espera — os pares dele, ou os eixos existirem na fonte.
    discarded_heading: str
    inside_band: str
    none_of: str
    concentrated: str
    tolerance: Decimal
    #: The axis's own plural, where his contract carries one. An axis absent from here falls
    #: back to `others_noun`, which is governed too — never to a plural invented on the spot.
    axis_plural: tuple[tuple[str, str], ...] = ()
    #: The axis's own SINGULAR — `OD-153`, 2026-09-06. It exists because a group's counted tail
    #: can leave exactly ONE part behind, and until he gave the word that one part was named
    #: with the word for many. Same shape, same fallback, same refusal as the plural, and the
    #: loader refuses a file that names an axis in one number and not the other.
    axis_singular: tuple[tuple[str, str], ...] = ()

    #: **How many parts one GROUP of the block names before its tail** — `OD-142`, 2026-09-06:
    #: *"the THREE largest"*. It is his number and it lives in the governed file for the reason
    #: `top_n` of the breakdown does: a total written in the package is a total that stops
    #: matching what he asked for without anybody noticing, and
    #: `test_the_loop_enumerates_nothing` sweeps this package for exactly that.
    #:
    #: Zero means *no cut*: every puller in the group is named. It is the declared absence and
    #: not a default, the same way an empty `axis_plural` is.
    top_n: int = 0

    def __post_init__(self) -> None:
        if type(self.top_n) is not int:
            raise ContributionGovernanceError(
                f"top_n is {type(self.top_n).__name__} and not an integer; a cut that is not a "
                "number is not a cut"
            )
        if self.top_n < 0:
            raise ContributionGovernanceError(
                f"top_n is {self.top_n}; a negative cut names no part and counts none either"
            )
        for word in _GOVERNED_WORDS:
            if not str(getattr(self, word)).strip():
                raise ContributionGovernanceError(
                    f"the governed block states an empty {word!r}; a block rendered with a "
                    "word that is not there is a block nobody approved"
                )
        if self.tolerance < 0:
            raise ContributionGovernanceError(
                f"tolerance is {self.tolerance}; a negative slack would refuse a sum that "
                "closes exactly"
            )
        if self.tolerance >= 1:
            raise ContributionGovernanceError(
                f"tolerance is {self.tolerance}; a slack of the whole deviation accepts every "
                "decomposition, which is the reconciliation not happening"
            )

    @property
    def words(self) -> tuple[str, ...]:
        """The vocabulary this file contributes, for `_every_word_is_his`.

        **The per-axis plurals are in here, and leaving them out was a bug caught by asking.**
        A word that reaches the reader and not the condition is a word nobody checked — the
        defect measured in the caller on 2026-09-04, where the delivered text carried four
        words the permission was never shown.
        """
        return (
            tuple(str(getattr(self, word)) for word in _GOVERNED_WORDS)
            + tuple(word for _axis, word in self.axis_plural)
            #: `OD-153`: the singular reaches the reader on a tail that counts one, so it
            #: reaches the permission that judges the words. The bug this repeats is the one
            #: quoted above — a word delivered without the condition ever seeing it.
            + tuple(word for _axis, word in self.axis_singular)
        )

    @classmethod
    def from_document(cls, document: object) -> ContributionGovernance:
        """Build from the parsed governed file, refusing anything it fails to state."""
        if not isinstance(document, dict):
            raise ContributionGovernanceError(
                f"the governed block is {type(document).__name__} and not a mapping"
            )
        stated = cast("dict[str, object]", document)
        for key in (*_GOVERNED_WORDS, "tolerance"):
            if key not in stated:
                raise ContributionGovernanceError(
                    f"the governed block states no {key!r}; silence is not a value"
                )
        said: dict[str, object] = {}
        for word in _GOVERNED_WORDS:
            value = stated[word]
            if not isinstance(value, str):
                raise ContributionGovernanceError(
                    f"{word!r} is {type(value).__name__} and not a word"
                )
            said[word] = value
        # A string in the file and a `Decimal` here, deliberately: a YAML float would round
        # the slack before anyone could see it happen.
        try:
            tolerance = Decimal(str(stated["tolerance"]))
        except InvalidOperation as exc:
            raise ContributionGovernanceError(
                f"tolerance is {stated['tolerance']!r}, which is not a number"
            ) from exc
        #: `OD-153`: the two NUMBERS an axis is named in, read and refused the same way, then
        #: checked against each other. An axis named in one and not the other has no word for
        #: the count it is missing, and the tail would print the word for the other one with
        #: nothing anywhere saying so.
        by_number: dict[str, dict[str, str]] = {}
        for key in ("axis_plural", "axis_singular"):
            stated_words = stated.get(key, {})
            if not isinstance(stated_words, dict):
                raise ContributionGovernanceError(
                    f"{key} is {type(stated_words).__name__} and not a mapping of axis to word"
                )
            named: dict[str, str] = {}
            for axis, word in cast("dict[object, object]", stated_words).items():
                if not isinstance(word, str) or not word.strip():
                    raise ContributionGovernanceError(
                        f"{key} states no word for {axis!r}; an axis listed with nothing "
                        "beside it is an axis nobody named"
                    )
                named[str(axis)] = word
            by_number[key] = named
        for key, other in (("axis_plural", "axis_singular"), ("axis_singular", "axis_plural")):
            for axis in by_number[key].keys() - by_number[other].keys():
                raise ContributionGovernanceError(
                    f"{other} states no word for {axis!r} while {key} does; an axis named in "
                    "one number and not the other has no word for the count it is missing"
                )
        #: `OD-142`. Optional in the document — absence is *no cut*, which is what the block did
        #: before the groups existed — and refused when stated as anything but a whole number,
        #: which is the `S-41` rule rather than a default. `bool` is an `int` by inheritance and
        #: is not a cut, so the exact type is what is asked.
        cut = stated.get("top_n", 0)
        if type(cut) is not int:
            raise ContributionGovernanceError(
                f"top_n is {type(cut).__name__} and not an integer; a cut that is not a number "
                "is not a cut"
            )
        return cls(
            tolerance=tolerance,
            top_n=cut,
            axis_plural=tuple(sorted(by_number["axis_plural"].items())),
            axis_singular=tuple(sorted(by_number["axis_singular"].items())),
            **cast("dict[str, str]", said),
        )

    def plural_for(self, column: str) -> str:
        """His plural for this axis, or the governed noun that stands in for any axis.

        **The fallback is a governed word and not a derivation.** His clause names the axis's
        own plural, and the axes this slice carries are country and game. Only one of the two
        plurals appears anywhere he wrote; inventing the other would be this package authoring
        a word in a report that refuses authored words by design.

        Neither plural is quoted here, and that is the guard working: a docstring naming one
        would copy a governed word into the package, which is exactly what
        `test_the_words_are_written_in_no_python_file_of_this_package` refuses. It caught this
        sentence on its first draft.

        **`OD-153` gave the second plural and this method still has a call site of its own.**
        The clause about the other parts names them without counting them, so there is no
        number for a word to agree with and the counted method would have to invent one.
        """
        for axis, word in self.axis_plural:
            if axis == column:
                return word
        return self.others_noun

    def singular_for(self, column: str) -> str:
        """His singular for this axis, or **empty when he named none** — `OD-153`.

        Empty rather than a fallback, and the asymmetry is the point: every axis needs a word
        for many, so `plural_for` stands one in, while a missing singular has no stand-in that
        is his. Deriving one from the plural would be this package authoring his vocabulary.
        """
        for axis, word in self.axis_singular:
            if axis == column:
                return word
        return ""

    def noun_for(self, column: str, count: int) -> str:
        """The word for ``count`` parts of this axis — **singular at exactly one** (`OD-153`).

        The block's groups cut at `top_n` and count what they left, and a group that left one
        part behind used to name it with the word for many because the file carried no other.

        The two maps are consulted independently, and the fallback does not agree by count: an
        axis he named nothing for keeps `others_noun` for every count, because his vocabulary
        states no singular for that generic noun. Absence measured, not a word chosen here.
        """
        if count == 1:
            singular = self.singular_for(column)
            if singular:
                return singular
        return self.plural_for(column)


class Verdict(StrEnum):
    """What happened when the parts were checked against the whole."""

    #: The parts close against the total's deviation. The block may be published.
    RECONCILED = "reconciled"
    #: They do not close. **The block is refused** — `SC-1302`.
    DID_NOT_RECONCILE = "did_not_reconcile"
    #: There was nothing to check: no deviation, or nothing measurable to decompose.
    NOT_ATTEMPTED = "not_attempted"


def deviation_between(before: Decimal | None, after: Decimal | None) -> Decimal:
    """Quanto uma parte moveu o TOTAL — a aritmética, num sítio só.

    **Uma função com nome porque DUAS coisas perguntam o mesmo**: uma parte de um eixo
    (:class:`Contribution`) e uma célula de dois (:class:`Cell`). Escrita duas vezes, uma delas
    envelhece sozinha — e a que envelhece é a que corre menos.

    **Um lado ausente não contribui para a soma do seu período, e isso é um facto sobre a SOMA e
    não uma afirmação sobre a parte.** Conflar as duas foi o que partiu a primeira versão da
    contribuição: uma parte medida só num dia era descartada, e a reconciliação era depois posta
    a fechar contra um total que ainda a continha.
    """
    return (after or Decimal(0)) - (before or Decimal(0))


def share_of_deviation(deviation: Decimal, total_deviation: Decimal) -> Decimal:
    """A fracção que um movimento representa do movimento inteiro.

    O chamador garante um total não nulo: uma fracção de nada não é um número, e quem chama
    recusa antes de chegar aqui em vez de dividir.
    """
    return deviation / total_deviation


@dataclass(frozen=True, slots=True)
class Cell:
    """Uma célula da interseção de DOIS eixos — `T1334`, peça 5 do contrato aprovado.

    *"uma célula explicando metade do desvio é causa, não coincidência"* — a peça existe para
    separar a concentração real da coincidência de dois eixos que se movem juntos.

    **A identidade é o PAR, e o par não é junto numa string aqui.** A forma como os dois nomes
    aparecem lado a lado no que ele lê é palavra dele, e essa palavra ainda não existe: o
    ficheiro governado não carrega nem o rótulo do núcleo nem o separador. Guardar a chave como
    tupla é o que impede este módulo de escolher a forma por ele.

    A aritmética é a MESMA de :class:`Contribution`, e é a mesma por construção e não por
    coincidência: as duas chamam :func:`deviation_between` e :func:`share_of_deviation`.
    """

    pair: tuple[str, str]
    before: Decimal | None
    after: Decimal | None

    @property
    def deviation(self) -> Decimal:
        return deviation_between(self.before, self.after)

    @property
    def was_measured_twice(self) -> bool:
        """Os dois lados observados, logo há um movimento que se pode mostrar."""
        return self.before is not None and self.after is not None

    def share_of(self, total_deviation: Decimal) -> Decimal:
        return share_of_deviation(self.deviation, total_deviation)


def core_cell_of(cells: Sequence[Cell], total_deviation: Decimal) -> Cell | None:
    """A célula que explica a MAIOR fatia do desvio, ou ``None`` quando não há uma.

    ## Devolve ``None`` em três casos, e os três são respostas

    * **sem células** — nada foi medido, e uma célula inventada seria pior do que nenhuma;
    * **total parado** — uma fracção de zero não é um número; quem chama recusa antes;
    * **empate na maior fatia** — duas células com exactamente o mesmo peso não têm núcleo, e
      escolher uma delas seria este módulo a decidir qual causa contar. **O empate é a resposta.**

    ## Só uma célula medida dos DOIS lados pode ser o núcleo

    Uma célula vista só num dos períodos tem movimento aritmético — entra na conservação, como
    qualquer parte — mas apresentá-la como o núcleo diria a alguém que uma interseção *passou de
    nada para seis*, um movimento que ninguém observou. É a mesma distinção que
    :func:`pulls_of` faz para as partes de um eixo.

    **A fatia é comparada em magnitude.** Uma queda de 55% do desvio e uma subida de 55% são a
    mesma concentração; o sinal diz para que lado, e não quanto.
    """
    if not cells or total_deviation == 0:
        return None
    candidatas = [cell for cell in cells if cell.was_measured_twice]
    if not candidatas:
        return None
    maior = max(abs(cell.deviation) for cell in candidatas)
    empatadas = [cell for cell in candidatas if abs(cell.deviation) == maior]
    if len(empatadas) != 1 or maior == 0:
        return None
    return empatadas[0]


def cells_reconcile(cells: Sequence[Cell], total_deviation: Decimal, tolerance: Decimal) -> bool:
    """A soma dos movimentos das células fecha contra o movimento do total?

    **É a propriedade que separa uma tabela certa de uma que parece certa**, e é a mesma que o
    bloco de um eixo já tem desde a `F3`. Aqui vale mais: uma célula cai se QUALQUER dos dois
    eixos vier vazio, logo a grelha pode encolher por duas razões em vez de uma.

    A tolerância é a do ficheiro governado, e é relativa ao próprio movimento — um resíduo de um
    centésimo sobre um desvio de dez mil não é o mesmo defeito que sobre um desvio de dois.
    """
    residual = total_deviation - sum((cell.deviation for cell in cells), Decimal(0))
    return abs(residual) <= abs(total_deviation) * tolerance


@dataclass(frozen=True, slots=True)
class Contribution:
    """One part of the movement: what it was, what it became, and what share it explains."""

    value: str
    #: ``None`` is *nobody measured this part in that period*, which is NOT zero. A country
    #: with no row yesterday did not sell nothing yesterday — it was not in the source.
    before: Decimal | None
    after: Decimal | None

    @property
    def deviation(self) -> Decimal:
        """How much this part moved the TOTAL, which is arithmetic and not a reading.

        **An absent side contributes nothing to its period's sum, and that is a fact about the
        sum rather than a claim about the part.** The two questions differ and conflating them
        is what broke the first version: a part measured on one day only was dropped, and the
        reconciliation was then asked to close over a total that still contained it. Against
        the real warehouse that refused every block, every day — 190 countries, dozens of them
        seen on one side only.

        So conservation counts every part, and :func:`pulls_of` prints only the parts whose
        before AND after were measured — because a line reading *nothing to 34* would state a
        movement from zero that nobody observed.
        """
        return deviation_between(self.before, self.after)

    @property
    def was_measured_twice(self) -> bool:
        """Both sides observed, so this part has a movement a reader can be shown."""
        return self.before is not None and self.after is not None

    def share_of(self, total_deviation: Decimal) -> Decimal:
        """This part's fraction of the whole movement.

        The caller guarantees a non-zero total: a share of nothing is not a number, and
        `contributions_of` refuses before reaching here rather than dividing.
        """
        return share_of_deviation(self.deviation, total_deviation)


@dataclass(frozen=True, slots=True)
class ContributionBlock:
    """The decomposition of one KPI's movement over one dimension, with its verdict."""

    column: str
    total_before: Decimal
    total_after: Decimal
    parts: tuple[Contribution, ...]
    verdict: Verdict
    residual: Decimal

    @property
    def total_deviation(self) -> Decimal:
        return self.total_after - self.total_before

    @property
    def may_publish(self) -> bool:
        """Only a reconciled block reaches a person — `SC-1302`."""
        return self.verdict is Verdict.RECONCILED and bool(self.parts)

    @property
    def others_compensated(self) -> bool:
        """True when a part explains more than the whole, because others moved against it.

        This is a legitimate reading and the text says so; it is NOT a reconciliation failure,
        and conflating the two would suppress the most interesting finding the block can make.
        """
        if not self.total_deviation:
            return False
        return any(abs(part.share_of(self.total_deviation)) > 1 for part in self.parts)


@dataclass(frozen=True, slots=True)
class Discarded:
    """One hypothesis MEASURED and eliminated, on one indicator and one axis — `T1334`.

    **This is the sixth piece of his approved contract**, and its reason is written there
    (`docs/exemplos-analise-dimensional.md`, line 154): *"as hipóteses medidas e eliminadas; é o
    que impede o leitor de duvidar"*. A reader who is not told what was ruled out redoes the
    ruling out by hand.

    ## What this carries is the COMPLEMENT of the block above it, and nothing else

    ``inside`` counts the parts of this axis whose own ninety-day band the last movement did NOT
    leave — the parts that were measured and stayed put. ``concentrated`` says whether ANY part
    left it, which is what separates *the others stayed inside their band* from *nothing
    concentrated at all*: his contract writes those as two different clauses, and they are.

    **An axis this repository declares UNAVAILABLE can never appear here**, and the distinction
    is the point rather than a detail. *Unavailable* and *measured and discarded* are OPPOSITE
    statements: the report already names the unavailable axes with the governed sentence that
    says why (`FR-1316`), and listing one here would claim a measurement of exactly what this
    repository declares it cannot measure. To the reader that reads as coverage, which is the
    reverse of what the piece exists to give. The two groups never share a list or a sentence.
    """

    kpi_label: str
    column: str
    inside: int
    concentrated: bool


class DiscardedCoverageError(ValueError):
    """An axis declared UNAVAILABLE was offered as a hypothesis measured and eliminated."""


class _NamesUnavailableAxes(Protocol):
    """The one question this rule asks of the breakdown governance, declared rather than imported.

    Stating the shape instead of importing `BreakdownGovernance` keeps the direction of the
    dependency where it already was — the renderer knows both, and neither of these two modules
    needs to know the other.
    """

    def unavailable_for(self, kpi: str) -> Sequence[_HasColumn]: ...


class _HasColumn(Protocol):
    #: Uma propriedade e nao um atributo, e um `Sequence` e nao um `tuple`: as duas escolhas sao
    #: a mesma. Um atributo declarado num Protocol e leitura E escrita, e um `tuple` e invariante
    #: -- as duas formas exigem tipo IDENTICO em vez de compativel, e a governanca real deixa de
    #: casar por ser mais especifica do que o pedido. Medido: o pyright recusou a primeira forma.
    @property
    def column(self) -> str: ...


def refuse_unavailable_coverage(one: Discarded, governance: _NamesUnavailableAxes | None) -> None:
    """Refuse a hypothesis whose axis this repository declares it cannot measure — `T1334`.

    **An error, not a line quietly dropped**, and the difference is the second half of the task.
    Dropping it would let the block shrink while nobody learns that something claimed coverage it
    does not have; raising names the axis and the indicator, so whoever built the entry answers
    for it.

    **The refusal lives beside the data and not inside the renderer**, which is the difference
    between a guarantee and a convention: today's caller only builds entries for permitted axes,
    and that is true and fragile — nothing obliges the next one to know the rule.
    """
    if governance is None:
        return
    if any(axis.column == one.column for axis in governance.unavailable_for(one.kpi_label)):
        raise DiscardedCoverageError(
            f"{one.column!r} / {one.kpi_label!r}: an axis declared unavailable cannot be a "
            "hypothesis measured and discarded -- the two statements are opposite"
        )


@dataclass(frozen=True, slots=True)
class Pull:
    """One part worth naming in the block: what moved, on which KPI, and how much it explains.

    **A flat list across KPIs, because that is the shape he approved.** His example names a
    gateway on one line and a country on the next, each carrying its own indicator — the block
    answers *who pulled the day*, not *how each indicator decomposes*.
    """

    value: str
    kpi_label: str
    column: str
    before: Decimal
    after: Decimal
    share: Decimal
    format_type: str
    others_compensated: bool

    @property
    def deviation(self) -> Decimal:
        return self.after - self.before


def pulls_of(
    block: ContributionBlock,
    kpi_label: str,
    format_type: str = "",
    relevant: Collection[str] | None = None,
) -> tuple[Pull, ...]:
    """The block's parts as lines for one KPI, or **nothing at all** when it may not publish.

    `SC-1302` lives here as much as in the verdict: a decomposition that did not reconcile
    produces no line, so a refusal cannot leak into the message as a partial list.

    ``relevant`` names the parts worth printing — `FR-1310`, and `D-1305` decides what makes
    one relevant. **It filters the LINES and never the reconciliation**, and the order is the
    whole point: the sum has to close over every part that moved, and only then does the
    message name the few that are worth a reader's second. Filtering first would let a
    decomposition that does not add up publish anyway, by dropping the parts that broke it.

    ``None`` is *nobody asked*, which is not *nothing is relevant*: it prints every puller.
    """
    if not block.may_publish:
        return ()
    total = block.total_deviation
    #: **Only the parts that moved WITH the deviation are pullers**, and the first render is
    #: what made that obvious: a country that rose while the day fell came out listed under
    #: *who pulled the deviation* with a share of minus one hundred per cent. It did not pull
    #: the day; it resisted it — and the parts that resisted are exactly what the compensation
    #: clause is already about. Derived from the sign, not chosen.
    #:
    #: The clause itself is PER PART and not per block. It says *the others rose and made up
    #: part of it*, which is true beside a part explaining more than the whole and false beside
    #: one explaining a third of it. The first render put it on every line.
    return tuple(
        Pull(
            value=part.value,
            kpi_label=kpi_label,
            column=block.column,
            before=part.before or Decimal(0),
            after=part.after or Decimal(0),
            share=share,
            format_type=format_type,
            others_compensated=share > 1,
        )
        for part in block.parts
        if part.was_measured_twice
        for share in (part.share_of(total),)
        if share > 0 and (relevant is None or part.value in relevant)
    )


def contributions_of(
    before_rows: Sequence[ViewRow],
    after_rows: Sequence[ViewRow],
    value_column: str,
    column: str,
    *,
    excluded: Sequence[str] = (),
    sample_floor: int = 0,
    tolerance: Decimal = Decimal("0.01"),
) -> ContributionBlock:
    """Decompose the movement between two periods across ``column``.

    Both periods are partitioned by the same key and aggregated by :func:`aggregate`, which is
    reused rather than reimplemented for the reason `F1` already relies on: it computes a rate
    as ``SUM(num)/SUM(den)`` over the rows it is handed, so each part's before and after are
    that part's own numbers.

    A part present in only one of the two periods keeps ``None`` on the side nobody measured:
    a country absent yesterday did not sell nothing yesterday. **It still enters the sum**,
    because it is part of the total either way — see :attr:`Contribution.deviation` for why
    those are two different questions, and for what happened when they were treated as one.
    """
    before = _measured(before_rows, value_column, column, excluded, sample_floor)
    after = _measured(after_rows, value_column, column, excluded, sample_floor)

    #: **The total is read over the SAME rows the partitions come from.** It was read over the
    #: raw rows, and that made one refusal certain rather than possible: `excluded` names values
    #: that are NOT values of the axis — the source's own `(Total)` marker sitting beside its
    #: parts — and `partition_by` drops them while a raw aggregate keeps them. The whole was
    #: then the parts PLUS their own aggregate, so the `game` axis could never close.
    #:
    #: What still counts against the block is a part the SAMPLE FLOOR withheld: it is a real
    #: value of the axis that really moved, and a list that leaves it out really does not
    #: explain the day. That refusal is `SC-1302` working, not the same defect.
    total_before = aggregate(_axis_rows(before_rows, column, excluded), value_column)
    total_after = aggregate(_axis_rows(after_rows, column, excluded), value_column)
    if total_before is None or total_after is None:
        return _not_attempted(column, total_before, total_after)

    total_deviation = total_after - total_before
    if total_deviation == 0:
        #: Nothing moved. There is no deviation to attribute, and every share would be a
        #: division by zero — which is why this is NOT_ATTEMPTED and not a failed check.
        return ContributionBlock(
            column=column,
            total_before=total_before,
            total_after=total_after,
            parts=(),
            verdict=Verdict.NOT_ATTEMPTED,
            residual=Decimal(0),
        )

    #: The UNION, not the intersection. Every partition of the source is part of the total, so
    #: every one of them has to be in the sum that checks it.
    parts = tuple(
        Contribution(value=value, before=before.get(value), after=after.get(value))
        for value in sorted(set(before) | set(after))
    )

    if not parts:
        return _not_attempted(column, total_before, total_after)

    residual = total_deviation - sum((part.deviation for part in parts), Decimal(0))
    closes = abs(residual) <= abs(total_deviation) * tolerance
    return ContributionBlock(
        column=column,
        total_before=total_before,
        total_after=total_after,
        parts=parts,
        verdict=Verdict.RECONCILED if closes else Verdict.DID_NOT_RECONCILE,
        residual=residual,
    )


def _axis_rows(
    rows: Sequence[ViewRow], column: str, excluded: Sequence[str]
) -> tuple[ViewRow, ...]:
    """The rows that belong to a VALUE of the axis, and no others.

    A row whose axis value is missing, is not text, or is a marker the governance excludes is
    not part of the axis — so it is not part of the whole the axis is asked to explain either.
    Read through :func:`partition_by` rather than re-deciding here: two answers to *what is a
    value of this axis* is one answer too many.
    """
    return tuple(row for _value, group in partition_by(rows, column, excluded) for row in group)


def _measured(
    rows: Sequence[ViewRow],
    value_column: str,
    column: str,
    excluded: Sequence[str],
    sample_floor: int,
) -> dict[str, Decimal]:
    """Each part's number for one period, omitting what was not measurable.

    The sample floor applies here for the same reason it applies to a breakdown (`SC-1301`):
    a rate over a handful of cases is not a rate to attribute a movement to.
    """
    answered: dict[str, Decimal] = {}
    for value, group in partition_by(rows, column, excluded):
        number = aggregate(group, value_column)
        if number is None:
            continue
        size = sample_size(group)
        if size is not None and size < sample_floor:
            continue
        answered[value] = number
    return answered


def _not_attempted(
    column: str, total_before: Decimal | None, total_after: Decimal | None
) -> ContributionBlock:
    return ContributionBlock(
        column=column,
        total_before=total_before if total_before is not None else Decimal(0),
        total_after=total_after if total_after is not None else Decimal(0),
        parts=(),
        verdict=Verdict.NOT_ATTEMPTED,
        residual=Decimal(0),
    )
