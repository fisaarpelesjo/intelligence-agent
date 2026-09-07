"""From the view's rows to one KPI's reading — **and the ZERO rule lives here** — `T822`.

## Why this module exists at all, and it is the finding that created it

The message that would have gone to the owner's chat was composed by a script that was
**never committed**. `Reading(...)` was constructed only in tests, so `T822` — *a KPI whose
value is zero is reported as zero with the footnote, never omitted* — was green over
fixtures while the seam it describes did not exist as code.

**And the uncommitted script had exactly the defect `T822` forbids.** It answered ``None``
when a numerator was falsy, and ``0`` is falsy. So `Chargeback (%)` came out as ``-`` on a
day whose measured value was **zero chargebacks** — good news rendered as *we do not know*.

> **Absent is not zero.** A KPI with no row, or with a null in the column that carries its
> number, has no value. A KPI whose rows sum to zero **has the value zero**, and reporting
> that as an absence hides a fact about the business — the same reasoning `OD-14-G` used
> for `Semiannual (%)` and its 60.641 zero rows.

## What is read and what is handed in

The **aggregation class** is read from the rows, because the view states it. The **column**
is a parameter, because `FR-806` puts that answer in the metric's catalog contract and this
module may not infer it — handed a different column it reads a different number, which is
what makes it drivable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Final

from ..contracts import ReportReasonCode, ReportRefusal
from .shape import EVENT_DATE_COLUMN, ViewRow

__all__ = [
    "AGGREGATION_CLASS_COLUMN",
    "DENOMINATOR_COLUMN",
    "NUMERATOR_COLUMN",
    "SNAPSHOT",
    "aggregate",
    "aggregate_by",
    "aggregation_class_of",
    "partition_by",
    "partition_by_pair",
    "sample_size",
]

#: The view's own columns for a ratio, and the column that states how to aggregate. These
#: are the SHAPE of the source, not its content: no KPI name and no section name is written
#: anywhere in this package.
NUMERATOR_COLUMN: Final = "numerator"
DENOMINATOR_COLUMN: Final = "denominator"
AGGREGATION_CLASS_COLUMN: Final = "aggregation_class"

#: How the view spells the three classes. Read from the rows and compared against these,
#: rather than assumed: a class this module does not know must refuse, because guessing
#: between a sum and a snapshot is guessing the number.
RATIO: Final = "RATIO"
SNAPSHOT: Final = "SNAPSHOT"
COUNT: Final = "COUNT"


def aggregation_class_of(rows: Sequence[ViewRow]) -> str:
    """The one aggregation class these rows state, or a refusal.

    Two classes across one KPI's rows means the KPI has no class, so nothing is chosen for
    it — the same reasoning `semantic/metrics/new_trials.yaml` records for its own.
    """
    stated = {
        str(row[AGGREGATION_CLASS_COLUMN]).strip()
        for row in rows
        if isinstance(row.get(AGGREGATION_CLASS_COLUMN), str)
    }
    if len(stated) != 1:
        raise ReportRefusal(
            ReportReasonCode.REPORT_KPI_NOT_DERIVABLE,
            f"these rows state {sorted(stated)} as {AGGREGATION_CLASS_COLUMN!r}; a KPI with "
            f"no single class has no class, and nothing is chosen for it",
        )
    only = stated.pop()
    if only not in (RATIO, SNAPSHOT, COUNT):
        raise ReportRefusal(
            ReportReasonCode.REPORT_KPI_NOT_DERIVABLE,
            f"{only!r} is an aggregation class this reader does not know; guessing between a "
            f"sum and a snapshot is guessing the number",
        )
    return only


def _numbers(rows: Iterable[ViewRow], column: str) -> list[Decimal]:
    """Every usable number in ``column``, and **an empty list means ABSENT, not zero**."""
    found: list[Decimal] = []
    for row in rows:
        value = row.get(column)
        if value is None or isinstance(value, bool):
            continue
        try:
            found.append(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            continue
    return found


def _paired(rows: Iterable[ViewRow]) -> tuple[list[Decimal], list[Decimal]]:
    """A rate's two halves, **taken row by row and only when BOTH are there**.

    ## The defect this exists to stop, measured against the warehouse on 2026-09-04

    The two columns used to be read independently, so a row carrying one half and a null in the
    other put its number on one side of the division and nothing on the other.

    The number he read was wrong by a measurable amount: on 2026-08-15 `Not renewed (%)` went
    out as `0,6228 %` where the paired arithmetic gives `0,5028 %`. Eight of the last ninety
    days moved.

    ## Both shapes exist, and this paragraph replaces one that said otherwise

    It used to read *"the rate was inflated, ALWAYS in the same direction, because an unmatched
    numerator can only push it up"*. That is true of the two KPIs it named and false as a claim
    about this function, which serves every rate. Counted over the ninety days ending
    2026-09-03, every RATIO KPI in the view that carries an unpaired row at all:

        Not renewed (%)     813 numerator-without-denominator,      0 the other way
        Cancellations (%)   194 numerator-without-denominator,      0 the other way
        CAC (R$)              0 numerator-without-denominator, 16.022 the other way

    An orphan DENOMINATOR pushes a rate DOWN, and `CAC (R$)` is made of nothing else. It is
    `unavailable` in the catalogue and reaches no report today, which is why the error never
    surfaced — not because the shape does not occur.

    **This function drops both, and always did** (`if not above or not below`). What was wrong
    was the sentence, which asserted a direction the measurement does not carry.

    The counts are dated because the window slides: `809` was written yesterday and reads `813`
    today over a window ending one day later. A number about a rolling window that carries no
    date is a number that goes quietly false.

    A row missing either half is not half a measurement. It is a row this rate cannot be
    computed from, and dropping the pair is the only reading that keeps `SUM(num)/SUM(den)`
    a statement about the same set of cases on both sides.
    """
    numerators: list[Decimal] = []
    denominators: list[Decimal] = []
    for row in rows:
        above = _numbers([row], NUMERATOR_COLUMN)
        below = _numbers([row], DENOMINATOR_COLUMN)
        if not above or not below:
            continue
        numerators.extend(above)
        denominators.extend(below)
    return numerators, denominators


def _the_last_day_in(rows: Sequence[ViewRow], day_column: str) -> list[ViewRow]:
    """The rows of the LAST day ``rows`` cover — every one of them, for the caller to sum.

    **Days are not summed; the last day's rows are.** The view is granular by country and by
    game, so the last day is many rows and the level is their total. What must never be added
    is one day to the next.

    A row with no usable day REFUSES rather than answering ``None``: it carried a number, and
    reporting a measured figure as an absence is `T822` said backwards. Which day is last is a
    question this reader cannot answer, and guessing it is guessing the number — the sentence
    :func:`aggregation_class_of` already carries one level up.
    """
    stated: list[str] = []
    for row in rows:
        day = row.get(day_column)
        if day is None or isinstance(day, bool) or not str(day).strip():
            raise ReportRefusal(
                ReportReasonCode.REPORT_KPI_NOT_DERIVABLE,
                f"a {SNAPSHOT} row carries no usable {day_column!r}; which day is last cannot "
                f"be answered, and a level reported on an unknown day is a number nobody can "
                f"tell is wrong",
            )
        stated.append(str(day).strip())
    latest = max(stated)
    return [row for row, day in zip(rows, stated, strict=True) if day == latest]


def aggregate(
    rows: Sequence[ViewRow], column: str, *, day_column: str = EVENT_DATE_COLUMN
) -> Decimal | None:
    """This KPI's number over ``rows``, or ``None`` when there is genuinely none.

    **The whole point is the difference between the two.** ``None`` is *nothing carried a
    number*; ``Decimal(0)`` is *the numbers carried summed to zero*, and only the first is
    an absence.

    A ratio whose denominator is zero or absent answers ``None`` — a rate over nothing is
    undefined, which is not the same as a rate of zero over something.

    **The two halves of a rate are taken in PAIRS**, and :func:`_paired` records the measured
    defect that made the pairing necessary.

    **A SNAPSHOT is the last day these rows cover, never their sum** — `SC-1306`, `T1330`. A
    level does not add up: seven days of `MAU` summed counts the same people seven times, and
    the source's own documentation measured that shape (*"somar dias no grain mes infla ~30x"*).
    The class was recognised here and then treated exactly like a count until 2026-09-05; the
    daily never showed it because every caller sliced one day before calling, and the weekly of
    `T1331` is the first caller that hands a week. The SQL half of this repository has read the
    last covered day since it was written, and this is the two readers agreeing.
    """
    if not rows:
        return None
    stated = aggregation_class_of(rows)
    if stated == RATIO:
        numerators, denominators = _paired(rows)
        if not numerators or not denominators:
            return None
        below = sum(denominators, Decimal(0))
        if below == 0:
            return None
        return sum(numerators, Decimal(0)) / below
    if stated == SNAPSHOT:
        rows = _the_last_day_in(rows, day_column)
    values = _numbers(rows, column)
    if not values:
        return None
    return sum(values, Decimal(0))


def partition_by(
    rows: Sequence[ViewRow], column: str, excluded: Sequence[str] = ()
) -> tuple[tuple[str, tuple[ViewRow, ...]], ...]:
    """Split ``rows`` by the value each one carries at ``column``.

    Rows whose value is missing or is not text are **dropped, not bucketed under a name this
    module invented** — an "(unknown)" bucket would be a word nobody decided, sitting in a
    report that refuses authored words by design.

    ``excluded`` names values that are NOT values of the axis — measured markers such as an
    aggregate sitting in the same column as its parts. They are dropped at the partition, not
    at the cut, because a partition that exists is a partition the conservation check counts:
    excluding one line later would leave the total including a number no line shows.

    The order is the order of first appearance, so this function decides nothing about
    ranking. What comes out is the same rows, grouped; which of them a person reads is the
    cut's business (`FR-1303`) and not this one's.

    ## A SNAPSHOT refuses HERE, and the first version of `T1330` put this guard one door away

    `aggregate_by` carried it, and `aggregate_by` has **no caller outside its own tests**. The
    breakdown and the contribution reach their parts through *this* function and then call
    `aggregate` per group — so the arithmetic the guard forbids was reachable while the guard
    read as satisfied. Found by adversarial review of `1756d11`, not by a mutation.

    **Why a level has no parts.** The figure is the last day the WHOLE set covers. A part whose
    last row is older would be reported on another part's day, and the tail would silently drop
    every part that stopped earlier — so the kept lines and the tail stop reconciling with the
    KPI's own number, which is the property `SC-1302` exists to hold. The query side declares
    the same limit by serving no axis for this class.

    Asked as *does ANY row say so*, rather than through :func:`aggregation_class_of`: that
    function refuses rows carrying two classes, and this one is handed whatever a caller
    partitions. A refusal about breakdowns must not become a refusal about mixed input.
    """
    if any(str(row.get(AGGREGATION_CLASS_COLUMN, "")).strip() == SNAPSHOT for row in rows):
        raise ReportRefusal(
            ReportReasonCode.REPORT_KPI_NOT_DERIVABLE,
            f"a {SNAPSHOT} has no breakdown: its figure is the last day the WHOLE set covers, "
            f"and a part whose last row is older would silently be reported on another part's "
            f"day — the same limit the query side declares by serving no axis for this class",
        )
    refused = set(excluded)
    buckets: dict[str, list[ViewRow]] = {}
    for row in rows:
        value = row.get(column)
        if not isinstance(value, str) or not value.strip() or value in refused:
            continue
        buckets.setdefault(value, []).append(row)
    return tuple((value, tuple(group)) for value, group in buckets.items())


def partition_by_pair(
    rows: Sequence[ViewRow],
    first: str,
    second: str,
    excluded_first: Sequence[str] = (),
    excluded_second: Sequence[str] = (),
) -> tuple[tuple[tuple[str, str], tuple[ViewRow, ...]], ...]:
    """Split ``rows`` by the PAIR of values each one carries at ``first`` and ``second``.

    A função separada de :func:`partition_by`, e a separação é a decisão. **Cinco sítios de
    produção e cinco nós dependem de partir por UMA coluna**; alargar aquela assinatura para
    aceitar uma coluna ou um par deixaria os cinco a poder receber algo que nenhum deles pediu, e
    o nó que fixa a assinatura deixaria de proteger o que protege. É o defeito da `--format-check`
    ao contrário: uma porta que passa a responder a duas perguntas deixa de responder bem a uma.

    ## O par cai se QUALQUER lado cair, e isso é medido

    Uma linha sem valor em qualquer das duas colunas não entra — a mesma regra de
    :func:`partition_by`, aplicada duas vezes. **Medido em 2026-09-07, seis dias e quatro KPIs,
    5.520 linhas: zero nulos em `country`, zero em `game`, zero em qualquer dos dois.** Nenhuma
    linha cai hoje; o dia em que caírem, a soma das células deixa de fechar contra o total, e é
    o nó da reconciliação que tem de o DIZER em vez de o esconder.

    ## O que se exclui é qualquer par que TOQUE o marcador

    ``excluded_first`` e ``excluded_second`` nomeiam o que a fonte escreve naquela coluna sem
    ser uma parte do eixo — o marcador de agregado sentado ao lado das próprias partes. **Um par
    é recusado se qualquer dos seus componentes for um desses**, e não apenas o par inteiro: o
    marcador é o AGREGADO daquele eixo, logo qualquer célula que o contenha soma o agregado
    junto com as partes e conta duas vezes. Medido: o ficheiro governado declara um desses
    marcadores só para `game`.

    **Nenhuma palavra dele é citada nesta docstring**, e não é timidez: o nó
    `test_the_words_are_written_in_no_python_file_of_this_package` acendeu na primeira escrita
    porque eu tinha usado, em prosa, uma que o ficheiro governado carrega. Um exemplo dentro do
    pacote é uma cópia que envelhece sozinha.

    A ordem é a da primeira aparição, como em :func:`partition_by`: esta função não decide
    ranking nenhum.
    """
    if any(str(row.get(AGGREGATION_CLASS_COLUMN, "")).strip() == SNAPSHOT for row in rows):
        raise ReportRefusal(
            ReportReasonCode.REPORT_KPI_NOT_DERIVABLE,
            f"a {SNAPSHOT} has no breakdown, and an intersection of two axes is a breakdown "
            f"twice over: the same limit that {partition_by.__name__} declares",
        )
    refused_first = set(excluded_first)
    refused_second = set(excluded_second)
    buckets: dict[tuple[str, str], list[ViewRow]] = {}
    for row in rows:
        left = row.get(first)
        right = row.get(second)
        if not isinstance(left, str) or not left.strip() or left in refused_first:
            continue
        if not isinstance(right, str) or not right.strip() or right in refused_second:
            continue
        buckets.setdefault((left, right), []).append(row)
    return tuple((pair, tuple(group)) for pair, group in buckets.items())


def aggregate_by(
    rows: Sequence[ViewRow], column: str, dimension: str, excluded: Sequence[str] = ()
) -> tuple[tuple[str, Decimal], ...]:
    """This KPI's number per value of ``dimension``, using :func:`aggregate` UNCHANGED.

    **The reuse is the correctness argument, not a convenience.** `aggregate` computes a rate
    as ``SUM(numerator) / SUM(denominator)`` over the rows it is given, so calling it once per
    partition yields each partition's own rate over its own rows. Computing a mean of the
    parts' rates would be a different number — and a wrong one on every real day, because the
    denominators differ.

    A partition whose number is genuinely absent is omitted rather than reported as zero: the
    distinction `aggregate` exists to keep is not thrown away one level up.
    """
    #: The `SNAPSHOT` refusal is NOT repeated here: it lives in :func:`partition_by`, which is
    #: the door every real breakdown goes through and this one goes through too. Two copies of
    #: one rule is two rules waiting to disagree.
    answered: list[tuple[str, Decimal]] = []
    for value, group in partition_by(rows, dimension, excluded):
        number = aggregate(group, column)
        if number is not None:
            answered.append((value, number))
    return tuple(answered)


def sample_size(rows: Sequence[ViewRow]) -> Decimal | None:
    """How many cases a RATE was measured over, or ``None`` when the question does not apply.

    For a ratio it is the sum of the denominators — the number `SC-1301`'s floor is about. For
    anything else there is no denominator and the floor does not apply: a count of five is a
    count of five, and refusing to state it would be refusing the measurement itself.
    """
    if not rows or aggregation_class_of(rows) != RATIO:
        return None
    #: PAIRED, like the rate itself. A denominator whose row carries no numerator is not a case
    #: this rate was measured over, so counting it would set the floor against a sample larger
    #: than the one the number came from — the floor would then pass a rate it exists to stop.
    _numerators, denominators = _paired(rows)
    if not denominators:
        return None
    return sum(denominators, Decimal(0))
