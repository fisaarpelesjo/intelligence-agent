from integracao_canal import ChannelCapability
from integracao_canal.entrega import planejar_entrega


def test_multiplos_blocos_preservam_conteudo_exato() -> None:
    capability = ChannelCapability(
        channel_id="fake", max_message_length=20, supports_multiple_messages=True
    )
    sentences = ["Primeira sentenca.", "Segunda sentenca.", "Terceira sentenca."]

    plano = planejar_entrega(capability, sentences)

    assert not isinstance(plano, str)
    assert len(plano.blocks) >= 2
    reconstituido = [s for bloco in plano.blocks for s in bloco]
    assert reconstituido == sentences


def test_sentenca_isolada_excede_capacidade_e_recusada() -> None:
    capability = ChannelCapability(
        channel_id="fake", max_message_length=10, supports_multiple_messages=True
    )

    plano = planejar_entrega(capability, ["Esta sentenca e maior que dez caracteres."])

    assert plano == "sentenca_excede_capacidade"


def test_lista_vazia_retorna_plano_sem_blocos() -> None:
    capability = ChannelCapability(
        channel_id="fake", max_message_length=100, supports_multiple_messages=True
    )

    plano = planejar_entrega(capability, [])

    assert not isinstance(plano, str)
    assert plano.blocks == ()
