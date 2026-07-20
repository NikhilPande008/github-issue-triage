from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_creates_required_tables(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")

    assert set(inspect(create_engine(database_url)).get_table_names()) >= {
        "alembic_version",
        "investigations",
        "hypotheses",
        "artifacts",
        "llm_calls",
    }
    columns = {column["name"]: column for column in inspect(create_engine(database_url)).get_columns("llm_calls")}
    assert columns["latency_ms"]["nullable"] is False
    assert columns["investigation_id"]["nullable"] is True
    assert columns["attempt_number"]["nullable"] is True
    assert columns["provider"]["nullable"] is True
    assert columns["pricing_version"]["nullable"] is True
    assert columns["cost_usd"]["nullable"] is True
    investigation_columns = {
        column["name"]: column for column in inspect(create_engine(database_url)).get_columns("investigations")
    }
    assert investigation_columns["asserts_failure"]["nullable"] is False
    assert investigation_columns["validation_reason"]["nullable"] is True
    assert investigation_columns["classification_model"]["nullable"] is True
    assert investigation_columns["classification_completed_at"]["nullable"] is True
