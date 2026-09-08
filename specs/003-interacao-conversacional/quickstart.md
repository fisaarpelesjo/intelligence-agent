# Quickstart: interacao_conversacional

```python
from datetime import date
from catalogo_semantico import carregar_catalogo
from execucao_query.fake_data_source import FakeDataSource
from interacao_conversacional import QuestionIntent, responder
from interacao_conversacional.llm_provider_stub import LLMProviderStub

catalogo = carregar_catalogo("packages/catalogo_semantico/catalog")

intent = QuestionIntent(
    metric_id="signups",
    dimension_id="country",
    dimension_value="BR",
    period_expression="mes_passado",
)

resultado = responder(
    intent,
    catalogo,
    data_source=FakeDataSource(),
    llm_provider=LLMProviderStub(),
    reference_today=date(2026, 8, 15),
    max_bytes=10_000_000,
    max_rows=1_000,
)

if resultado.success:
    for sentenca in resultado.sentences:
        print(f"[{sentenca.claim_class}] {sentenca.text}")
else:
    print(f"recusado: {resultado.reason_code}")
```

Rodar os testes deste pacote: `uv run pytest packages/interacao_conversacional`.
