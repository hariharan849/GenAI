from main import DEFAULT_PORT


def test_content_builder_default_port_is_dedicated() -> None:
    assert DEFAULT_PORT == 8003
