"""Rate before count — `SC-1303`, `FR-1320`, `T1333`.

> *"Desvio de contagem só vira alerta se a **taxa** também saiu da banda; volume subindo com
> taxa estável é crescimento, e crescimento não alarma."*
> — his rule 3, `docs/exemplos-analise-dimensional.md` linha 348.

## Why this is a separate pass and not a condition inside `evaluate`

:func:`daily_reporting.alert.rule.evaluate` answers about ONE KPI, from that KPI's own history
and nothing else, and that is deliberate: a threshold that could see a second series would be a
threshold nobody could re-derive. `SC-1303` is the opposite kind of question — it is about the
RELATION between two KPIs — so it runs AFTER every KPI has been judged, over the whole set of
crossings, where both answers already exist.

That ordering is also what makes *"the rate did not leave the band"* a measurable statement
rather than an assumption: the rate's own band was computed by the same `evaluate`, on the same
run, from the same 90 days.

## A count is a count because the VIEW says so

The three words `COUNT`, `RATIO` and `SNAPSHOT` come from
`daily_reporting.view.reading` — the source's own `aggregation_class` column. Nothing here
matches a KPI name, and nothing here reads a per-cent sign out of a label: a rule that
recognised *"(qty)"* or *"(%)"* would be this repository authoring a taxonomy the warehouse
already publishes.

## `SNAPSHOT` is a LEVEL, and `SC-1303` does not reach it — decided here, in writing

`MAU`, `MRR (US$)` and `Paid subscribers` are `SNAPSHOT` (`report_governance/snapshot_mark.yaml`,
`SC-1306`): the size of the base on the last day the rows cover, never a sum of the period.

`SC-1303`'s argument is a sentence about a numerator and its denominator — *volume up with a
stable rate is growth* only means something when the count is events accumulated over the
period and some rate divides them by a base that grew alongside. **A level accumulates
nothing.** `MAU` rising is not "more of something happened"; it is the base itself being
larger, which is the very denominator the rate would have divided by. Withholding it because
some rate stayed inside its band would suppress a real movement on the strength of a comparison
that does not exist.

So a `SNAPSHOT` passes through this pass untouched, and the movement of `MAU +0,27 %` observed
on 2026-09-06 stays an alert on its own terms. If he wants a level governed by a rate too, that
is a pairing he declares like any other — see `report_governance/rate_before_count.yaml`.

## What happens when the governing rate was NOT MEASURED — and it is one or the other

A count whose rate is undeclared, or declared but never actually judged this run (too short a
series, no movement to compare, a refusal caught upstream), is in a third state that is neither
*the rate crossed* nor *the rate stayed*.

**It is KEPT in the alert and NAMED in** :attr:`RateBeforeCount.unresolved`. Both halves are the
decision:

* it does not silently alarm, because it comes back in a list whose whole purpose is to say
  *the rule could not be applied to this one*;
* it does not silently vanish, because the alternative — withholding on an absence — hands a
  broken rate series the power to silence every count in the product. `SC-1303` exists to
  remove FALSE alerts, and there is nothing false about a count whose rate nobody measured.

The reader-facing half of that naming is `T1334`'s (*what was discarded*), and `T1336`'s
auditable silence reads the same two lists. This module decides; it renders nothing.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from ..view.reading import COUNT

__all__ = [
    "RateBeforeCount",
    "RateBeforeCountGovernanceError",
    "apply_rate_before_count",
    "governing_rates_from_document",
]


class RateBeforeCountGovernanceError(ValueError):
    """The governed pairing cannot be trusted. Never silently replaced by a default."""


def governing_rates_from_document(document: object) -> dict[str, str]:
    """His declared ``{count: rate}`` map, out of `report_governance/rate_before_count.yaml`.

    ## Absence refuses, and an EMPTY declaration is not an absence

    The `S-41` rule the rest of the governed tree keeps: a file that fails to state something
    must not be answered for. A missing ``pairs`` key, or a ``pairs`` that is not a mapping of
    name to name, refuses here rather than resolving to *nothing is governed* — the two look
    identical downstream and mean opposite things.

    ``pairs: {}`` **is** a statement, and the one the file makes today: he has not declared a
    pairing yet. It comes back as an empty map, which sends every count to ``unresolved``.
    """
    if not isinstance(document, dict):
        raise RateBeforeCountGovernanceError(
            f"the governed pairing is {type(document).__name__} and not a mapping"
        )
    stated = cast("dict[str, object]", document)
    if "pairs" not in stated:
        raise RateBeforeCountGovernanceError(
            "the governed file states no 'pairs'; a missing declaration and an empty one are "
            "opposite answers, and silence may not stand for either"
        )
    pairs = stated["pairs"]
    #: `pairs: {}` parses to an empty dict, and `pairs:` alone parses to None. The second is
    #: the typo the first is trying not to be mistaken for, so it refuses.
    if not isinstance(pairs, dict):
        raise RateBeforeCountGovernanceError(
            f"'pairs' is {type(pairs).__name__} and not a mapping of count to rate"
        )
    declared: dict[str, str] = {}
    for count, rate in cast("dict[object, object]", pairs).items():
        if not isinstance(count, str) or not isinstance(rate, str) or not count.strip():
            raise RateBeforeCountGovernanceError(
                f"the pair {count!r} -> {rate!r} is not two KPI names; a pairing that cannot be "
                f"read is a suppression rule nobody can audit"
            )
        if not rate.strip():
            raise RateBeforeCountGovernanceError(
                f"{count!r} is paired with an empty rate; a count governed by nothing is not "
                f"the same as a count nobody declared, and this file may not blur them"
            )
        declared[count] = rate
    return declared


@dataclass(frozen=True, slots=True)
class RateBeforeCount:
    """What the alert carries after `SC-1303`, and what it left behind, by name.

    ``unresolved`` is a SUBSET of ``alerted``: those KPIs go out, and they go out marked.
    ``withheld`` is disjoint from ``alerted`` — those are the growth cases, the ones this
    criterion exists to stop.
    """

    alerted: tuple[str, ...]
    withheld: tuple[str, ...]
    unresolved: tuple[str, ...]


def apply_rate_before_count(
    crossed: Sequence[str],
    *,
    classes: Mapping[str, str],
    governing_rate: Mapping[str, str],
    bands_measured: Collection[str],
) -> RateBeforeCount:
    """Which of the KPIs that crossed may still alarm — `SC-1303`.

    ``crossed`` is the run's own list, in the run's own order, and the order survives: the
    alert's block is built from it.

    ``classes`` maps a KPI to the word the view stated in ``aggregation_class``. A KPI absent
    from it has no stated class, and **not knowing whether something is a count is not the same
    as knowing it is not one** — it comes back ``unresolved`` rather than waved through.

    ``governing_rate`` maps a COUNT to the RATE that governs it. It is governed data, his to
    declare; nothing is derived from a name. An empty map means no count is governed yet, and
    every count comes back ``unresolved``.

    ``bands_measured`` is every KPI whose band was actually computed on this run — crossed or
    not. It is what separates *the rate stayed inside* from *nobody looked*.
    """
    alerted: list[str] = []
    withheld: list[str] = []
    unresolved: list[str] = []
    also_crossed = set(crossed)

    for kpi in crossed:
        stated = classes.get(kpi, "").strip()
        if stated and stated != COUNT:
            #: A RATIO is the thing this rule defers to, and a SNAPSHOT is a level the rule
            #: does not reach. Both pass, and neither is marked: their answer is not missing.
            alerted.append(kpi)
            continue

        rate = governing_rate.get(kpi)
        if not stated or rate is None or rate not in bands_measured:
            alerted.append(kpi)
            unresolved.append(kpi)
            continue

        if rate in also_crossed:
            alerted.append(kpi)
        else:
            #: The rate was measured and stayed inside its own 90-day band while the count left
            #: its. That is volume, and volume is growth.
            withheld.append(kpi)

    return RateBeforeCount(
        alerted=tuple(alerted),
        withheld=tuple(withheld),
        unresolved=tuple(unresolved),
    )
