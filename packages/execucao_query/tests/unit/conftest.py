from datetime import date

import pytest
from catalogo_semantico import AccessDecision, MetricDefinitionVersion
from catalogo_semantico.modelos import Aggregation, Grain


@pytest.fixture
def decisao_permitida() -> AccessDecision:
    versao = MetricDefinitionVersion(
        effective_from=date(2026, 1, 1),
        label="Novos cadastros",
        source_view="signups_v1",
        grain=Grain.DAY,
        aggregation=Aggregation.COUNT,
        unit="count",
        allowed_dimensions=("country",),
    )
    return AccessDecision(allowed=True, resolved_metric_version=versao)


@pytest.fixture
def decisao_negada() -> AccessDecision:
    return AccessDecision(allowed=False, reason_code=None)
