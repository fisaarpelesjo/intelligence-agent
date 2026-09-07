"""The report's shape — and **the only authored words in this package** — `T809`.

## Two strings, both his, and a correction to the specification

`FR-804` first said **one**: the footnote for short or empty source data. Writing the
header revealed a second — the word the form opens with, next to the date, because the
daily report speaks of **yesterday** and `OD-15-C` put that word in the form he
selected.

**Both came from the form he chose, and neither is this repository's wording.** The
requirement is corrected to name two rather than leaving the code quietly contradict
it; a specification saying *one* over a module holding *two* is the mismatch this loop
exists to catch, and it is cheaper to correct the sentence than to hide the word.

**A string this repository authored is a violation** — the permitted set is
``AUTHORED_WORDS`` below, and ``tests/contract/test_only_his_words_are_authored_here.py``
walks the syntax tree of this package and compares against that set rather than against a
number written in a test. It has stood at one, two, three, seven, eight and now twelve, and
**every move was a decision of his with a date beside it**; the node never needed editing
for any of them, which is the property that makes it a guard.

## What is NOT here

**No KPI name and no section header.** Those are derived from the view — `FR-803` — and
there are not twenty labels waiting on his word, there are none.

**No sentence.** Every line is a label and a value. Where there is no prose, there is no
sentence claiming more than was measured, which is the property that decided `OD-15-A`.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "ALERT_DESCRIPTION",
    "ALERT_TITLE",
    "AUTHORED_WORDS",
    "CLOSED_DAY_WORD",
    "DAY_COUNT_WORD",
    "IN_BRL_WORD",
    "MOVED_BADLY",
    "MOVED_WELL",
    "OVER_PERIOD_WORD",
    "PREVIOUS_DAY_WORD",
    "REPORT_DESCRIPTION",
    "REPORT_TITLE",
    "SHORT_OR_EMPTY_SOURCE",
    "THRESHOLD_LABEL",
    "UNMOVED",
    "VARIATION_WORD",
]

#: The word the report opens with, beside the date. `OD-15-C`.
#:
#: **Capital since 2026-08-30, by `OD-32`** — his words: *"aqui o ontem e anteontem nao pode ter
#: inicial alto?"*. Changing the CASE of a string he authored is not a new string: it is the same
#: word of his, written the way he asked for it, and the authored set still holds two.
CLOSED_DAY_WORD: Final = "Ontem"

#: The footnote marking a KPI whose source series is short or empty. `OD-15-B`. If the
#: wording is not his, one word of his removes it.
SHORT_OR_EMPTY_SOURCE: Final = "dado curto ou vazio na fonte"

#: Both of them, as a set, so the node that counts authored strings compares against
#: something derived from this module rather than against a number it was told.
#: The word beside the day being compared against. `OD-32`, and his own words on reading the
#: first daily report: *"aqui o ontem e anteontem nao pode ter inicial alto?"*.
#:
#: **This is the THIRD authored string, and `FR-804` moved to three because he asked for it.**
#: The requirement had already moved once, from one to two, the day the header was written —
#: and the practice it set is the one followed here: **the requirement moves WITH the
#: decision rather than being quietly contradicted by the code.** What is forbidden is this
#: repository authoring a word; this word is his, said twice, in his own message.
#:
#: The alternative was leaving the second day as a bare date, and that is what the report did
#: until he read it — `OD-33-C` is what that cost: the header carried two naked dates in one
#: order and the line carried two numbers in the other, and **nothing in the text undid the
#: inversion**. The word is what makes the order legible.
PREVIOUS_DAY_WORD: Final = "Anteontem"

#: The three marks a movement can carry, and **not one of them has a letter in it**.
#:
#: `OD-34`: green when the movement goes the good way, red when it goes the bad way, yellow
#: when it is exactly zero, and **nothing at all when there is no comparison** — an absence
#: already prints its dash, and colouring an absence would say more than was measured.
#:
#: **Which way is good is NOT this repository's opinion**: the metric's contract declares
#: `lower_is_better` and the direction is read from it — the view carried it until `D-1303`
#: on 2026-09-04. A table of which KPIs are good going up would be the hand-written
#: enumeration `S-4` was about.
MOVED_WELL: Final = "\N{LARGE GREEN CIRCLE}"
MOVED_BADLY: Final = "\N{LARGE RED CIRCLE}"
UNMOVED: Final = "\N{LARGE YELLOW CIRCLE}"

#: What each product says it IS, and what it covers — `OD-49`, chosen by him between two
#: wordings for each.
#:
#: ## The defect these close, on the SECOND attempt
#:
#: The report and the alert arrived **visually identical** — same header, same sections, same
#: line shape — and he asked twice which one was the alert. `OD-43` answered by putting the
#: crossed threshold on the alert's lines, and **that answer was not enough**: two bare
#: numbers at the end of a line do not say *this is an alert*, they look like a column left
#: over. He proved it by asking a second time.
#:
#: A sentence of his naming the product is worth more than two numbers trying to explain
#: themselves, and it fixes the bare `0,40 · 90` at the same time — the line above now says
#: those are a threshold from the KPI's own series.
#:
#: He refused the shorter pair, whose alert description did not say *a threshold of what*, and
#: refused putting the business's name in a title.
REPORT_TITLE: Final = "Relatório diário"
#: **It said "Os vinte indicadores" until 2026-08-31**, and by then nineteen were active:
#: `OD-40` declared `CAC (R$)` inactive AFTER he chose the sentence. He refused swapping
#: twenty for nineteen and refused leaving twenty — **a sentence that states a count goes
#: stale the next time the set moves**.
#:
#: **"Os indicadores ativos" went the same way on 2026-09-05, by `OD-131`**, and for the same
#: reason one layer up: `T1329` (`OD-107`, `FR-1319`) made the 08:00 daily carry the three
#: indicators of `report_governance/daily_scope.yaml`, three of nineteen active, so a definite
#: plural naming THE active indicators claimed more than the message delivers. What is left is
#: the half that stayed true: the two days being compared, in his own words.
#:
#: **This is a SUBTRACTION, not a new string.** Every word of it was already his — `Ontem` and
#: `Anteontem` are `CLOSED_DAY_WORD` and `PREVIOUS_DAY_WORD` (`OD-32`), `contra` stood in the
#: sentence he approved — so the budget below does not move and no vocabulary grew. The
#: precedent is `OD-32`: writing a word of his the way he asked is not authoring a word.
#: **NOT RENDERED SINCE `OD-146`/`OD-145` (2026-09-06), AND THAT IS A REVERSAL OF `OD-131`,
#: WHICH WAS HIS OWN DECISION OF THE DAY BEFORE.** His words on reading the real 08:00 message:
#: *"ai esse ontem contra anteontem, arranca essa frase fora"*.
#:
#: **The reason is duplication, not wrongness.** The line immediately under it already prints
#: `Ontem 05/09/2026 · Anteontem 04/09/2026` — the sentence said in WORDS exactly what the line
#: below says in DATES, and two lines saying one thing is one line of information.
#:
#: **The string stays in the ledger on purpose.** Deleting it would erase the record that these
#: were his words and that he chose them twice (`OD-49`, then `OD-131`), and the next person to
#: want a description would author one from scratch instead of restoring his. The RENDERING is
#: what `OD-145` removed; `render` takes a title and nothing else.
#:
#: **Reintroduction condition**: the day the header stops printing the two dates — a weekly, a
#: range, a product whose period is not one closed day against the one before — the sentence
#: stops being a duplicate and becomes the only thing that says what is being compared. Whoever
#: puts it back then is fulfilling this reasoning, not undoing the order.
REPORT_DESCRIPTION: Final = "Ontem contra anteontem"
ALERT_TITLE: Final = "Alerta"
#: **NOT RENDERED SINCE `OD-149` (2026-09-06)**, his words: *"arranca fora o texto Indicadores
#: que passaram do limiar da própria série"*.
#:
#: **A DIFFERENT argument from `OD-145`'s**, and conflating them would lose both. The daily's
#: description was deleted for saying twice what the line below it says once. This one says
#: something no other line said — and it was deleted anyway, because `OD-151` moved the same
#: fact onto the lines that carry it: every indicator in the alert now prints
#: `{THRESHOLD_LABEL}: 0,40 % em 90 d` under its own numbers. A subtitle announcing a property
#: that each item then states about itself is a header repeating its own contents.
#:
#: Kept in the ledger for the reason `REPORT_DESCRIPTION` is: the record of his wording, and
#: `THRESHOLD_LABEL` below is built from three of its own words rather than from new ones.
ALERT_DESCRIPTION: Final = "Indicadores que passaram do limiar da própria série"

#: **The word that names the movement on its own line** — `OD-147`, 2026-09-06.
#:
#: The line he read was `🟢 New trials: 736 · 695 · +5,90 % · +12,54 % vs D-7 (654)`: four
#: numbers separated by one character, and **not one of them said what it was**. He chose a
#: labelled shape from a preview built with his own numbers, and this is the one word in it
#: that was not already his: `Ontem` and `Anteontem` are `CLOSED_DAY_WORD` and
#: `PREVIOUS_DAY_WORD`, `vs D-7` is governed data (`report_governance/references.yaml`).
#:
#: **The unit stays where the arithmetic puts it** — `pp` where the movement is percentage
#: points and `%` where it is per cent — and this word names neither. It names the row.
VARIATION_WORD: Final = "Variação"

#: **The heading of the BRL block** — `OD-150`, 2026-09-06.
#:
#: `MRR` reached him as nine numbers on one line in two currencies. He refused both shortcuts:
#: putting BRL back on one line (which loses the `D-7` comparison in reais) and dropping BRL
#: from the alert — *"apaga um número que hoje está lá"*, which is losing information rather
#: than losing lines. So the second currency opens its own block, and a block needs a name.
#:
#: `OD-71` is why there are two currencies at all: *"Tem que ter MRR e Revenue em reais
#: brasileiros tambem, pq trabalhamos tanto em dolar quanto em reais"* — **his own words carry
#: `em reais`**, and this is that phrase written at the head of a line, which `OD-32` already
#: settled is the same word and not a new one.
IN_BRL_WORD: Final = "Em reais"

#: **The label of the threshold line** — `OD-151`, 2026-09-06.
#:
#: **His reasoning, and it is why this is a line and not a footnote**: the threshold is the
#: REASON the indicator is in the alert at all. It was `(0,40 % · 90 d)` trailing the numbers,
#: which reads as a column somebody forgot to remove — the exact complaint `OD-43` and `OD-49`
#: were already answering. First-class information gets a line and a word.
#:
#: **Every word of it stood in `ALERT_DESCRIPTION`** — *limiar*, *da*, *série* — so no
#: vocabulary grew; what changed is where the sentence is said. That is the `OD-131`
#: precedent used in the other direction: a subtraction spends no budget, and a
#: recomposition of words already his spends none either.
THRESHOLD_LABEL: Final = "Limiar da série"

#: **The word between the threshold and the length of the series it came from** — `OD-151`.
#: `Limiar da série: 0,40 % em 90 d`. The `90` already wears his `d` (`DAY_COUNT_WORD`); this
#: is the preposition that binds the two, and it is his, from the shape he chose. It also
#: already stands inside `IN_BRL_WORD`, which is why the delivered text carried it before this
#: constant existed.
OVER_PERIOD_WORD: Final = "em"

#: **The word for the `90`** — his, chosen 2026-08-31 among three options with one recommended
#: (the others: *"90 dias"* whole, and leaving the count bare). The alert's anchor closes as
#: `(3,57 pp · 90 d)`.
#:
#: `T838` had anchored the threshold with the movement's own unit and **stopped exactly here**:
#: naming the `90` needed a word in no permitted vocabulary, and `FR-804`'s budget is his to
#: spend. He spent it. The stop-point comment in the renderer — written for this moment — now
#: records the choice instead of the wait.
DAY_COUNT_WORD: Final = "d"

#: **TWELVE since 2026-09-06**, and the count lives here rather than in a node: the node compares
#: what the package emits against this set, so a THIRTEENTH string fails without anybody choosing
#: a new number. The marks above are not in it because they carry no word.
#:
#: It has moved five times — one to two when the header was written, two to three when he asked
#: for *Anteontem*, three to seven with the two product headings, seven to eight when he chose
#: `d` for the alert's day count, and eight to twelve when he read the real 08:00 messages and
#: rebuilt both line shapes (`OD-147`, `OD-150`, `OD-151`). **Every move was his decision,
#: written with its reason and its date**, and what the requirement forbids has never changed:
#: this repository authoring a word.
#:
#: **Two members are no longer rendered and stay counted** — `REPORT_DESCRIPTION` and
#: `ALERT_DESCRIPTION`, by `OD-145` and `OD-149`. This set is what the package HOLDS, which is
#: what the requirement is about; the comment beside each says why the string outlived its line
#: and what would bring it back. A ledger that forgot them would let the next person author his
#: sentences again from scratch.
AUTHORED_WORDS: Final[frozenset[str]] = frozenset(
    {
        CLOSED_DAY_WORD,
        PREVIOUS_DAY_WORD,
        SHORT_OR_EMPTY_SOURCE,
        REPORT_TITLE,
        REPORT_DESCRIPTION,
        ALERT_TITLE,
        ALERT_DESCRIPTION,
        DAY_COUNT_WORD,
        VARIATION_WORD,
        IN_BRL_WORD,
        THRESHOLD_LABEL,
        OVER_PERIOD_WORD,
    }
)
