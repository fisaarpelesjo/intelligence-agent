"""O sink operacional do D-13 — arquivo JSONL, consultável por correlação e principal.

OD-103 (clicado em 2026-09-02; executado no ciclo 537, 2026-09-03): o T110 pedia um sink
que ACEITA `CatalogDecisionAuditEvent` com `correlation_id` e `principal_id` indexados e
consultáveis. Este módulo é as duas metades: `FileAuditArchive` (o `AuditSink` real, uma
linha JSON por evento no padrão da casa — dois fusos, zero valor de usuário: o contrato do
evento já recusa valor de métrica, texto de pergunta e credencial por validador, e o sink
acrescenta SÓ os carimbos) e `find_events` (a consulta, que re-parseia cada linha pelo
CONTRATO — uma linha adulterada falha nomeando a posição, nunca volta como evento).

## ESCOLHA ESCRITA: semântica de append

`open(..., "a")` com UMA escrita por evento — a semântica O_APPEND de processo único. O
produtor deste arquivo é um processo por vez (o CLI do steward, ou o harness de conversa;
cada um escreve no `runs/` do próprio cwd), e um lock multiplataforma compraria complexidade
para um concorrente que não existe. Se um segundo produtor simultâneo nascer um dia, esta
linha é a que muda — e o nó que afirma a escolha falha, apontando para cá.

"Indexado" aqui é a forma honesta de um JSONL: `correlation_id` e `principal_id` são
chaves de PRIMEIRO nível em toda linha (afirmado por nó), então qualquer consumidor — este
`find_events`, um `jq`, um load para tabela — filtra sem parsear o evento inteiro.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..contracts.audit_event import CatalogDecisionAuditEvent

__all__ = ["DEFAULT_ARCHIVE", "ArchiveLineCorrupt", "FileAuditArchive", "find_events"]

#: O padrão da casa: `runs/` relativo ao processo — o steward escreve no `runs/` da raiz
#: do repositório, o harness de conversa no `runs/` do próprio diretório (este pacote não
#: sabe em que canal ele fala, e não precisa); os dois já são git-ignored.
DEFAULT_ARCHIVE = Path("runs") / "operational-audit.jsonl"

_LOCAL = ZoneInfo("America/Sao_Paulo")


class ArchiveLineCorrupt(RuntimeError):  # noqa: N818 - a named refusal to answer, not a defect
    """Uma linha do arquivo não re-parseia pelo contrato — dita com a POSIÇÃO, nunca
    devolvida como evento: um arquivo meio-lido que responde é um arquivo que mente."""

    def __init__(self, path: Path, line_number: int) -> None:
        self.line_number = line_number
        super().__init__(f"{path.name}: line {line_number} does not parse as an audit event")


class FileAuditArchive:
    """`AuditSink` real: um `CatalogDecisionAuditEvent` por linha, append-only."""

    def __init__(self, path: Path = DEFAULT_ARCHIVE) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def __call__(self, event: CatalogDecisionAuditEvent) -> None:
        now = datetime.now(tz=UTC)
        record: dict[str, Any] = {
            # As duas chaves consultáveis vêm PRIMEIRO e no nível de cima — o "index".
            "correlation_id": event.correlation_id,
            "principal_id": event.principal_id,
            "at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "at_local": now.astimezone(_LOCAL).strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": event.model_dump(mode="json"),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)


def find_events(
    path: Path,
    *,
    correlation_id: str | None = None,
    principal_id: str | None = None,
) -> tuple[CatalogDecisionAuditEvent, ...]:
    """Os eventos que casam com os filtros dados, RE-VALIDADOS pelo contrato.

    Arquivo ausente é resposta vazia (nada foi auditado ainda); linha corrupta é
    `ArchiveLineCorrupt` nomeando a posição. Os filtros olham as chaves de primeiro
    nível — o índice — antes de parsear o evento inteiro.
    """
    if not path.is_file():
        return ()
    found: list[CatalogDecisionAuditEvent] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError as broken:
            raise ArchiveLineCorrupt(path, number) from broken
        if not isinstance(parsed, dict):
            raise ArchiveLineCorrupt(path, number)
        record: dict[str, Any] = {str(key): value for key, value in parsed.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        if correlation_id is not None and record.get("correlation_id") != correlation_id:
            continue
        if principal_id is not None and record.get("principal_id") != principal_id:
            continue
        try:
            found.append(CatalogDecisionAuditEvent.model_validate(record.get("event")))
        except Exception as broken:
            raise ArchiveLineCorrupt(path, number) from broken
    return tuple(found)
