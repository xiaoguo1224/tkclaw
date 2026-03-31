from app.utils.alembic_url import escape_for_alembic_config


def test_escape_for_alembic_config_keeps_plain_url() -> None:
    url = "postgresql+asyncpg://user:password@localhost:5432/nodeskclaw"

    assert escape_for_alembic_config(url) == url


def test_escape_for_alembic_config_escapes_percent_sequences() -> None:
    url = "postgresql+asyncpg://user:P%40ss%25word@localhost:5432/nodeskclaw"

    assert escape_for_alembic_config(url) == "postgresql+asyncpg://user:P%%40ss%%25word@localhost:5432/nodeskclaw"
