from intelligence_agent import __version__


def test_package_importable() -> None:
    assert __version__ == "0.1.0"
