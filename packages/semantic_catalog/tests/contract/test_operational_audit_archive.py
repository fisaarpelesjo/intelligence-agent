"""O sink operacional do D-13, dirigido pelo caminho PÚBLICO — T110 (OD-103, ciclo 537).

O produtor é o `check` do CLI — o mesmo comando que um steward digita — apontado para um
arquivo temporário. Os nós afirmam as duas metades da evidência exigida: o sink ACEITA o
`CatalogDecisionAuditEvent` (ALLOW e DENY igualmente, com os dois fusos e as duas chaves
consultáveis no primeiro nível), e a consulta devolve o evento re-validado pelo contrato —
com os drills em cópia: linha adulterada falha NOMEANDO a posição; arquivo ausente é
resposta vazia; um filtro que não casa devolve nada em vez de tudo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from semantic_catalog.cli.main import main
from semantic_catalog.provenance.file_archive import (
    ArchiveLineCorrupt,
    FileAuditArchive,
    find_events,
)

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
PRODUCTION = REPO / "semantic"
ON = "2026-09-02"


def _check(tmp_path: Path, *, correlation: str, principal: str = "steward-drill") -> int:
    return main(
        [
            "check",
            "mrr",
            "--from",
            "2026-08-01",
            "--to",
            "2026-08-20",
            "--path",
            str(PRODUCTION),
            "--on",
            ON,
            "--principal",
            principal,
            "--correlation-id",
            correlation,
            "--audit-path",
            str(tmp_path / "operational-audit.jsonl"),
        ]
    )


def test_the_public_check_emits_one_queryable_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Uma decisão do steward = um evento no arquivo, ALLOW ou DENY igualmente."""
    _check(tmp_path, correlation="corr-drill-1")
    capsys.readouterr()
    archive = tmp_path / "operational-audit.jsonl"
    assert archive.is_file(), "o check nao emitiu nada"
    lines = archive.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1

    record = json.loads(lines[0])
    # O "indice": as duas chaves consultaveis no PRIMEIRO nivel, mais os dois fusos.
    assert record["correlation_id"] == "corr-drill-1"
    assert record["principal_id"] == "steward-drill"
    assert "at_utc" in record and "at_local" in record
    assert isinstance(record["event"], dict)

    found = find_events(archive, correlation_id="corr-drill-1")
    assert len(found) == 1
    event = found[0]
    assert event.principal_id == "steward-drill"
    assert event.metric_ids == ("mrr",)


def test_two_runs_append_and_each_filter_finds_its_own(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _check(tmp_path, correlation="corr-a", principal="steward-a")
    _check(tmp_path, correlation="corr-b", principal="steward-b")
    capsys.readouterr()
    archive = tmp_path / "operational-audit.jsonl"
    assert len(archive.read_text(encoding="utf-8").strip().split("\n")) == 2
    assert len(find_events(archive, correlation_id="corr-a")) == 1
    assert len(find_events(archive, principal_id="steward-b")) == 1
    assert find_events(archive, correlation_id="corr-que-nao-existe") == ()


def test_a_missing_archive_answers_empty_rather_than_raising(tmp_path: Path) -> None:
    assert find_events(tmp_path / "nunca-escrito.jsonl", correlation_id="x") == ()


def test_a_tampered_line_fails_naming_its_position(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Drill em cópia: a linha 2 vira lixo; a consulta falha dizendo LINHA 2 — nunca
    devolve um arquivo meio-lido como se fosse a resposta."""
    _check(tmp_path, correlation="corr-t1")
    _check(tmp_path, correlation="corr-t2")
    capsys.readouterr()
    archive = tmp_path / "operational-audit.jsonl"
    lines = archive.read_text(encoding="utf-8").strip().split("\n")
    lines[1] = '{"correlation_id": "corr-t2", "event": {"adulterado": true}}'
    copia = tmp_path / "copia.jsonl"
    copia.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ArchiveLineCorrupt) as caught:
        find_events(copia, correlation_id="corr-t2")
    assert caught.value.line_number == 2

    lixo = tmp_path / "lixo.jsonl"
    lixo.write_text("isto nao e json\n", encoding="utf-8")
    with pytest.raises(ArchiveLineCorrupt):
        find_events(lixo)


def test_no_user_value_beyond_the_contract_reaches_a_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """O sink acrescenta SÓ os carimbos: toda chave da linha é uma das cinco nomeadas, e
    o evento é byte a byte o dump do contrato (que já recusa valor/pergunta/credencial)."""
    _check(tmp_path, correlation="corr-shape")
    capsys.readouterr()
    archive = tmp_path / "operational-audit.jsonl"
    record = json.loads(archive.read_text(encoding="utf-8").strip())
    assert set(record.keys()) == {
        "correlation_id",
        "principal_id",
        "at_utc",
        "at_local",
        "event",
    }
    reparsed = find_events(archive, correlation_id="corr-shape")[0]
    assert reparsed.model_dump(mode="json") == record["event"]


def test_the_append_choice_is_the_written_one() -> None:
    """ESCOLHA ESCRITA (single-process append, sem lock): o sink usa open-append com uma
    escrita por evento, e nenhum lock aparece — o dia em que um segundo produtor
    simultâneo nascer, este nó falha apontando para a linha que muda."""
    source = (
        REPO
        / "packages"
        / "semantic_catalog"
        / "src"
        / "semantic_catalog"
        / "provenance"
        / "file_archive.py"
    ).read_text(encoding="utf-8")
    assert 'with self._path.open("a", encoding="utf-8") as handle:' in source
    assert "flock" not in source and "msvcrt" not in source and "lockf" not in source
    assert source.count(".open(") == 1, "um segundo ponto de escrita/abertura apareceu"


def test_the_default_archive_is_the_house_runs_convention() -> None:
    assert FileAuditArchive().path == Path("runs") / "operational-audit.jsonl"
