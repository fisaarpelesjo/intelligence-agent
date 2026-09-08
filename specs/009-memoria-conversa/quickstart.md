# Quickstart: memoria_conversa

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
print(resultado.accepted, resultado.reason_code)  # sempre False, "inbound_desabilitado"
```

Rodar os testes deste pacote: `uv run pytest packages/memoria_conversa`.
