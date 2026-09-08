from integracao_canal import ChannelCapability, entregar
from integracao_canal.fake_channel import FakeChannel
from integracao_canal.identidade import FakeIdentityRegistry


def test_canal_sem_suporte_a_multiplas_mensagens_recusa_sem_enviar() -> None:
    capability = ChannelCapability(
        channel_id="fake", max_message_length=10, supports_multiple_messages=False
    )
    channel = FakeChannel(capability=capability)
    registry = FakeIdentityRegistry()

    resultado = entregar(channel, registry, "fake", "12345", ["Primeira.", "Segunda.", "Terceira."])

    assert resultado.success is False
    assert resultado.reason_code == "canal_nao_suporta_multiplas_mensagens"
    assert channel.sent == []


def test_entrega_com_sucesso_envia_todos_os_blocos() -> None:
    capability = ChannelCapability(
        channel_id="fake", max_message_length=100, supports_multiple_messages=True
    )
    channel = FakeChannel(capability=capability)
    registry = FakeIdentityRegistry()

    resultado = entregar(channel, registry, "fake", "12345", ["Ola.", "Tudo bem?"])

    assert resultado.success is True
    assert resultado.blocks_sent == 1
    assert len(channel.sent) == 1


def test_falha_no_envio_e_nomeada_e_para_a_entrega() -> None:
    capability = ChannelCapability(
        channel_id="fake", max_message_length=10, supports_multiple_messages=True
    )
    channel = FakeChannel(capability=capability, fail_after=0)
    registry = FakeIdentityRegistry()

    resultado = entregar(channel, registry, "fake", "12345", ["Primeira.", "Segunda."])

    assert resultado.success is False
    assert resultado.reason_code == "falha_no_envio"
    assert resultado.blocks_sent == 0
