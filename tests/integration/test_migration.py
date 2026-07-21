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
        "review_packets",
        "review_assessments",
        "review_assessment_audit",
        "review_consensus_snapshots",
        "posting_approvals",
        "posting_approval_events",
        "review_activities",
        "review_work_sessions",
        "pilot_weekly_reports",
        "corpus_consents",
        "corpus_exports",
        "automation_eligibility_policies",
        "eligibility_reports",
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
    assert investigation_columns["review_packet_status"]["nullable"] is True
    packet_columns = {column["name"]: column for column in inspect(create_engine(database_url)).get_columns("review_packets")}
    assert packet_columns["snapshot_json"]["nullable"] is False
    assert packet_columns["integrity_hash"]["nullable"] is False
    assessment_columns = {column["name"]: column for column in inspect(create_engine(database_url)).get_columns("review_assessments")}
    assert assessment_columns["packet_hash"]["nullable"] is False
    assert assessment_columns["test_aligned"]["nullable"] is False
    consensus_columns = {column["name"]: column for column in inspect(create_engine(database_url)).get_columns("review_consensus_snapshots")}
    assert consensus_columns["snapshot_hash"]["nullable"] is False
    approval_columns = {column["name"]: column for column in inspect(create_engine(database_url)).get_columns("posting_approvals")}
    assert approval_columns["comment_body_hash"]["nullable"] is False


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


def test_behavior_gap_migration_renames_only_legacy_reproduced_verdict(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'behavior-gap.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0007")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO investigations (id, repository, issue_number, status, classification, asserts_failure)
            VALUES
                ('legacy-gap', 'psf/requests', 1, 'COMPLETED', 'REPRODUCED', 1),
                ('needs-info', 'psf/requests', 2, 'COMPLETED', 'NEEDS_INFO', 0)
        """))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        classifications = dict(connection.execute(text("SELECT id, classification FROM investigations")).all())
    assert classifications["legacy-gap"] == "BEHAVIOR_GAP_CONFIRMED"
    assert classifications["needs-info"] == "NEEDS_INFO"


def test_completed_no_gap_migration_preserves_operational_failures(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'completed-no-gap.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0021")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO investigations (id, repository, issue_number, status, classification, asserts_failure)
            VALUES
                ('needs-info', 'psf/requests', 1, 'FAILED', 'NEEDS_INFO', 0),
                ('wont-repro', 'psf/requests', 2, 'FAILED', 'WONT_REPRO', 0),
                ('confirmed', 'psf/requests', 3, 'COMPLETED', 'BEHAVIOR_GAP_CONFIRMED', 1),
                ('setup-failure', 'psf/requests', 4, 'FAILED', NULL, 0)
        """))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        statuses = dict(connection.execute(text("SELECT id, status FROM investigations")).all())
    assert statuses == {
        "needs-info": "COMPLETED_NO_GAP",
        "wont-repro": "COMPLETED_NO_GAP",
        "confirmed": "COMPLETED",
        "setup-failure": "FAILED",
    }
