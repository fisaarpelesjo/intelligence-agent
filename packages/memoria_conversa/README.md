# memoria_conversa

Memoria de turno de conversa de curto prazo, indexada por `RegistryRef`, com processamento de mensagem inbound estruturalmente desligado. Ve `specs/009-memoria-conversa/spec.md` para a especificacao completa.

## Uso

```python
from datetime import datetime, timedelta, UTC
from memoria_conversa import ConversationTurn, InMemoryConversationMemory
from memoria_conversa.inbound import processar_mensagem_inbound

memoria = InMemoryConversationMemory()
agora = datetime.now(UTC)

memoria.registrar_turno(
    ConversationTurn(
        registry_ref="registry-ref-1",
        metric_id="signups",
        period_expression="mes_passado",
        recorded_at=agora,
    )
)

turnos = memoria.turnos_recentes("registry-ref-1", reference_now=agora, max_age=timedelta(days=1))
print(turnos)

resultado = processar_mensagem_inbound({"qualquer": "coisa"})
print(resultado.accepted, resultado.reason_code)
```

## Garantias

- Turnos sao sempre indexados por `RegistryRef` — nunca por identificador bruto de canal.
- Turno fora da janela de retencao configurada nunca e retornado.
- `processar_mensagem_inbound()` sempre recusa e nao tem, por assinatura, nenhuma forma de acessar a memoria.

## Testes

```bash
uv run pytest packages/memoria_conversa
```
