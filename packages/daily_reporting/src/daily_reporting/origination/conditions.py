"""The five conditions of `ADR 0036`, each checkable and each on its own — `T834`.

`FR-062` of `004` says the system MUST originate no message on its own initiative. **That
requirement is not amended.** `ADR 0035` supersedes it for the prioritisable finding and
**excludes a digest by name**; `ADR 0036` supersedes it for **two named products** — the
daily report and the rule alert — and its five conditions must all hold:

1. the channel is **already** enabled;
2. the recipient is the owner's own chat and no other;
3. every number comes from the source;
4. the wording is the closed template of `OD-15`;
5. a KPI without sufficient series appears **without** an alert.

## The order is not cosmetic

**The scope question comes before every condition**, because *this record was never about
that* and *a condition failed* are different answers, and asking about channels first would
report a configuration problem when the truth is that no record covers the act at all.

After that the cheapest and most informative refusal comes first: a channel nobody enabled
is the answer to *may anything leave at all*.

## The channel condition READS THE RECORD

It is not a parameter, and that is `007`'s `T703` inherited rather than relearned: **a
parameter is the caller telling this function what it wants to hear.** A record that cannot
be read comes back as *not enabled*, because not measuring is never passing and a crash is
not a governed refusal.

## What this module does NOT do

**It enables nothing and it sends nothing.** It answers whether sending would be permitted.
The send is `T824` and does not exist.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from channel_integration.compliance.readiness import ReadinessMalformed, may_send_to
from channel_integration.contracts.descriptor import ChannelId

from ..contracts.origination_codes import OriginationReasonCode
from ..report.summary import Summary
from ..report.template import AUTHORED_WORDS
from ..view.shape import ViewRow, kpi_label_of

__all__ = [
    "ORIGINATED_CHANNEL",
    "RECIPIENT_KEY",
    "Permission",
    "Product",
    "channel_is_enabled",
    "every_recipient_is_declared",
    "may_originate",
    "recipients_from",
]

#: The one channel `OD-7`'s reach covers. A second channel is not a configuration value
#: here — it is a decision that does not exist.
ORIGINATED_CHANNEL = ChannelId.TELEGRAM

#: The key the recipient is DERIVED from. The id itself is never written: a chat id in
#: source is a violation even when the value happens to be correct.
#:
#: ## It was `TELEGRAM_ALLOWED_CHAT_ID` until 2026-08-30, and one key cannot answer two questions
#:
#: That key says **which chats may TALK TO the bot**, and a list is correct there — the owner
#: authorised three on 2026-08-21. This condition asks the opposite direction: **where does a
#: report GO**, and `OD-7` answers *his chat and no other*. One key over two questions is how
#: condition two came to answer *yes* while the key named two other people.
#:
#: `OD-28` is his decision and it is the shape of `OD-20-A`, which split *may receive* from *may
#: send* for the same reason: **one key, one question.**
RECIPIENT_KEY = "TELEGRAM_REPORT_CHAT_ID"


class Product(StrEnum):
    """The two things `ADR 0036` names, and nothing else is covered by it."""

    DAILY_REPORT = "daily_report"
    RULE_ALERT = "rule_alert"


@dataclass(frozen=True, slots=True)
class Permission:
    """Whether the built thing may leave, and — when not — exactly what stopped it.

    The two fields cannot disagree: permitted while naming a refusal, or refused while
    naming none, is refused at construction. **An unexplained no is the silence this stack
    exists to avoid.**
    """

    permitted: bool
    refused_for: OriginationReasonCode | None
    #: The declared list, whole. It was a singular ``recipient`` until 2026-08-31 — see `S-24`
    #: at `_the_declared_recipients` — and the singular shape is what refused the first real
    #: send to three.
    recipients: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.permitted and self.refused_for is not None:
            raise ValueError(f"permitted and refused at once: {self.refused_for}")
        if not self.permitted and self.refused_for is None:
            raise ValueError(
                "a refusal must name the condition that failed; an unexplained no is the "
                "silence this feature exists to avoid"
            )
        if self.permitted and not self.recipients:
            raise ValueError("permitted with nobody to send to, which cannot be acted on")

    @property
    def recipient(self) -> str | None:
        """The single recipient, for a caller that still sends to exactly one.

        ``None`` whenever the declaration is not exactly one — the same refusal
        `_recipient_from` carries, kept at the edge instead of inside condition 2.
        """
        return self.recipients[0] if len(self.recipients) == 1 else None


def channel_is_enabled(channel: ChannelId = ORIGINATED_CHANNEL) -> bool:
    """Whether ``channel`` is enabled, **read from `004`'s readiness records**.

    It takes no override. A record that cannot be read is **not enabled**, deliberately:
    absent evidence and negative evidence are different facts and neither is permission.
    """
    try:
        return may_send_to(channel)
    except ReadinessMalformed:
        return False


#: What separates chat ids when the key names more than one. The harness's own reader
#: accepts a comma-separated list, because the key answers a DIFFERENT question there:
#: which chats may TALK TO the bot. `OD-7` is about the other direction.
_RECIPIENT_SEPARATORS = (",", ";", " ")


def recipients_from(environment: Mapping[str, str]) -> tuple[str, ...]:
    """**Every** recipient declared for sending, in order and without duplicates. Never written.

    ## `OD-7` was amended on 2026-08-31, and the amendment is narrow

    His words: *"agora para as pessoas que tem o bot, pode tacar le pau"*. `OD-7` went from **one
    recipient and no other** to **the DECLARED recipients and no other**. What moved is how many he
    named; what did not move is that **a chat outside the declaration receives nothing**.

    ## And the list is DECLARED FOR SENDING, never inherited

    Measured 2026-08-31: `TELEGRAM_ALLOWED_CHAT_ID` holds **three** ids and this key holds **one**,
    and the one is the first of the three. **That overlap is a coincidence, not a definition.** The
    other key answers *which chats may TALK TO the bot*; this one answers *where a report GOES*.
    Reading the first as the second is exactly the defect of 2026-08-30 — see below — and it stays
    forbidden however convenient today's overlap looks.

    An empty declaration returns **nothing**, and the caller must read that as a refusal rather than
    as an empty loop that reports success. **Sending to nobody satisfies every check phrased as
    "each recipient was authorised".**
    """
    found = environment.get(RECIPIENT_KEY, "").strip()
    if not found:
        return ()
    ordered: list[str] = []
    for part in re.split(r"[,;\s]+", found):
        piece = part.strip()
        if piece and piece not in ordered:
            ordered.append(piece)
    return tuple(ordered)


def every_recipient_is_declared(sent_to: Sequence[str], environment: Mapping[str, str]) -> bool:
    """Condition 2, amended: the send reached **exactly** the declared list — `FR-1003`.

    Two halves, and the second is the one that catches the interesting failure:

    1. every chat that received something is in the declaration;
    2. **the count of sends equals the count of the declaration.**

    Without (2), a run that sent to **nobody** passes: "every recipient was declared" is vacuously
    true of an empty set. Without (1), a fourth chat rides along. Both, or neither is worth having.
    """
    declared = recipients_from(environment)
    if not declared:
        return False
    reached = list(sent_to)
    if len(reached) != len(declared):
        return False
    return set(reached) == set(declared)


def _recipient_from(environment: Mapping[str, str]) -> str | None:  # pyright: ignore[reportUnusedFunction] -- kept: the docstring is the record
    """The FIRST declared recipient, kept for callers that still send to one.

    Superseded by `recipients_from` on 2026-08-31 and left in place because the refusal it carries
    is still the right refusal for a single-recipient caller. Its docstring below is the record of
    why the refusal exists at all, and it is not deleted: erasing the reason is how the next person
    reintroduces the defect.

    ## A key naming more than one chat is REFUSED, and 2026-08-30 is why

    This returned the key's raw value, so a key holding three chat ids satisfied condition 2
    — *the recipient is the owner's own chat and no other* — while naming **two other
    people**. Measured that day: `TELEGRAM_ALLOWED_CHAT_ID` carried three ids, and the send
    died in `int()` **after** the condition had already answered yes.

    **The condition read as present and was not**, which is the shape this repository keeps
    closing. Two things were wrong and both are fixed here: a crash where a governed refusal
    belongs, and a check that could not see the thing it exists to protect.

    The same key answers a different question for the harness — *which chats may talk to the
    bot*, where a list is correct and the owner authorised more than one on 2026-08-21. It
    cannot answer both: **`OD-7` is about what LEAVES**, and there the answer is one chat or
    no send at all. Refusing is what leaves the decision with him rather than letting this
    module pick a name out of three.
    """
    declared = recipients_from(environment)
    if len(declared) != 1:
        #: **Still a refusal, and still for the 2026-08-30 reason.** A caller that sends to one
        #: cannot be handed one of three by this function picking a name; whoever needs the list
        #: asks for the list.
        return None
    return declared[0]


def _every_figure_came_from_the_source(summary: Summary, rows: Sequence[ViewRow]) -> bool:
    """Condition 3: no line carries a KPI the source never stated.

    Compared against the ROWS, not against another call on the summary: an expectation
    computed by the thing being measured agrees with it whatever it does — the `G-1` lesson
    this package already paid for once.
    """
    stated = {kpi_label_of(row) for row in rows}
    carried = {line.label for _name, lines in summary.sections for line in lines}
    return carried <= stated


#: Punctuation the report separates with. Stripped from BOTH the emitted text and the
#: supplied vocabulary, so the two are comparable: the first draft compared `a_one:` against
#: `a_one` and refused a correct report over a colon.
_SEPARATORS = ":()*,"


def _words_in(text: str) -> set[str]:
    """The tokens of ``text`` that carry a letter, with separators stripped."""
    return {
        stripped
        for token in text.split()
        for stripped in (token.strip(_SEPARATORS),)
        if any(character.isalpha() for character in stripped)
    }


def _every_word_is_his(
    rendered: str,
    rows: Sequence[ViewRow],
    dimension_rows: Sequence[ViewRow] = (),
    dimension_columns: Sequence[str] = (),
    governed_words: Sequence[str] = (),
) -> bool:
    """Condition 4: every word a person reads comes from a named vocabulary.

    **There are three, and the third was found by this condition refusing a correct
    report.** The first draft allowed two — the source's labels and his two words of
    `OD-15` — and it refused the legitimate output, because the unit beside every movement
    is neither.

    * **the source's**: the KPI and section names the view supplied;
    * **his**: the two words `AUTHORED_WORDS` holds, by `OD-15`;
    * **the governed units**: the members of :class:`VariationUnit`. **Which unit applies is
      derived** from `format_type` and never chosen per line; **the word it prints is his**,
      by `OD-20-C` — *"pontos percentuais"* for a rate and *"%"* for a volume.
    * **the source's value marks** — added 2026-08-31, and found the same way the third was:
      by this condition refusing a correct report. `OD-71` put `R$` beside the BRL pair and
      the first dual-currency `--dry` was refused right here, `origination_wording_not_his`.
      `US$` had passed BY COINCIDENCE — the view's labels carry `(US$)`, so `US` entered
      through the first vocabulary; no active label carries `(R$)`. The marks were already
      named source vocabulary before this line read them: `OD-42` holds them in
      `_VALUE_UNITS`, derived from `format_type`, never chosen per line. Nothing is admitted
      that `OD-42` does not already govern.

    **The third is named rather than waved through**, and what it was pointing at got
    decided.

    ## What this paragraph said until 2026-08-28, and why it was wrong twice over

    It said the spelling was *"a decision of his that has not been taken"* and that this
    feature *"emits the derived name rather than inventing a friendlier one"*. `OD-20-C` took
    that decision **in the same commit that made these sentences false**, which is how a
    docstring comes to claim more than the code does.

    **And the classification underneath was inverted, which is the worse half.** It called
    these members *"the machine's own vocabulary, not prose somebody wrote for the reader"* —
    and after `OD-20-C` they are exactly prose he wrote for the reader. That reading is what
    let them sit in a permitted vocabulary while spelling `relative_percent`; what makes them
    permitted now is not that they are the machine's, it is that they are **his**.

    ## The fifth, and the condition his own decision put on it (`OD-111`, 2026-09-03)

    `F1` puts a country name and a game title in the report, and neither is in any of the four
    above — so the first breakdown run would be refused right here and **nothing would be
    sent**. That is the gate working, and the fix he chose is not to author those words: the
    fifth vocabulary's members are **the dimension values READ FROM THE SAME LINES that
    produced the numbers**.

    **And he attached a condition to his own choice, which is the half that makes it a fix
    rather than a loosening**: a vocabulary that accepted arbitrary text would be option (c)
    under another name. So the members come from `row[column]` of the SUPPLIED lines, for
    columns the caller names — never from the rendered text, never from a list written here.
    **A value that is not in those lines is still refused**, and a node drives exactly that.

    Two properties hold by construction and are asserted rather than trusted: this module
    names no dimension and no value of one (the caller passes both, the same way
    `declared_order` already arrives as data), and a row that carries a column the caller did
    not name contributes nothing.

    Numbers, punctuation and separators carry no letter and are not words.
    """
    from ..numbers.variation import VALUE_UNIT_MARKS, VariationUnit
    from ..view.shape import SECTION_NAME_COLUMN

    supplied: set[str] = set()
    #: The fourth vocabulary, `OD-42`'s value marks — see the docstring for how it earned
    #: its place. The set iterated is the governed one, not a copy of its words.
    for mark in VALUE_UNIT_MARKS.values():
        supplied.update(_words_in(mark))
    for phrase in AUTHORED_WORDS:
        supplied.update(_words_in(phrase))
    #: **Split into WORDS, like everything else in this set** — and it did not, until the
    #: report grew past one KPI on 2026-08-30. `supplied` held *"pontos percentuais"* as a
    #: single token while the check below reads a line word by word, so `pontos` and
    #: `percentuais` were never in the vocabulary. **Every report containing a rate KPI would
    #: have been refused**, and the one-KPI report never exercised it because its only unit
    #: was `%`, a single token that happened to match.
    #:
    #: This is not the vocabulary being widened: it is the same rule the line is read by,
    #: applied to the same words. What is permitted is still exactly his and the source's.
    for unit in VariationUnit:
        supplied.update(_words_in(unit.value))
    for row in rows:
        supplied.update(_words_in(kpi_label_of(row)))
        section = row.get(SECTION_NAME_COLUMN)
        if isinstance(section, str):
            supplied.update(_words_in(section))
    #: The fifth vocabulary — see the docstring, and `OD-111` for why it is derived rather
    #: than authored. Only the columns the caller NAMED are read, and only from the lines the
    #: caller SUPPLIED: a value that appears in neither is not in this set and the report
    #: carrying it is refused, which is the condition he attached to his own choice.
    for row in dimension_rows:
        for column in dimension_columns:
            value = row.get(column)
            if isinstance(value, str):
                supplied.update(_words_in(value))
    #: The SIXTH: words he wrote, arriving as governed DATA rather than as a literal here.
    #: `por pais`, `por jogo` and `demais` are in the example contract he approved, word for
    #: word, and they reach the report through `report_governance/breakdown.yaml` the way the
    #: section order already does. This is deliberately NOT a widening of `AUTHORED_WORDS`:
    #: that budget counts words the PACKAGE holds, and the node asserting its size stays where
    #: it is. A word here is his because a governed file he signs says it, and changing one is
    #: an edit to that file with no code touched.
    for phrase in governed_words:
        supplied.update(_words_in(phrase))
    #: **Compared without case**, because `OD-32` already decided that changing the case of a
    #: word of his does not make it a different word: *"aqui o ontem e anteontem nao pode ter
    #: inicial alto?"*. The header carries `Anteontem` and the line carries `anteontem`, and
    #: they are one word said twice. **This admits no word that was not already permitted** —
    #: only spellings of the same ones.
    folded = {token.casefold() for token in supplied}
    return all(
        token.casefold() in folded for line in rendered.splitlines() for token in _words_in(line)
    )


def may_originate(
    product: Product,
    summary: Summary,
    rendered: str,
    rows: Sequence[ViewRow],
    alerted: Sequence[str],
    short_series: Sequence[str],
    *,
    environment: Mapping[str, str],
    dimension_rows: Sequence[ViewRow] = (),
    dimension_columns: Sequence[str] = (),
    governed_words: Sequence[str] = (),
) -> Permission:
    """Answer `ADR 0036`'s five conditions, in the order the docstring gives.

    ``product`` is a parameter because the caller knows which of the two it built.
    ``environment`` is a parameter because a module reading `os.environ` is a module that
    cannot be handed a different world. **The channel is neither**: the record answers it.

    ``dimension_rows`` and ``dimension_columns`` are the fifth vocabulary of condition 4
    (`OD-111`), and they default to empty so a caller that emits no breakdown is unchanged —
    the report that existed before `F1` is refused or permitted by exactly the same rules it
    was. Both are parameters for the reason `declared_order` is: naming a dimension here would
    make this module hold a fact that belongs to the caller's data.
    """
    if product not in tuple(Product):  # pragma: no cover - StrEnum makes this unreachable
        return Permission(
            permitted=False,
            refused_for=OriginationReasonCode.ORIGINATION_NOT_NAMED_BY_THE_ADR,
            recipients=(),
        )
    if not channel_is_enabled():
        return Permission(
            permitted=False,
            refused_for=OriginationReasonCode.ORIGINATION_CHANNEL_NOT_ENABLED,
            recipients=(),
        )
    #: **Condition 2, as amended on 2026-08-31 — `S-24` is why this line reads the LIST.**
    #:
    #: `OD-58` reached the caller, the journal and `recipients_from`, and this condition
    #: stayed on the old rule: it validated through `_recipient_from`, the SINGULAR reader,
    #: which answers `None` the moment the key carries separators. The key now carries three
    #: ids by his order — so the first real send to three was refused right here,
    #: `origination_recipient_not_authorized`, delivered to 0 of 3. The system refused
    #: correctly by its own lights and recorded it per recipient; the lights were stale.
    #:
    #: The amended rule, and nothing looser: the send goes to **the declared recipients and
    #: no other**. An empty declaration refuses — a permission naming nobody cannot be acted
    #: on, and sending to nobody must never read as authorised.
    _the_declared_recipients = recipients_from(environment)
    if not _the_declared_recipients:
        return Permission(
            permitted=False,
            refused_for=OriginationReasonCode.ORIGINATION_RECIPIENT_NOT_AUTHORIZED,
            recipients=(),
        )
    if not _every_figure_came_from_the_source(summary, rows):
        return Permission(
            permitted=False,
            refused_for=OriginationReasonCode.ORIGINATION_FIGURE_NOT_FROM_THE_SOURCE,
            recipients=(),
        )
    if not _every_word_is_his(rendered, rows, dimension_rows, dimension_columns, governed_words):
        return Permission(
            permitted=False,
            refused_for=OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS,
            recipients=(),
        )
    if set(alerted) & set(short_series):
        return Permission(
            permitted=False,
            refused_for=OriginationReasonCode.ORIGINATION_SHORT_SERIES_WAS_ALERTED,
            recipients=(),
        )
    return Permission(permitted=True, refused_for=None, recipients=_the_declared_recipients)
