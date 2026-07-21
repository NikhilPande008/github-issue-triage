"""Deterministically validate the committed offline demo seed."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from triage.validation.junit import matches_selected_node, parse_junit_xml  # noqa: E402

REQUESTS_TARGET = "tests/test_requests.py::TestRequests::test_invalid_ssl_certificate_files"


def alembic_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head() or ""


def validate(database: Path, artifacts: Path, manifest_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"cannot read manifest: {error}"]
    required = {"schema_version", "exported_at", "investigations"}
    if not required.issubset(manifest): errors.append("manifest is missing required top-level fields")
    entries = manifest.get("investigations", [])
    if not entries: errors.append("manifest contains no investigations")
    ids = [entry.get("id") for entry in entries]
    if len(ids) != len(set(ids)): errors.append("manifest contains duplicate investigation IDs")
    try:
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as error:
        return [f"cannot open demo database: {error}"]
    with connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if not version or version["version_num"] != alembic_head(): errors.append("demo database is not at the current Alembic head")
        confirmed = completed_no_gap = 0
        artifact_root = artifacts.resolve()
        flagship: tuple[sqlite3.Row, list[sqlite3.Row]] | None = None
        for entry in entries:
            row = connection.execute("SELECT repository, issue_number, issue_title, classification, asserts_failure, status FROM investigations WHERE id = ?", (entry.get("id"),)).fetchone()
            if not row:
                errors.append(f"manifest investigation is absent: {entry.get('id')}"); continue
            for field in ("repository", "issue_number", "title", "classification", "assertsFailure"):
                actual = {"title": "issue_title", "assertsFailure": "asserts_failure"}.get(field, field)
                if entry.get(field) != row[actual]: errors.append(f"manifest {field} does not match database for {entry.get('id')}")
            artifact_rows = connection.execute("SELECT kind, path FROM artifacts WHERE investigation_id = ?", (entry.get("id"),)).fetchall()
            if entry.get("artifact_count") != len(artifact_rows): errors.append(f"manifest artifact_count does not match database for {entry.get('id')}")
            for artifact in artifact_rows:
                relative = Path(artifact["path"])
                if not relative.parts or relative.parts[0] != "artifacts": errors.append(f"artifact path has unexpected root: {relative}"); continue
                destination = (artifacts / Path(*relative.parts[1:])).resolve()
                if artifact_root not in destination.parents or not destination.is_file(): errors.append(f"artifact missing or outside demo root: {relative}")
            confirmed += row["classification"] == "BEHAVIOR_GAP_CONFIRMED"
            completed_no_gap += row["status"] == "COMPLETED_NO_GAP" and row["classification"] is not None
            if row["repository"] == "psf/requests" and row["issue_number"] == 7564:
                flagship = (row, artifact_rows)
        if not confirmed: errors.append("demo lacks a confirmed behavior-gap case")
        if not completed_no_gap: errors.append("demo lacks a classified completed-no-gap case")
        if flagship is None:
            errors.append("demo lacks the Requests #7564 flagship")
        else:
            row, artifact_rows = flagship
            if row["status"] != "COMPLETED" or row["classification"] != "BEHAVIOR_GAP_CONFIRMED" or not row["asserts_failure"]:
                errors.append("Requests flagship is not a completed confirmed case")
            by_kind: dict[str, list[Path]] = {}
            for artifact in artifact_rows:
                by_kind.setdefault(artifact["kind"], []).append(artifacts / Path(*Path(artifact["path"]).parts[1:]))
            required = ("structured_test_results_junit", "proof_integrity_report", "focused_test_selection", "reproducibility_manifest")
            if any(not by_kind.get(kind) for kind in required):
                errors.append("Requests flagship lacks required modern evidence artifacts")
            else:
                try:
                    selections = [json.loads(item.read_text(encoding="utf-8")) for item in by_kind["focused_test_selection"]]
                    if not all(item.get("precision") == "EXACT" and item.get("targets") == [REQUESTS_TARGET] for item in selections): errors.append("Requests flagship exact target is missing or incorrect")
                    proofs = [json.loads(item.read_text(encoding="utf-8")) for item in by_kind["proof_integrity_report"]]
                    if not any(item.get("result") == "ACCEPTABLE" for item in proofs): errors.append("Requests flagship lacks an acceptable proof-integrity report")
                    manifests = [json.loads(item.read_text(encoding="utf-8")) for item in by_kind["reproducibility_manifest"]]
                    required_runs = max(int(item.get("confirmation_runs", 1) or 1) for item in manifests)
                    if len(manifests) < required_runs or any(item.get("execution_failure_reason") for item in manifests): errors.append("Requests flagship confirmation evidence is incomplete or unclean")
                    reports = [parse_junit_xml(item, "pytest", [REQUESTS_TARGET]) for item in by_kind["structured_test_results_junit"]]
                    if len(reports) < required_runs or any(report.rejection_reason or report.total != 1 or report.failed != 1 or report.errors or not all(matches_selected_node(case.path, case.name, [REQUESTS_TARGET]) for case in report.cases if case.outcome == "failure") for report in reports): errors.append("Requests flagship JUnit evidence does not match the exact selected target cleanly")
                except (OSError, json.JSONDecodeError, ValueError) as error:
                    errors.append(f"cannot validate Requests flagship evidence: {error}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the committed offline demo seed.")
    parser.add_argument("--database", type=Path, default=ROOT / "demo" / "seed" / "triage-demo.db")
    parser.add_argument("--artifacts", type=Path, default=ROOT / "demo" / "seed" / "artifacts")
    parser.add_argument("--manifest", type=Path, default=ROOT / "demo" / "seed" / "demo-manifest.json")
    args = parser.parse_args(argv)
    errors = validate(args.database, args.artifacts, args.manifest)
    if errors:
        print("Demo seed validation failed:\n- " + "\n- ".join(errors)); return 1
    print("Demo seed validation passed."); return 0


if __name__ == "__main__":
    raise SystemExit(main())
