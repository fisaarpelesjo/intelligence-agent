# distribuicao_proativa

Gate de 3 condicoes (finding priorizavel + canal habilitado + destinatario na allow-list) que origina uma mensagem de campos rotulados via `integracao_canal`. Ve `specs/008-distribuicao-proativa/spec.md` para a especificacao completa.

## Uso

```python
from priorizacao_insights import InsightCandidate, priorizar
from integracao_canal import ChannelCapability
from integracao_canal.fake_channel import FakeChannel
from integracao_canal.identidade import FakeIdentityRegistry
from distribuicao_proativa import ChannelGateConfig, distribuir

candidato = InsightCandidate(
    identifier="signups:2026-08-14", magnitude=50, confidence=0.9, reach=1000
)
insight = priorizar([candidato]).prioritized[0]

capability = ChannelCapability(
    channel_id="fake", max_message_length=200, supports_multiple_messages=True
)
channel = FakeChannel(capability=capability)
registry = FakeIdentityRegistry()
gate = ChannelGateConfig(
    channel_id="fake", enabled=True, allowed_raw_sender_ids=frozenset({"12345"})
)

resultado = distribuir(insight, gate, "12345", channel, registry)

print(resultado.originated, resultado.reason_code)
print(channel.sent)
```

## Garantias

- Mensagem so e originada quando as 3 condicoes sao verdadeiras simultaneamente.
- Qualquer condicao falha impede toda chamada a `integracao_canal.entregar()`.
- Conteudo enviado e sempre campos rotulados (`"rotulo: valor"`), nunca frase composta livre.

## Testes

```bash
uv run pytest packages/distribuicao_proativa
```
