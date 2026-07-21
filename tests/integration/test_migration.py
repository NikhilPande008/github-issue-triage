from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


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


def test_codex_cost_migration_only_nulls_unambiguously_identified_synthetic_costs(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'codex-costs.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0006")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO llm_calls (id, investigation_id, attempt_number, provider, model, pricing_version, purpose,
                input_tokens, cached_input_tokens, output_tokens, cost_usd, latency_ms)
            VALUES
                ('codex-provider', NULL, 1, 'codex', 'codex', NULL, 'investigation', 0, 0, 0, 0, 1),
                ('codex-legacy', NULL, NULL, NULL, 'codex', NULL, 'investigation', 0, 0, 0, 0, 1),
                ('openai-zero', NULL, NULL, 'openai', 'zero-priced', 'test', 'issue_extraction', 1, 0, 1, 0, 1)
        """))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        costs = dict(connection.execute(text("SELECT id, cost_usd FROM llm_calls")).all())
    assert costs["codex-provider"] is None
    assert costs["codex-legacy"] is None
    assert float(costs["openai-zero"]) == 0
