"""Export selected investigation evidence to the committed offline-demo format."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy import text
from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from triage.persistence.database import Base, create_session_factory  # noqa: E402
from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall  # noqa: E402


def copy_row(model, row):
    return model(**{column.name: getattr(row, column.name) for column in model.__table__.columns})


def alembic_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head() or ""


def artifact_relative_path(path: str) -> Path:
    relative = Path(path).relative_to("artifacts")
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"artifact path escapes artifact root: {path}")
    return relative


def main() -> int:
    parser = argparse.ArgumentParser(description="Export selected evidence without copying the live database.")
    parser.add_argument("--investigation-id", action="append", required=True, help="Investigation ID to include; repeat as needed.")
    parser.add_argument("--source-database", default=f"sqlite:///{ROOT / 'triage.db'}")
    parser.add_argument("--source-artifacts", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--destination-database", type=Path, default=ROOT / "demo" / "seed" / "triage-demo.db")
    parser.add_argument("--destination-artifacts", type=Path, default=ROOT / "demo" / "seed" / "artifacts")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    ids = set(args.investigation_id)
    if (args.destination_database.exists() or args.destination_artifacts.exists()) and not args.force:
        parser.error("demo destination exists; pass --force to replace it")
    if args.destination_database.exists():
        args.destination_database.unlink()
    if args.destination_artifacts.exists():
        shutil.rmtree(args.destination_artifacts)
    args.destination_database.parent.mkdir(parents=True, exist_ok=True)
    source_factory = create_session_factory(args.source_database)
    destination_factory = create_session_factory(f"sqlite:///{args.destination_database}")
    Base.metadata.create_all(destination_factory.kw["bind"])
    with source_factory() as source, destination_factory() as destination:
        investigations = list(source.scalars(select(Investigation).where(Investigation.id.in_(ids))))
        if len(investigations) != len(ids):
            parser.error("one or more investigation IDs were not found")
        destination.add_all(copy_row(Investigation, item) for item in investigations)
        for model in (Hypothesis, Artifact, LLMCall):
            destination.add_all(copy_row(model, item) for item in source.scalars(select(model).where(model.investigation_id.in_(ids))))
        destination.commit()
        destination.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        destination.execute(text("INSERT INTO alembic_version (version_num) VALUES (:head)"), {"head": alembic_head()})
        destination.commit()
        artifacts = list(source.scalars(select(Artifact).where(Artifact.investigation_id.in_(ids))))
    for artifact in artifacts:
        relative_path = artifact_relative_path(artifact.path)
        source_path = args.source_artifacts / relative_path
        if not source_path.is_file():
            parser.error(f"persisted artifact is missing from source root: {artifact.path}")
        target_path = args.destination_artifacts / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    print(f"Exported {len(ids)} investigation(s) to {args.destination_database}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
