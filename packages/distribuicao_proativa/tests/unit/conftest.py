import pytest
from distribuicao_proativa import ChannelGateConfig
from integracao_canal import ChannelCapability
from integracao_canal.fake_channel import FakeChannel
from integracao_canal.identidade import FakeIdentityRegistry
from priorizacao_insights import InsightCandidate, priorizar


@pytest.fixture
def insight_priorizavel():
    resultado = priorizar(
        [
            InsightCandidate(
                identifier="signups:2026-08-14", magnitude=50, confidence=0.9, reach=1000
            )
        ]
    )
    return resultado.prioritized[0]


@pytest.fixture
def channel() -> FakeChannel:
    capability = ChannelCapability(
        channel_id="fake", max_message_length=200, supports_multiple_messages=True
    )
    return FakeChannel(capability=capability)


@pytest.fixture
def registry() -> FakeIdentityRegistry:
    return FakeIdentityRegistry()


@pytest.fixture
def gate_habilitado() -> ChannelGateConfig:
    return ChannelGateConfig(
        channel_id="fake", enabled=True, allowed_raw_sender_ids=frozenset({"12345"})
    )
