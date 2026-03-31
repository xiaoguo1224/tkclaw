def escape_for_alembic_config(database_url: str) -> str:
    return database_url.replace("%", "%%")
