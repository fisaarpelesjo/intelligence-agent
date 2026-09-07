"""A leitura REAL das duas tabelas do D-12, pelo caminho do PRÓPRIO pacote — ciclo 539.

Condições 2 e 3 do T109 (a 1 foi medida satisfeita: as tabelas existem, governadas e
populadas). Este módulo é o caminho de leitura que faltava: até aqui, todo acesso real ao
armazém provava-se pelo executor do bot (a identidade do d_15, que é de OUTRA feature) ou
por SQL avulso em teste. Aqui o `semantic_catalog` lê as SUAS duas tabelas com a
identidade dedicada e devolve os SEUS contratos — e a credencial chega INJETADA (um
caminho de arquivo em argumento), porque o nó de escopo do d_15 afirma que NENHUM pacote
conhece o NOME da variável de ambiente: quem a lê é o chamador (o teste, o steward na
linha de comando), nunca este src.

## O mapeamento declarado (condição 2)

O produtor (business-intelligence) publica colunas; este pacote declara contratos. O
casamento é DECLARADO aqui, coluna a coluna, e um nó compara as duas pontas contra o
`INFORMATION_SCHEMA` VIVO: coluna viva fora do mapa, ou mapa citando coluna que não
existe, falham nomeando qual. Medido em 2026-09-03:

  - `source_freshness`: source_id→source, status→status, last_loaded_at→
    last_successful_update, ingestion_started_at/ingestion_finished_at→idem;
    `data_revision_id` é do produtor e alimenta a linhagem de revisão (não é campo do
    `FreshnessRecord`; viaja para quem rastreia revisão) — declarado como CONSUMIDO.
  - `metric_availability`: metric_id→metric, source_id→source, covered_from→min_date,
    covered_to→max_date; `available` (BOOL) decide se a linha VIRA cobertura — uma linha
    available=false é ausência declarada, não cobertura.

`observed_at` não é coluna: é o instante DESTA leitura, como o contrato pede.

**Só SELECT.** Nada aqui escreve, e o caminho do arquivo de credencial nunca é impresso.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, cast

from ..validation.l3_reconciliation import ObservedCoverageSet
from .external import CompletenessStatus, FreshnessRecord, ObservedCoverage

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "LIVE_AVAILABILITY_COLUMNS",
    "LIVE_FRESHNESS_COLUMNS",
    "METRIC_AVAILABILITY_TABLE",
    "SOURCE_FRESHNESS_TABLE",
    "WarehouseUnreachable",
    "client_from_credentials",
    "read_freshness_records",
    "read_observed_coverage",
]

SOURCE_FRESHNESS_TABLE = "example-project-id.semantic.source_freshness"
METRIC_AVAILABILITY_TABLE = "example-project-id.semantic.metric_availability"

#: Coluna viva → destino no contrato (ou o consumo declarado). O nó da condição 2 compara
#: ESTAS chaves com o INFORMATION_SCHEMA vivo, nas duas direções.
LIVE_FRESHNESS_COLUMNS: dict[str, str] = {
    "source_id": "FreshnessRecord.source",
    "status": "FreshnessRecord.status",
    "last_loaded_at": "FreshnessRecord.last_successful_update",
    "ingestion_started_at": "FreshnessRecord.ingestion_started_at",
    "ingestion_finished_at": "FreshnessRecord.ingestion_finished_at",
    "data_revision_id": "consumed-by-revision-lineage (producer-supplied revision id)",
}
LIVE_AVAILABILITY_COLUMNS: dict[str, str] = {
    "metric_id": "ObservedCoverage.metric",
    "source_id": "ObservedCoverage.source",
    "covered_from": "ObservedCoverage.min_date",
    "covered_to": "ObservedCoverage.max_date",
    "available": "row-admission (false = declared absence, never coverage)",
}


class WarehouseUnreachable(RuntimeError):  # noqa: N818 - a named refusal, not a defect
    """Sem credencial ENTREGUE não há leitura — dito sem citar variável nem caminho."""

    def __init__(self) -> None:
        super().__init__(
            "no credential file was handed to the dedicated read identity, so nothing was measured"
        )


class _QueryClient(Protocol):
    def query(self, sql: str) -> Any: ...


def client_from_credentials(credentials_file: str) -> _QueryClient:
    """O client da identidade dedicada, nascido do arquivo ENTREGUE — nunca ambiente ADC.

    O provedor é importado AQUI, não no topo: um ambiente sem a biblioteca continua
    importando este módulo e recebe a recusa nomeada só quando pede a leitura. O caminho
    recebido não é impresso e não fica guardado além do client.
    """
    configured = credentials_file.strip()
    if not configured:
        raise WarehouseUnreachable
    from google.cloud import (
        bigquery,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType] - stub parcial do provedor, mesmo caso do client em run
    )

    return cast(
        "_QueryClient",
        bigquery.Client.from_service_account_json(configured),  # pyright: ignore[reportUnknownMemberType] - stub parcial
    )


def _rows(client: _QueryClient, sql: str) -> list[dict[str, Any]]:
    return [dict(cast("Mapping[str, Any]", row).items()) for row in client.query(sql).result()]


def read_observed_coverage(client: _QueryClient) -> ObservedCoverageSet:
    """`semantic.metric_availability` VIVO, como o contrato deste pacote — `is_fixture=False`.

    A única construção de `ObservedCoverageSet(is_fixture=False)` a partir do mundo: o
    loader de arquivo força fixture=True por desenho, e esta função é o caminho que um
    arquivo não pode fingir.
    """
    now = datetime.now(tz=UTC)
    rows: list[ObservedCoverage] = []
    for row in _rows(client, f"SELECT * FROM `{METRIC_AVAILABILITY_TABLE}`"):
        if not row.get("available"):
            continue
        rows.append(
            ObservedCoverage(
                metric=str(row["metric_id"]),
                source=str(row["source_id"]),
                min_date=row["covered_from"],
                max_date=row["covered_to"],
                observed_at=now,
            )
        )
    return ObservedCoverageSet(rows=tuple(rows), is_fixture=False)


def read_freshness_records(client: _QueryClient) -> tuple[FreshnessRecord, ...]:
    """`semantic.source_freshness` VIVO, uma linha por fonte, pelo contrato deste pacote."""
    now = datetime.now(tz=UTC)
    records: list[FreshnessRecord] = []
    for row in _rows(client, f"SELECT * FROM `{SOURCE_FRESHNESS_TABLE}`"):
        records.append(
            FreshnessRecord(
                source=str(row["source_id"]),
                status=CompletenessStatus(str(row["status"])),
                observed_at=now,
                ingestion_started_at=row.get("ingestion_started_at"),
                ingestion_finished_at=row.get("ingestion_finished_at"),
                last_successful_update=row.get("last_loaded_at"),
            )
        )
    return tuple(records)


def live_information_schema(client: _QueryClient) -> dict[str, Sequence[str]]:
    """As colunas vivas das duas tabelas, para o nó da condição 2 comparar com o mapa."""
    found: dict[str, Sequence[str]] = {}
    for table in ("source_freshness", "metric_availability"):
        rows = _rows(
            client,
            "SELECT column_name FROM `example-project-id.semantic.INFORMATION_SCHEMA.COLUMNS` "
            f"WHERE table_name = '{table}' ORDER BY ordinal_position",
        )
        found[table] = [str(row["column_name"]) for row in rows]
    return found
