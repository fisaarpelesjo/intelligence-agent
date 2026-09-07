"""A assinatura de frescor cobre o commit ATUAL da fonte — OD-99 (ciclo 519), S-34 (521).

O achado do ciclo 517: o bump v2 tocou `semantic/sources/subscription_daily.yaml` e a
aprovação seguiu presa em `7c5e577` — COMMIT_MISMATCH em todo lugar que a avalia, com o
cabeçalho sem saber. Este nó lê a aprovação REAL, a fonte REAL e o commit REAL (o mesmo
comando que o CLI usa) e avalia pelo CAMINHO PÚBLICO — `FreshnessApprovalRegistry.evaluate`
— exatamente como o portão de publicação avalia (S-34: a primeira versão importava o
`_covers` privado e o strict types do pacote recusou; o público é mais forte, porque mede
a avaliação inteira). A cópia com o commit velho ACENDE.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from semantic_catalog.contracts.freshness_approval import (
    FreshnessApprovalRegistry,
    FreshnessDenial,
)
from semantic_catalog.contracts.source import Source

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
APPROVALS = REPO / "semantic" / "governance" / "freshness-approvals.yaml"
SOURCE_PATH = "semantic/sources/subscription_daily.yaml"


def _registry() -> FreshnessApprovalRegistry:
    loaded: object = yaml.safe_load(APPROVALS.read_text(encoding="utf-8"))
    return FreshnessApprovalRegistry.model_validate(loaded)


def _source() -> Source:
    loaded: object = yaml.safe_load((REPO / SOURCE_PATH).read_text(encoding="utf-8"))
    return Source.model_validate(loaded)


def _current_source_commit() -> str:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", SOURCE_PATH],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert len(out) == 40, "o git nao resolveu o commit da fonte"
    return out


def test_the_signature_covers_the_current_source_commit() -> None:
    """O caminho publico inteiro, contra os artefatos REAIS — divergiu, vermelho nomeado."""
    denial = _registry().evaluate(
        _source(),
        source_content_commit=_current_source_commit(),
        on=date(2026, 9, 2),
    )
    assert denial is None, (
        f"a avaliacao publica recusou com {denial}: a assinatura nao cobre mais a fonte — "
        "reassinar e ato do dono (precedente OD-99)"
    )


def test_a_stale_signature_in_a_copy_lights_up() -> None:
    """A mutação dirigida: o commit velho de 26-27/08 numa cópia = COMMIT_MISMATCH nomeado."""
    raw = cast("dict[str, Any]", yaml.safe_load(APPROVALS.read_text(encoding="utf-8")))
    entrada = cast("list[dict[str, Any]]", raw["approvals"])[0]
    entrada["source_commit"] = "7c5e577"
    copia = FreshnessApprovalRegistry.model_validate(raw)
    denial = copia.evaluate(
        _source(),
        source_content_commit=_current_source_commit(),
        on=date(2026, 9, 2),
    )
    assert denial is FreshnessDenial.COMMIT_MISMATCH, (
        f"a copia com o commit velho avaliou {denial!r} em vez de COMMIT_MISMATCH"
    )
