from sqlalchemy import inspect

from triage.persistence.database import Base, create_engine_from_url
import triage.persistence.models  # noqa: F401 -- registers mapped tables


def test_metadata_creates_required_tables(tmp_path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'triage.db'}")
    Base.metadata.create_all(engine)
    assert set(inspect(engine).get_table_names()) == {
        "investigations",
        "hypotheses",
        "artifacts",
        "llm_calls",
        "webhook_jobs",
        "similarity_documents",
            "duplicate_candidates",
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
