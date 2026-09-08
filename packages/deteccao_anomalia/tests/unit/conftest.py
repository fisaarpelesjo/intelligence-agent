from pathlib import Path

import pytest
from catalogo_semantico import Catalogo, carregar_catalogo

CATALOG_DIR = Path(__file__).resolve().parents[3] / "catalogo_semantico" / "catalog"


@pytest.fixture
def catalogo() -> Catalogo:
    return carregar_catalogo(CATALOG_DIR)
