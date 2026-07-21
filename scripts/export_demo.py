"""Export selected investigation evidence to the committed offline-demo format."""

from __future__ import annotations

import argparse
import json
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
from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall, ReviewPacket  # noqa: E402
from triage.validation.junit import matches_selected_node, parse_junit_xml  # noqa: E402


REQUESTS_TARGET = "tests/test_requests.py::TestRequests::test_invalid_ssl_certificate_files"


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


def _artifact_path(source_artifacts: Path, artifact: Artifact) -> Path:
    return source_artifacts / artifact_relative_path(artifact.path)


def _json_artifact(source_artifacts: Path, artifact: Artifact) -> dict:
    try:
        value = json.loads(_artifact_path(source_artifacts, artifact).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {artifact.kind} for {artifact.investigation_id}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{artifact.kind} for {artifact.investigation_id} is not a JSON object")
    return value


def validate_modern_requests_confirmation(investigation: Investigation, artifacts: list[Artifact], source_artifacts: Path) -> None:
    """Reject a legacy or incomplete Requests flagship before it can be exported."""
    if investigation.status.value != "COMPLETED" or investigation.classification is None or investigation.classification.value != "BEHAVIOR_GAP_CONFIRMED" or not investigation.asserts_failure:
        raise ValueError("Requests flagship must be completed, behavior-gap confirmed, and asserts_failure=true")
    grouped = {kind: [item for item in artifacts if item.kind == kind] for kind in {item.kind for item in artifacts}}
    required = ("structured_test_results_junit", "proof_integrity_report", "focused_test_selection", "reproducibility_manifest")
    if any(not grouped.get(kind) for kind in required):
        raise ValueError("Requests flagship lacks required modern JUnit, proof-integrity, focused-selection, or manifest evidence")
    selections = [_json_artifact(source_artifacts, item) for item in grouped["focused_test_selection"]]
    if not all(item.get("precision") == "EXACT" and item.get("targets") == [REQUESTS_TARGET] for item in selections):
        raise ValueError("Requests flagship does not persist the required exact pytest target")
    if not any(_json_artifact(source_artifacts, item).get("result") == "ACCEPTABLE" for item in grouped["proof_integrity_report"]):
        raise ValueError("Requests flagship has no acceptable proof-integrity report")
    manifests = [_json_artifact(source_artifacts, item) for item in grouped["reproducibility_manifest"]]
    confirmation_runs = max(int(item.get("confirmation_runs", 1) or 1) for item in manifests)
    if len(manifests) < confirmation_runs or any(item.get("execution_failure_reason") for item in manifests):
        raise ValueError("Requests flagship lacks clean persisted confirmation evidence")
    reports = [parse_junit_xml(_artifact_path(source_artifacts, item), "pytest", [REQUESTS_TARGET]) for item in grouped["structured_test_results_junit"]]
    if len(reports) < confirmation_runs or any(report.rejection_reason or report.total != 1 or report.failed != 1 or report.errors or not all(matches_selected_node(case.path, case.name, [REQUESTS_TARGET]) for case in report.cases if case.outcome == "failure") for report in reports):
        raise ValueError("Requests flagship JUnit evidence is incomplete, contains unrelated results, or does not match the exact selected target")


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
    source_factory = create_session_factory(args.source_database)
    with source_factory() as source:
        investigations = list(source.scalars(select(Investigation).where(Investigation.id.in_(ids))))
        if len(investigations) != len(ids):
            parser.error("one or more investigation IDs were not found")
        artifacts = list(source.scalars(select(Artifact).where(Artifact.investigation_id.in_(ids))))
        for investigation in investigations:
            if investigation.repository == "psf/requests" and investigation.issue_number == 7564:
                try:
                    validate_modern_requests_confirmation(investigation, [item for item in artifacts if item.investigation_id == investigation.id], args.source_artifacts)
                except ValueError as error:
                    parser.error(str(error))
    if (args.destination_database.exists() or args.destination_artifacts.exists()) and not args.force:
        parser.error("demo destination exists; pass --force to replace it")
    if args.destination_database.exists():
        args.destination_database.unlink()
    if args.destination_artifacts.exists():
        shutil.rmtree(args.destination_artifacts)
    args.destination_database.parent.mkdir(parents=True, exist_ok=True)
    destination_factory = create_session_factory(f"sqlite:///{args.destination_database}")
    Base.metadata.create_all(destination_factory.kw["bind"])
    with source_factory() as source, destination_factory() as destination:
        investigations = list(source.scalars(select(Investigation).where(Investigation.id.in_(ids))))
        destination.add_all(copy_row(Investigation, item) for item in investigations)
        # Packets are immutable persisted snapshots. Copy only packets belonging
        # to the explicitly selected investigations; never copy the live DB.
        for model in (Hypothesis, Artifact, LLMCall, ReviewPacket):
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
