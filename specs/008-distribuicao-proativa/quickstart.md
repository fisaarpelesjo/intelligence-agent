# Quickstart: distribuicao_proativa

```python
from priorizacao_insights import InsightCandidate, priorizar
from integracao_canal import ChannelCapability
from integracao_canal.fake_channel import FakeChannel
from integracao_canal.identidade import FakeIdentityRegistry
from distribuicao_proativa import ChannelGateConfig, distribuir

candidato = InsightCandidate(
    identifier="signups:2026-08-14", magnitude=50, confidence=0.9, reach=1000
)
resultado_priorizacao = priorizar([candidato])
insight = resultado_priorizacao.prioritized[0]

capability = ChannelCapability(
    channel_id="fake", max_message_length=200, supports_multiple_messages=True
)
channel = FakeChannel(capability=capability)
registry = FakeIdentityRegistry()
gate = ChannelGateConfig(channel_id="fake", enabled=True, allowed_raw_sender_ids={"12345"})

resultado = distribuir(insight, gate, "12345", channel, registry)

print(resultado.originated, resultado.reason_code)
print(channel.sent)
```

Rodar os testes deste pacote: `uv run pytest packages/distribuicao_proativa`.
