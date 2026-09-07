from pathlib import Path

import pytest
from catalogo_semantico import Catalogo, carregar_catalogo

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "catalogo_exemplo"


@pytest.fixture
def catalogo() -> Catalogo:
    return carregar_catalogo(FIXTURE_DIR)
