import inspect

from memoria_conversa import InMemoryConversationMemory, processar_mensagem_inbound


def test_qualquer_payload_e_recusado() -> None:
    for payload in [{"a": 1}, "texto livre", None, 12345, ["lista"]]:
        resultado = processar_mensagem_inbound(payload)
        assert resultado.accepted is False
        assert resultado.reason_code == "inbound_desabilitado"


def test_assinatura_nao_aceita_referencia_a_memoria() -> None:
    assinatura = inspect.signature(processar_mensagem_inbound)
    for parametro in assinatura.parameters.values():
        assert parametro.annotation is not InMemoryConversationMemory
