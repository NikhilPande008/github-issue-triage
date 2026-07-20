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
    }
