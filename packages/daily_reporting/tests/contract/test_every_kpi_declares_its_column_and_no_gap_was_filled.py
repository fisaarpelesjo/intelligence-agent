"""Every KPI of the real view declares its column, and no gap was filled — `T829`.

## The two halves of `T829`, and only one of them is mechanical

`FR-806` says the column carrying a KPI's number is **declared in that metric's contract**
and read from there, never inferred and above all **never defaulted to `value`** — that
default is what published MRR and Revenue as valueless. `daily_reporting` has refused at
read time since `T811`; what was missing was the catalog half, and on 2026-08-30 the owner
signed the draft — *"FACA TUDO / EU PERMITO"* — and the nineteen entered `semantic/metrics/`.

**The signature authorised the contracts to exist. It did not authorise filling the gaps.**
`D-28` is not a permission rule, it is a truth rule: no order makes true what nobody
measured. So each of the nineteen carries its derived half written and its business half as
a **named gap, copied verbatim from the draft he signed** — and this file is what stops that
arrangement from quietly becoming something else.

## Why the sweep is derived and not listed

A contract is in scope when its `source_view` is a view the warehouse actually holds. The
four that do not exist are already named, with their reason, in
`test_nothing_is_signed_and_nothing_is_written.py`, and that name is **imported rather than
retyped**: a second list is a list that lies the day one of them changes. A metric pointing
at an absent view has no observable column, and declaring one for it would be the invention
this guard exists to prevent.

## What this does NOT catch, declared rather than left to be found

It cannot tell whether the pt-BR in a gap is *true* — no node reads meaning. It checks that
the gap is still **the owner's own words**, that the derived half stays free of business
vocabulary, and that the column is declared. A gap rewritten into a different sentence that
happens to avoid the vocabulary below would pass the vocabulary check — but not the verbatim
check, which is byte-level against the signed draft.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
METRICS = REPO / "semantic" / "metrics"
DRAFT = REPO / "docs" / "rascunho-definicoes-dezenove-kpis.md"

#: The view the warehouse holds. Every other `source_view` this catalog names is one of the
#: four that do not exist, and those are named — with their reason — in the security suite.
THE_VIEW = "semantic.subscription_daily_metrics"

#: The first catalog schema version in which the column may be declared, read from the
#: module that refuses at read time rather than written again here.
from daily_reporting.numbers.column import (  # noqa: E402  - after the constants it documents
    SCHEMA_VERSION_DECLARING_THE_COLUMN,
    VALUE_COLUMN_FIELD,
    value_column_for,
)
from daily_reporting.report.scope import (  # noqa: E402  - same reason as above
    active_kpis,
    day_is_loaded,
    declares_inactive,
    shape_rows,
)

#: Business vocabulary: words that name what a number MEANS. None of them is derivable from
#: `aggregation_class`, `format_type` or a column, so any of them inside the derived half is
#: meaning that came from the label — `S-8`, in the document this catalog was built from.
BUSINESS_VOCABULARY = (
    "receita",
    "custo",
    "assinante",
    "cliente",
    "venda",
    "usuário",
    "usuario",
    "cancelamento",
    "contestação",
    "contestacao",
    "aquisição",
    "aquisicao",
    "vida",
    "fim de ciclo",
    "reconhecid",
)


def _contracts() -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(METRICS.glob("*.yaml")):
        payload: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            typed = cast("dict[str, Any]", payload)
            if typed.get("kind") == "metric":
                found.append((path, typed))
    return found


def bound_to_the_view(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """The version blocks of ``contract`` that point at the view the warehouse holds."""
    versions = contract.get("versions")
    if not isinstance(versions, list):
        return []
    found: list[dict[str, Any]] = []
    for version in cast("list[object]", versions):
        if isinstance(version, dict):
            typed = cast("dict[str, Any]", version)
            if typed.get("source_view") == THE_VIEW:
                found.append(typed)
    return found


def gaps_in_the_signed_draft() -> list[str]:
    """Every `A DEFINIR POR ELE` line of the draft the owner signed, normalised.

    Read from the draft itself. **The draft is the signed artefact**, so a contract quoting
    it is quoting him; a contract quoting something else is quoting somebody else.
    """
    text = DRAFT.read_text(encoding="utf-8")
    found: list[str] = []
    for match in re.finditer(
        r"^\* \*\*A DEFINIR POR ELE\*\*: (.+?)(?=\n\* |\n\n|\Z)", text, re.S | re.M
    ):
        found.append(" ".join(match.group(1).split()))
    return found


def quotes_a_signed_gap(limitations: list[str], gaps: list[str]) -> bool:
    """Does any limitation carry one of the owner's gap sentences, verbatim?"""
    joined = [" ".join(str(item).split()) for item in limitations]
    return any(gap in line for gap in gaps for line in joined)


def business_words_in(text: str) -> list[str]:
    """Which business words appear in ``text``. The derived half must carry none."""
    lowered = text.lower()
    return [word for word in BUSINESS_VOCABULARY if word in lowered]


def test_the_sweep_reaches_the_contracts_and_the_draft() -> None:
    """A sweep over nothing forbids nothing — the `F115` shape, before the sweeps are used."""
    contracts = _contracts()
    assert len(contracts) >= 20, f"the sweep found {len(contracts)} metric contracts"

    bound = [path.name for path, payload in contracts if bound_to_the_view(payload)]
    assert len(bound) == 20, (
        f"{len(bound)} contracts point at {THE_VIEW}; the view holds twenty KPIs and the "
        f"catalog should name each once: {sorted(bound)}"
    )

    gaps = gaps_in_the_signed_draft()
    assert len(gaps) >= 12, f"the draft yielded {len(gaps)} gap sentences"


def test_every_contract_bound_to_the_view_declares_its_column() -> None:
    """`FR-806`, the catalog half. Declared per metric, never inferred, never defaulted."""
    offending: list[str] = []
    for path, payload in _contracts():
        for version in bound_to_the_view(payload):
            schema = payload.get("catalog_schema_version")
            #: **`<`, not `!=` — and the difference was invisible until a schema bump.**
            #:
            #: This read `!=` while its own message said *"readable from 2 onwards"* and the
            #: production reader (`numbers/column.py`) said `<`. The two agreed by accident for
            #: as long as 2 was the newest version, and `D-1303` bumping the catalogue to 3 on
            #: 2026-09-04 turned every correct contract into an offender: twenty metrics that
            #: DO declare their column were reported as unable to say where their number lives.
            #:
            #: The node was wrong, not the contracts. A version window written as equality is a
            #: window that closes the first time anything moves.
            if not isinstance(schema, int) or schema < SCHEMA_VERSION_DECLARING_THE_COLUMN:
                offending.append(
                    f"{path.name}: catalog_schema_version {schema}, and the field is readable "
                    f"from {SCHEMA_VERSION_DECLARING_THE_COLUMN} onwards (FR-808)"
                )
                continue
            if not version.get(VALUE_COLUMN_FIELD):
                offending.append(
                    f"{path.name}: version {version.get('version')} declares no "
                    f"{VALUE_COLUMN_FIELD}"
                )
            if not version.get("kpi_name"):
                offending.append(
                    f"{path.name}: version {version.get('version')} declares no kpi_name, so "
                    "nothing says which row of the view it is"
                )
    assert not offending, (
        "these point at the view the warehouse holds and cannot say where their number "
        "lives; it is NOT defaulted to 'value', because that default is what published MRR "
        "and Revenue as valueless:\n" + "\n".join(offending)
    )


def test_the_production_reader_agrees_with_every_declaration() -> None:
    """And the declaration is read by the code that refuses, not only by this node."""
    for path, payload in _contracts():
        for version in bound_to_the_view(payload):
            column = value_column_for(payload, version=version)
            assert column in {"value", "value_usd", "value_brl"}, f"{path.name}: {column}"


def cites_a_dated_decision(limitations: list[str]) -> bool:
    """Emendado no ciclo 523 (2026-09-02, OD-100): uma lacuna sai de cena SOMENTE virando
    decisao DATADA e assinada por ordem — a citacao carrega o OD e a data juntos."""
    marcadores = ("DEFINICAO DECIDIDA (OD-", "ANOTADA SEM RESPOSTA (OD-")
    return any(m in limitation for limitation in limitations for m in marcadores)


def test_no_gap_was_filled_and_every_one_is_his_own_words() -> None:
    """`D-28`, and it is the half his signature did not move — ate a palavra ESPECIFICA.

    Emendado no ciclo 523 (2026-09-02, OD-100): o dono respondeu as perguntas uma a uma,
    por clique, e as lacunas viraram DEFINICOES DECIDIDAS datadas nos contratos. A regra
    que fica e a mesma com a saida nova: cada contrato preso a view ou CITA a lacuna
    verbatim do rascunho assinado, ou carrega a decisao DATADA que a fechou (OD + data na
    mesma frase) — uma limitacao que nao e nenhum dos dois e uma lacuna que alguem
    preencheu sem ordem, e falha. `new_trials` segue a excecao original (definicao por
    verificacao, sem lacuna desde o inicio).
    """
    gaps = gaps_in_the_signed_draft()
    offending: list[str] = []

    for path, payload in _contracts():
        for version in bound_to_the_view(payload):
            content = cast("dict[str, Any]", version.get("content") or {})
            limitations = cast("list[str]", list(content.get("limitations") or ()))

            if (
                payload.get("name") != "new_trials"
                and not quotes_a_signed_gap(limitations, gaps)
                and not cites_a_dated_decision(limitations)
            ):
                offending.append(
                    f"{path.name}: no limitation quotes a gap from the signed draft NOR cites "
                    "a dated owner decision; a gap rewritten is a gap somebody filled"
                )

            words = business_words_in(str(version.get("calculation_basis", "")))
            if words and payload.get("name") != "new_trials":
                offending.append(
                    f"{path.name}: calculation_basis carries {words}, which names what the "
                    "number MEANS and is not derivable from the class or the columns"
                )

    assert not offending, "\n".join(offending)


def test_both_guards_bite() -> None:
    """**Read this before believing the three nodes above** — the two mutations `T829` names.

    Driven over in-memory contracts, so the repository is not made to carry the thing the
    guard exists to prevent even for one measurement.
    """
    gaps = gaps_in_the_signed_draft()
    real = gaps[0]

    #: A contract that declares no column.
    sem_coluna = {
        "kind": "metric",
        "name": "decorativo",
        "catalog_schema_version": SCHEMA_VERSION_DECLARING_THE_COLUMN,
        "versions": [{"version": 1, "source_view": THE_VIEW, "kpi_name": "MAU"}],
    }
    version = bound_to_the_view(sem_coluna)[0]
    assert version.get(VALUE_COLUMN_FIELD) is None
    with pytest.raises(Exception, match="declares no"):
        value_column_for(sem_coluna, version=version)

    #: A contract at the old schema version carrying the field anyway — `FR-808`.
    velho = {**sem_coluna, "catalog_schema_version": 1}
    velho["versions"] = [{**version, VALUE_COLUMN_FIELD: "value"}]
    with pytest.raises(Exception, match="predates"):
        value_column_for(velho, version=velho["versions"][0])

    #: A gap replaced by an invented definition.
    assert quotes_a_signed_gap([f"LACUNA NOMEADA, copiada verbatim: {real}"], gaps)
    assert not quotes_a_signed_gap(
        ["Cancelamentos sao assinaturas encerradas a pedido do usuario no dia."], gaps
    ), "an invented definition passed as a quoted gap"

    #: And the derived half carrying business vocabulary.
    assert business_words_in("Contagem de cancelamentos de assinantes no periodo.")
    assert not business_words_in(
        "A view declara a classe COUNT e o formato int, e o numero vive na coluna value."
    )


def test_a_kpi_leaves_the_report_only_by_a_declaration_with_a_reason() -> None:
    """`OD-40`, and `FR-805` was amended with it: every **ACTIVE** KPI, not every KPI.

    His words were *"cac esta desativado, entao vamos tirar da lista"*, and the measurement
    is recorded beside the decision: `CAC (R$)` is **not** switched off at the source — it
    has a denominator and **never** a numerator, so the ratio is not computable and the line
    carried a dash.

    **The omission is derived from a DECLARATION in the catalog and never from a name in
    code.** Dropping a KPI by name would be the enumeration this repository closed five times
    over, and it would leave without a reason or a date.
    """
    contracts = {payload.get("name"): payload for _path, payload in _contracts()}
    cac = contracts.get("cac_brl")
    assert cac is not None, "the CAC contract vanished; this node measures nothing"
    assert declares_inactive(cac), "CAC is not declared inactive, so nothing removes it"

    #: The model itself refuses an unavailable source with no reason, so a KPI cannot leave
    #: the report silently. Asserted rather than trusted.
    entry = next(
        cast("dict[str, Any]", item)
        for item in cast("list[object]", cac["source_availability"])
        if isinstance(item, dict) and cast("dict[str, Any]", item).get("status") == "unavailable"
    )
    assert entry.get("reason_code"), entry
    assert entry.get("effective_from"), entry


def test_the_declaration_is_what_removes_it_in_both_directions() -> None:
    """**Proof it bites both ways** — `OD-40` asked for exactly this pair.

    Declaring an appearing KPI inactive must remove it; and an active KPI must stay, so the
    rule cannot quietly empty the report.
    """
    active: dict[str, Any] = {"name": "x", "source_availability": []}
    assert not declares_inactive(active)

    #: The mutation: the same contract, one declaration later.
    inactive = {
        "name": "x",
        "source_availability": [
            {"source": "s", "status": "unavailable", "reason_code": "r", "effective_from": "d"}
        ],
    }
    assert declares_inactive(inactive)

    #: And an AVAILABLE declaration does not remove anything -- otherwise every metric that
    #: declares its window would vanish from the report.
    still_active = {
        "name": "x",
        "source_availability": [
            {"source": "s", "status": "available", "available_from": "d", "effective_from": "d"}
        ],
    }
    assert not declares_inactive(still_active)


def test_the_active_set_is_read_from_the_contracts_and_not_from_the_rows() -> None:
    """**The defect was never in the rendering — it was in who CHOOSES the lines.**

    ## What the node this replaces actually measured

    `OD-54` moved the count out of the description and into a node, and that node landed one
    layer away: it handed the renderer a list of KPIs and asserted the renderer gave those
    KPIs back. **It compared a list with itself.** The reviewer drove the proof: reintroducing
    the original defect — deriving the active set from the closed day's rows — left every
    suite green.

    So the choice moved into the package, and this drives it where it lives. `Chargeback
    (qty)` lags two days and `Not renewed (qty)` one, so neither has a row on the closed day.
    **A set read from those rows loses them; a set read from the contracts does not.**
    """
    contracts = [payload for _path, payload in _contracts()]
    wanted = active_kpis(contracts, view=THE_VIEW)
    assert wanted, "no KPI is active; this node would forbid nothing"

    #: The rows of ONE day, with two active KPIs missing from it — the real situation.
    lagging = sorted(wanted)[:2]
    closed_day_rows = [
        {"kpi_name": kpi, "section_name": "s"} for kpi in sorted(wanted) if kpi not in lagging
    ]

    #: **Read from the contracts**: every active KPI is there, including the two the day lost.
    shape = shape_rows(contracts, closed_day_rows, view=THE_VIEW)
    assert {row["kpi_name"] for row in shape} == set(wanted)
    for kpi in lagging:
        assert any(row["kpi_name"] == kpi for row in shape), kpi

    #: **The mutation, driven here**: the same choice made from the rows instead. It loses
    #: exactly the KPIs the day did not carry, which is what shipped as seventeen of twenty.
    from_the_rows = {str(row["kpi_name"]) for row in closed_day_rows}
    assert from_the_rows != set(wanted), "the mutation did not actually change the set"
    assert len(from_the_rows) == len(wanted) - len(lagging)


def test_a_declaration_is_the_only_thing_that_takes_a_kpi_out_of_the_set() -> None:
    """`OD-40`, driven over the real contracts and over a mutation of them."""
    contracts = [payload for _path, payload in _contracts()]
    wanted = active_kpis(contracts, view=THE_VIEW)

    inactive = [payload.get("name") for payload in contracts if declares_inactive(payload)]
    assert inactive, "no contract declares itself inactive; the mechanism is untested"
    for name in inactive:
        assert name not in wanted.values(), name

    #: Declare an ACTIVE one inactive and it leaves; nothing else moves.
    #: **Among the ones actually in the set** — the catalog also holds metrics bound to no
    #: view, and dropping one of those would change nothing and prove nothing.
    victim = next(
        payload
        for payload in contracts
        if not declares_inactive(payload) and payload.get("name") in set(wanted.values())
    )
    mutated = [
        {
            **payload,
            "source_availability": [
                {"source": "s", "status": "unavailable", "reason_code": "r", "effective_from": "d"}
            ],
        }
        if payload is victim
        else payload
        for payload in contracts
    ]
    after = active_kpis(mutated, view=THE_VIEW)
    assert len(after) == len(wanted) - 1, (len(after), len(wanted))


def test_the_day_must_be_loaded_before_anything_is_composed() -> None:
    """`T837`'s hour, asserted in both directions.

    Measured 2026-08-31 at 05:00 UTC: the source rebuilds at 06:00 and every one of the
    nineteen lines carried a dash. **Nineteen absences dressed as a daily report** teach the
    reader only that something is broken, and the refusal names the day instead.

    **Deleting the refusal used to leave everything green** — the reviewer proved it by
    replacing the condition with `if False`.
    """
    from datetime import date

    day = date(2026, 8, 30)
    loaded = [{"event_date": day, "kpi_name": "k"}]
    not_loaded = [{"event_date": date(2026, 8, 29), "kpi_name": "k"}]

    assert day_is_loaded(loaded, day), "a loaded day was refused"
    assert not day_is_loaded(not_loaded, day), "an unloaded day was accepted"
    assert not day_is_loaded([], day), "no rows at all read as loaded"

    #: And the dates arrive as strings from the warehouse client just as often.
    assert day_is_loaded([{"event_date": "2026-08-30"}], day)
