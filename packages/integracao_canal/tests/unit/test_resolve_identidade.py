from integracao_canal.identidade import FakeIdentityRegistry, resolver_identidade


def test_ref_e_diferente_do_identificador_bruto() -> None:
    registry = FakeIdentityRegistry()

    ref = resolver_identidade(registry, "fake", "12345")

    assert ref != "12345"


def test_resolucao_e_idempotente() -> None:
    registry = FakeIdentityRegistry()

    primeiro = resolver_identidade(registry, "fake", "12345")
    segundo = resolver_identidade(registry, "fake", "12345")

    assert primeiro == segundo


def test_identificadores_diferentes_geram_refs_diferentes() -> None:
    registry = FakeIdentityRegistry()

    ref_a = resolver_identidade(registry, "fake", "12345")
    ref_b = resolver_identidade(registry, "fake", "67890")

    assert ref_a != ref_b
