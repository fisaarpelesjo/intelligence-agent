"""`ADR 0036`'s five conditions, each individually load-bearing — `T834`, `SC-811`.

**Five mutations, one per condition removed, and each must let a message through.** A
condition that can be deleted while the answer stays *refused* is a condition the code does
not actually consult — the shape `007` proved for its three, applied here rather than
relearned.

## The refusals never merge, and that reason is `377`'s

A reader who sees one code must know which of the five stopped them, because each is
resolved by a different person doing a different thing: enabling the channel, deciding a
recipient, fixing a seam, taking a wording decision, and waiting for a series to fill. And
a **sixth** code answers what the ADR does not name at all, which is not *a condition
failed* but *this record was never about that*.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from daily_reporting.contracts.origination_codes import OriginationReasonCode
from daily_reporting.origination import conditions
from daily_reporting.origination.conditions import (
    RECIPIENT_KEY,
    Permission,
    Product,
    may_originate,
)
from daily_reporting.report.summary import Reading, Summary, render, summarise
from daily_reporting.report.template import SHORT_OR_EMPTY_SOURCE
from daily_reporting.view.shape import ViewRow

pytestmark = pytest.mark.unit

AN_INSTANT = datetime(2026, 8, 28, 3, 5, tzinfo=UTC)
A_CLOSED_DAY = date(2026, 8, 27)

ROWS: tuple[ViewRow, ...] = (
    {"section_name": "alpha", "kpi_name": "a_one"},
    {"section_name": "alpha", "kpi_name": "a_two"},
)
READINGS = {
    "a_one": Reading(
        format_type="qty",
        value=Decimal("10"),
        previous_period=Decimal("10"),
        current_period=Decimal("11"),
        series_is_short=False,
    ),
    "a_two": Reading(
        format_type="qty",
        value=Decimal("0"),
        previous_period=Decimal("1"),
        current_period=Decimal("0"),
        series_is_short=True,
    ),
}

#: The recipient reaches the code only through the declared KEY. No real id is written
#: here, and no node compares this placeholder against one.
PRESENT: Mapping[str, str] = {RECIPIENT_KEY: "a-placeholder-no-node-reads"}


def _built() -> tuple[Summary, str]:
    summary = summarise(ROWS, READINGS, day=A_CLOSED_DAY, instant=AN_INSTANT)
    return summary, render(summary)


def _ask(
    *,
    product: Product = Product.DAILY_REPORT,
    rows: Sequence[ViewRow] = ROWS,
    alerted: Sequence[str] = (),
    short: Sequence[str] = ("a_two",),
    environment: Mapping[str, str] = PRESENT,
    rendered: str | None = None,
    dimension_rows: Sequence[ViewRow] = (),
    dimension_columns: Sequence[str] = (),
    governed_words: Sequence[str] = (),
) -> Permission:
    summary, text = _built()
    return may_originate(
        product,
        summary,
        text if rendered is None else rendered,
        rows,
        alerted,
        short,
        environment=environment,
        dimension_rows=dimension_rows,
        dimension_columns=dimension_columns,
        governed_words=governed_words,
    )


def _with_channel(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    def _answer(*_args: object, **_keywords: object) -> bool:
        return enabled

    monkeypatch.setattr(conditions, "channel_is_enabled", _answer)


def test_the_real_record_says_the_channel_may_send_now() -> None:
    """**This node went red on 2026-08-28, and that was its function.**

    It asserted the opposite and was right to: no decision had opened a channel, and the
    collision between two of his own decisions was unresolved. `OD-20-A` resolved it by
    **splitting the key**: *may a message arrive* and *may a message be sent* became two
    questions, the inbound rule of 2026-08-18 stands in full, and sending opened inside
    `OD-7`'s reach.

    **RE-DERIVED, not deleted** — `FR-818`. The same reading now holds the new world and
    goes red the day the record is un-declared, which is exactly as useful as what it held
    before.
    """
    assert conditions.channel_is_enabled(), (
        "the record reports the channel as NOT permitted to send; d_24 was declared and "
        "signed under OD-18 and OD-20-A, so either the record was reverted or the "
        "derivation stopped reading it"
    )


def test_sending_opened_and_receiving_did_not() -> None:
    """**The half `OD-20-A` left closed, asserted from this feature's side too.**

    `004`'s own gate holds the inbound rule, and this is the cheap check that this feature
    never confuses the two: it may send, and nothing here may receive.
    """
    from channel_integration.compliance.readiness import may_receive_from, may_send_to

    from daily_reporting.origination.conditions import ORIGINATED_CHANNEL

    assert may_send_to(ORIGINATED_CHANNEL) is True
    assert may_receive_from(ORIGINATED_CHANNEL) is False, (
        "the channel may RECEIVE; his decision of 2026-08-18 forbids that until a governed "
        "cross-process store exists, and OD-20-A split the key rather than weakening it"
    )


def test_all_five_together_permit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The premise. A function that refused everything would satisfy all five below."""
    _with_channel(monkeypatch, enabled=True)
    permission = _ask()
    assert permission.permitted, permission.refused_for
    assert permission.refused_for is None
    assert permission.recipient is not None


def test_condition_one_a_disabled_channel_stops_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_channel(monkeypatch, enabled=False)
    permission = _ask()
    assert not permission.permitted
    assert permission.refused_for is OriginationReasonCode.ORIGINATION_CHANNEL_NOT_ENABLED


def test_condition_two_no_recipient_stops_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Derived from the KEY. An empty value is no recipient, not an empty one."""
    _with_channel(monkeypatch, enabled=True)
    for environment in ({}, {RECIPIENT_KEY: ""}, {RECIPIENT_KEY: "   "}):
        permission = _ask(environment=environment)
        assert not permission.permitted
        assert permission.refused_for is OriginationReasonCode.ORIGINATION_RECIPIENT_NOT_AUTHORIZED


def test_condition_two_the_declared_recipients_and_no_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Condition 2 as amended on 2026-08-31, in BOTH directions — and its history is load-bearing.

    ## What this node said until 2026-08-31, and why each version was right in its day

    First (2026-08-30): the key non-empty was enough, and the send died in `int()` **after** the
    condition said yes while the key named two other people. The fix made a multi-id key REFUSE —
    right, under `OD-7`'s *one recipient and no other*.

    Then the owner amended `OD-7` — *"agora para as pessoas que tem o bot"* — and `OD-58` declared
    three ids in the SEND key. `S-24`: everything moved except this condition, which kept
    validating through the singular reader — so **the first real send to three was refused right
    here**, `origination_recipient_not_authorized`, delivered to 0 of 3, per-recipient `refused`
    lines and a non-zero exit. A correct refusal by stale lights.

    The property that never changed and is still what this node drives: **the condition sees what
    it protects.** Nothing leaves toward anybody the declaration does not name.
    """
    _with_channel(monkeypatch, enabled=True)

    #: **Three declared is PERMITTED, and the permission names all three** — the S-24 direction,
    #: the one that refused the real send.
    for value in ("1,2,3", "1;2;3", " 1 , 2 , 3 "):
        permission = _ask(environment={RECIPIENT_KEY: value})
        assert permission.permitted, f"{value!r} declared three and was refused"
        assert permission.recipients == ("1", "2", "3")
        #: The singular view answers None for a list: a caller that sends to exactly one must
        #: never be handed one of three by this module picking a name.
        assert permission.recipient is None

    #: One declared still passes — regression here breaks the send that already works.
    permitted = _ask(environment={RECIPIENT_KEY: "1"})
    assert permitted.permitted, "a single declared chat was refused"
    assert permitted.recipients == ("1",)
    assert permitted.recipient == "1"

    #: An EMPTY declaration refuses: a permission naming nobody cannot be acted on, and sending
    #: to nobody must never read as authorised.
    for value in ("", "   ", ",", " ; "):
        refused = _ask(environment={RECIPIENT_KEY: value})
        assert not refused.permitted, f"{value!r} declared nobody and was permitted"
        assert refused.refused_for is OriginationReasonCode.ORIGINATION_RECIPIENT_NOT_AUTHORIZED
        assert refused.recipients == ()

    #: And the declaration is never inherited from who may TALK to the bot — the 2026-08-30
    #: defect stays closed under the amended rule.
    inherited = _ask(environment={RECIPIENT_KEY: "", "TELEGRAM_ALLOWED_CHAT_ID": "1,2,3"})
    assert not inherited.permitted, "an empty declaration fell back to the may-talk key"


def test_condition_three_a_figure_the_source_never_stated_stops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A line for a KPI the view did not supply is a number this feature invented."""
    _with_channel(monkeypatch, enabled=True)
    permission = _ask(rows=ROWS[:1])
    assert not permission.permitted
    assert permission.refused_for is OriginationReasonCode.ORIGINATION_FIGURE_NOT_FROM_THE_SOURCE


def test_condition_four_a_word_nobody_approved_stops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two vocabularies reach the reader — the source's and his — and there is no third."""
    _with_channel(monkeypatch, enabled=True)
    _summary, text = _built()
    permission = _ask(rendered=text + "\nresumo executivo do dia\n")
    assert not permission.permitted
    assert permission.refused_for is OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS


def test_condition_four_admits_the_sources_own_currency_marks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OD-71` put `67.223,40 R$` on a line, and condition 4 refused the real report.

    `US$` had been passing BY COINCIDENCE: the labels the view supplies carry `(US$)`, so the
    token `US` entered through the source's-labels vocabulary. No active KPI is labelled
    `(R$)`, so the mark's `R` entered through nothing and the first dual-currency `--dry` at
    the final HEAD printed `RECUSADO ... origination_wording_not_his` — measured 2026-08-31.

    The marks are the SOURCE's vocabulary already: `OD-42` put them in `_VALUE_UNITS`, beside
    `RATE_FORMAT` and `WHOLE_FORMATS`, derived from `format_type` and never chosen per line.
    Condition 4 admitting that same named set is the `VariationUnit` story again — the
    docstring above it records the condition refusing a correct report until the vocabulary
    it was pointing at got named. Nothing a person reads is added here that `OD-42` did not
    already govern.
    """
    _with_channel(monkeypatch, enabled=True)
    rows: tuple[ViewRow, ...] = ({"section_name": "alpha", "kpi_name": "MRR (US$)"},)
    readings = {
        "MRR (US$)": Reading(
            format_type="usd_k",
            value=Decimal("46948.23"),
            previous_period=Decimal("46860.55"),
            current_period=Decimal("46948.23"),
            series_is_short=False,
            brl_value=Decimal("67223.40"),
            brl_previous=Decimal("67230.98"),
            brl_format="brl",
        )
    }
    summary = summarise(rows, readings, day=A_CLOSED_DAY, instant=AN_INSTANT)
    text = render(summary)
    assert "R$" in text, "the dual-currency line is not in the rendering under test"
    permission = may_originate(
        Product.DAILY_REPORT, summary, text, rows, (), (), environment=PRESENT
    )
    assert permission.refused_for is not OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS, (
        "the source's own currency mark was read as a word nobody approved"
    )
    assert permission.permitted


def test_condition_five_an_alert_on_a_short_series_stops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A threshold over a series that cannot support one is noise nobody measured."""
    _with_channel(monkeypatch, enabled=True)
    permission = _ask(alerted=("a_two",))
    assert not permission.permitted
    assert permission.refused_for is OriginationReasonCode.ORIGINATION_SHORT_SERIES_WAS_ALERTED


def test_the_two_products_the_adr_names_are_the_only_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ADR 0036` names the daily report and the rule alert. The set is closed."""
    _with_channel(monkeypatch, enabled=True)
    assert {product.value for product in Product} == {"daily_report", "rule_alert"}
    for product in Product:
        assert _ask(product=product).permitted


def test_every_condition_answers_a_different_code() -> None:
    """`377`: five conditions behind one refusal is *not today* without saying why."""
    seen = {
        OriginationReasonCode.ORIGINATION_CHANNEL_NOT_ENABLED,
        OriginationReasonCode.ORIGINATION_RECIPIENT_NOT_AUTHORIZED,
        OriginationReasonCode.ORIGINATION_FIGURE_NOT_FROM_THE_SOURCE,
        OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS,
        OriginationReasonCode.ORIGINATION_SHORT_SERIES_WAS_ALERTED,
    }
    assert len(seen) == 5
    assert OriginationReasonCode.ORIGINATION_NOT_NAMED_BY_THE_ADR not in seen, (
        "the ADR's SCOPE and its CONDITIONS share a code; a reader could not tell "
        "'no record covers this' from 'a condition failed'"
    )


def test_a_permission_that_cannot_say_what_stopped_it_is_refused() -> None:
    """An unexplained no is the silence this stack exists to avoid."""
    with pytest.raises(ValueError, match="name the condition"):
        Permission(permitted=False, refused_for=None, recipients=())
    with pytest.raises(ValueError, match="permitted and refused"):
        Permission(
            permitted=True,
            refused_for=OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS,
            recipients=("x",),
        )
    with pytest.raises(ValueError, match="nobody to send to"):
        Permission(permitted=True, refused_for=None, recipients=())


def test_the_footnote_is_his_and_does_not_trip_the_wording_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise condition 4 would refuse every report that has a short series in it."""
    _with_channel(monkeypatch, enabled=True)
    _summary, text = _built()
    assert SHORT_OR_EMPTY_SOURCE in text
    assert _ask().permitted


# --- the fifth vocabulary of condition 4 — `OD-111`, F1 -----------------------
#
# A country name and a game title are in NONE of the four older vocabularies, so the first
# breakdown report would be refused here and nothing would be sent. His decision was the fifth
# vocabulary DERIVED from the supplied lines — and he attached the condition that makes it a
# fix instead of a loosening: a value that is not in those lines must still be REFUSED.
#
# Both halves are driven below, because either alone is worthless. Permitting the value that
# came from the data proves nothing if anything else is permitted too; refusing an unknown
# value proves nothing if the real one is refused as well.

_BREAKDOWN_ROWS: tuple[ViewRow, ...] = (
    {"country": "Brasil", "game": "Valorant"},
    {"country": "Mexico", "game": "Fortnite"},
)
_BREAKDOWN_COLUMNS = ("country", "game")


def test_a_value_read_from_the_supplied_lines_is_permitted() -> None:
    """The half that unblocks F1: the report may say a word the DATA said."""
    _, text = _built()
    permission = _ask(
        rendered="\n".join([text, "Brasil Valorant"]),
        dimension_rows=_BREAKDOWN_ROWS,
        dimension_columns=_BREAKDOWN_COLUMNS,
    )
    assert permission.permitted, permission.refused_for


def test_a_value_that_is_in_no_supplied_line_is_still_refused() -> None:
    """**The condition he attached to his own choice.**

    Without this the fifth vocabulary would be "accept any token", which is the option he did
    NOT choose wearing the name of the one he did.
    """
    _, text = _built()
    permission = _ask(
        rendered="\n".join([text, "Brasil Chile"]),
        dimension_rows=_BREAKDOWN_ROWS,
        dimension_columns=_BREAKDOWN_COLUMNS,
    )
    assert not permission.permitted
    assert permission.refused_for is OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS


def test_a_column_the_caller_did_not_name_contributes_nothing() -> None:
    """The rows are supplied, the column is not named, so the value is not vocabulary.

    This is what stops "pass the whole row and hope": widening happens by NAMING a column,
    which is a decision somebody makes, not a side effect of the data carrying a field.
    """
    _, text = _built()
    permission = _ask(
        rendered="\n".join([text, "Valorant"]),
        dimension_rows=_BREAKDOWN_ROWS,
        dimension_columns=("country",),
    )
    assert not permission.permitted
    assert permission.refused_for is OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS


def test_a_report_with_no_breakdown_is_judged_exactly_as_before() -> None:
    """The defaults are empty, so the report that existed before F1 is unchanged.

    Driven rather than assumed: the same rendered text, once with the fifth vocabulary
    supplied and once without, gets the same verdict.
    """
    assert _ask().permitted
    assert _ask(dimension_rows=_BREAKDOWN_ROWS, dimension_columns=_BREAKDOWN_COLUMNS).permitted


def test_this_module_names_no_dimension_and_no_value_of_one() -> None:
    """The words arrive as DATA, the way `declared_order` already does.

    A dimension named in the package is a fact the package should not hold — and it is also
    how the fifth vocabulary would quietly become a written list again.
    """
    source = Path(conditions.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1] if source.count('"""') >= 2 else source
    for value in ("Brasil", "Valorant", "Mexico", "Fortnite"):
        assert value not in body, f"{value} is written into the module"


# --- the word he approved, accent and all — `S-44` ---------------------------
#
# The render said `por pais` and the contract he approved says it WITH the accent: measured on
# the two artefacts, 8 occurrences in the example contract and 11 in his own examples, ZERO
# without. And the tail went out as `demais 72: 321`, dropping the noun that `FR-1303` and
# `SC-1304` both spell out.
#
# **The noun did not fall out by decision — it fell out because this gate would have refused
# it.** That is the wrong direction entirely: a word the gate refuses is a word to GOVERN, not
# a word to drop. Both are now data in `report_governance/breakdown.yaml`, and the nodes below
# drive the gate rather than assuming it copes.


def test_an_accented_governed_word_survives_the_tokenizer() -> None:
    """The accent is in the message he reads, so it has to survive `_words_in`.

    Driven rather than reasoned about: the folded comparison and the word split both have to
    treat the accented form as the same token the governed file supplied.
    """
    _, text = _built()
    permission = _ask(
        rendered="\n".join([text, "por país: Brasil 412"]),
        dimension_rows=_BREAKDOWN_ROWS,
        dimension_columns=_BREAKDOWN_COLUMNS,
        governed_words=("por país",),
    )
    assert permission.permitted, permission.refused_for


def test_the_unaccented_form_is_not_admitted_by_the_accented_one() -> None:
    """**Anti-vacuity for the node above.**

    If the tokenizer folded accents away, supplying the accented word would silently admit the
    unaccented one and the finding could come back without anything going red.
    """
    _, text = _built()
    permission = _ask(
        rendered="\n".join([text, "por pais: Brasil 412"]),
        dimension_rows=_BREAKDOWN_ROWS,
        dimension_columns=_BREAKDOWN_COLUMNS,
        governed_words=("por país",),
    )
    assert not permission.permitted
    assert permission.refused_for is OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS


def test_the_tail_with_its_noun_passes_when_the_noun_is_governed() -> None:
    """The shape the two artefacts approved, admitted because the word is data."""
    _, text = _built()
    permission = _ask(
        rendered="\n".join([text, "demais 72 valores: 321"]),
        dimension_rows=_BREAKDOWN_ROWS,
        dimension_columns=_BREAKDOWN_COLUMNS,
        governed_words=("demais", "valores"),
    )
    assert permission.permitted, permission.refused_for


def test_the_tail_noun_is_refused_when_it_is_not_governed() -> None:
    """**The mutation the reviewer asked for, as a node.**

    Removing the noun from the governed file must make the rendered tail REFUSE — that is what
    proves the word is admitted because it is governed, and not because the gate is loose. It
    is also exactly what happened in the finding: the gate refused, and the response was to
    drop the word instead of governing it.
    """
    _, text = _built()
    permission = _ask(
        rendered="\n".join([text, "demais 72 valores: 321"]),
        dimension_rows=_BREAKDOWN_ROWS,
        dimension_columns=_BREAKDOWN_COLUMNS,
        governed_words=("demais",),
    )
    assert not permission.permitted
    assert permission.refused_for is OriginationReasonCode.ORIGINATION_WORDING_NOT_HIS
