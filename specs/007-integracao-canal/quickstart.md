# Quickstart: integracao_canal

```python
from integracao_canal import ChannelCapability, entregar
from integracao_canal.identidade import FakeIdentityRegistry
from integracao_canal.fake_channel import FakeChannel

capability = ChannelCapability(
    channel_id="fake", max_message_length=200, supports_multiple_messages=True
)
channel = FakeChannel(capability=capability)
registry = FakeIdentityRegistry()

resultado = entregar(
    channel,
    registry,
    channel_id="fake",
    raw_sender_id="12345",
    sentences=["Signups foi 150 em julho.", "Variacao de 50% em relacao ao mes anterior."],
)

print(resultado.success, resultado.reason_code)
print(channel.sent)  # lista de (registry_ref, texto) efetivamente enviados
```

Rodar os testes deste pacote: `uv run pytest packages/integracao_canal`.
