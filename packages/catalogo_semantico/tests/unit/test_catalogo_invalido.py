from pathlib import Path

import pytest
from catalogo_semantico.carregamento import CatalogoInvalido, carregar_catalogo

_VERSAO_BASE = """
        label: "L"
        source_view: v
        grain: month
        aggregation: sum
        unit: count
        allowed_dimensions: []
"""


def _write(base: Path, metrics_yaml: str) -> None:
    (base / "metrics.yaml").write_text(metrics_yaml, encoding="utf-8")
    (base / "dimensions.yaml").write_text("dimensions: []\n", encoding="utf-8")


def test_metricas_com_id_duplicado_falham_na_carga(tmp_path: Path) -> None:
    metrics_yaml = f"""
metrics:
  - id: signups
    status: active
    versions:
      - effective_from: 2026-01-01
{_VERSAO_BASE}
  - id: signups
    status: active
    versions:
      - effective_from: 2026-01-01
{_VERSAO_BASE}
"""
    _write(tmp_path, metrics_yaml)

    with pytest.raises(CatalogoInvalido, match="duplicate metric id"):
        carregar_catalogo(tmp_path)


def test_versoes_com_janela_sobreposta_falham_na_carga(tmp_path: Path) -> None:
    metrics_yaml = f"""
metrics:
  - id: signups
    status: active
    versions:
      - effective_from: 2026-01-01
        effective_until: 2026-06-01
{_VERSAO_BASE}
      - effective_from: 2026-05-01
{_VERSAO_BASE}
"""
    _write(tmp_path, metrics_yaml)

    with pytest.raises(CatalogoInvalido, match="overlapping version windows"):
        carregar_catalogo(tmp_path)
