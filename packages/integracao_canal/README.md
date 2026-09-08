# integracao_canal

Resolve identidade via registro derivado (nunca o identificador bruto do canal) e planeja entrega respeitando a capacidade do canal, sem nunca resumir ou truncar conteudo. Ve `specs/007-integracao-canal/spec.md` para a especificacao completa.

## Uso

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
print(channel.sent)
```

## Garantias

- `RegistryRef` nunca e igual ao identificador bruto do canal; a mesma origem sempre resolve para o mesmo ref.
- Sentencas nunca sao cortadas no meio; uma sentenca isolada que excede a capacidade e recusada, nunca truncada.
- Canal sem suporte a multiplas mensagens recusa a entrega inteira em vez de enviar parcialmente.

## Testes

```bash
uv run pytest packages/integracao_canal
```
